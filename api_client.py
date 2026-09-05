from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Callable, Iterable


API_URL = "https://api.openai.com/v1/responses"


class OpenAIError(RuntimeError):
    pass


class ResponseCancelled(OpenAIError):
    pass


@dataclass(frozen=True)
class ResponseResult:
    text: str
    response_id: str | None = None
    input_tokens: int | None = None
    output_tokens: int | None = None

    @property
    def total_tokens(self) -> int | None:
        if self.input_tokens is None and self.output_tokens is None:
            return None
        return (self.input_tokens or 0) + (self.output_tokens or 0)


def create_response(
    *,
    api_key: str,
    model: str,
    instructions: str,
    input_items: list[dict[str, Any]],
    max_output_tokens: int = 1800,
    timeout: int = 90,
) -> ResponseResult:
    if not api_key.strip():
        raise OpenAIError("OpenAI API 키가 설정되지 않았습니다.")
    if not model.strip():
        raise OpenAIError("모델 이름이 비어 있습니다.")

    request = _request(
        api_key=api_key,
        model=model,
        instructions=instructions,
        input_items=input_items,
        max_output_tokens=max_output_tokens,
        stream=False,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = _http_error_message(error)
        raise OpenAIError(_friendly_http_error(error.code, detail)) from error
    except urllib.error.URLError as error:
        raise OpenAIError(f"네트워크 연결에 실패했습니다: {error.reason}") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OpenAIError("OpenAI 응답을 읽지 못했습니다.") from error

    text = extract_output_text(body)
    if not text:
        raise OpenAIError("OpenAI가 빈 응답을 반환했습니다.")
    return _result_from_body(body, text)


def create_streaming_response(
    *,
    api_key: str,
    model: str,
    instructions: str,
    input_items: list[dict[str, Any]],
    on_delta: Callable[[str], None],
    cancel_event: threading.Event | None = None,
    max_output_tokens: int = 1800,
    timeout: int = 90,
) -> ResponseResult:
    if not api_key.strip():
        raise OpenAIError("OpenAI API 키가 설정되지 않았습니다.")
    if not model.strip():
        raise OpenAIError("모델 이름이 비어 있습니다.")

    request = _request(
        api_key=api_key,
        model=model,
        instructions=instructions,
        input_items=input_items,
        max_output_tokens=max_output_tokens,
        stream=True,
    )
    cancel_event = cancel_event or threading.Event()
    chunks: list[str] = []
    completed: dict[str, Any] | None = None
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            for event in iter_sse_events(response):
                if cancel_event.is_set():
                    raise ResponseCancelled("요청이 취소되었습니다.")
                event_type = event.get("type")
                if event_type == "response.output_text.delta":
                    delta = event.get("delta")
                    if isinstance(delta, str) and delta:
                        chunks.append(delta)
                        on_delta(delta)
                elif event_type == "response.completed":
                    response_body = event.get("response")
                    if isinstance(response_body, dict):
                        completed = response_body
                elif event_type == "response.failed":
                    response_body = event.get("response", {})
                    error = response_body.get("error", {}) if isinstance(response_body, dict) else {}
                    message = error.get("message") if isinstance(error, dict) else None
                    raise OpenAIError(str(message or "OpenAI 응답 생성에 실패했습니다."))
    except urllib.error.HTTPError as error:
        detail = _http_error_message(error)
        raise OpenAIError(_friendly_http_error(error.code, detail)) from error
    except urllib.error.URLError as error:
        raise OpenAIError(f"네트워크 연결에 실패했습니다: {error.reason}") from error
    except UnicodeDecodeError as error:
        raise OpenAIError("OpenAI 스트림을 읽지 못했습니다.") from error

    if cancel_event.is_set():
        raise ResponseCancelled("요청이 취소되었습니다.")
    if completed is None:
        raise OpenAIError("OpenAI 스트림이 완료 이벤트 없이 종료되었습니다.")
    text = "".join(chunks).strip() or extract_output_text(completed)
    if not text:
        raise OpenAIError("OpenAI가 빈 응답을 반환했습니다.")
    return _result_from_body(completed, text)


def iter_sse_events(lines: Iterable[bytes]) -> Iterable[dict[str, Any]]:
    data_lines: list[str] = []
    for raw_line in lines:
        line = raw_line.decode("utf-8").rstrip("\r\n")
        if line == "":
            if data_lines:
                payload = "\n".join(data_lines)
                data_lines.clear()
                if payload != "[DONE]":
                    try:
                        event = json.loads(payload)
                    except json.JSONDecodeError as error:
                        raise OpenAIError("OpenAI 스트림 이벤트를 해석하지 못했습니다.") from error
                    if isinstance(event, dict):
                        yield event
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())
    if data_lines:
        payload = "\n".join(data_lines)
        if payload != "[DONE]":
            try:
                event = json.loads(payload)
            except json.JSONDecodeError as error:
                raise OpenAIError("OpenAI 스트림 이벤트를 해석하지 못했습니다.") from error
            if isinstance(event, dict):
                yield event


def _request(
    *,
    api_key: str,
    model: str,
    instructions: str,
    input_items: list[dict[str, Any]],
    max_output_tokens: int,
    stream: bool,
) -> urllib.request.Request:
    payload = {
        "model": model.strip(),
        "instructions": instructions,
        "input": input_items,
        "max_output_tokens": max_output_tokens,
        "store": False,
        "stream": stream,
    }
    return urllib.request.Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )


def _result_from_body(body: dict[str, Any], text: str) -> ResponseResult:
    usage = body.get("usage", {})
    if not isinstance(usage, dict):
        usage = {}
    input_tokens = usage.get("input_tokens")
    output_tokens = usage.get("output_tokens")
    return ResponseResult(
        text=text,
        response_id=body.get("id"),
        input_tokens=input_tokens if isinstance(input_tokens, int) else None,
        output_tokens=output_tokens if isinstance(output_tokens, int) else None,
    )


def extract_output_text(body: dict[str, Any]) -> str:
    direct = body.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    parts: list[str] = []
    for item in body.get("output", []):
        if not isinstance(item, dict) or item.get("type") != "message":
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                parts.append(content["text"])
    return "\n".join(parts).strip()


def parse_edit_proposal(text: str, valid_fields: set[str]) -> tuple[str, dict[str, str]]:
    candidate = text.strip()
    if candidate.startswith("```"):
        lines = candidate.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        candidate = "\n".join(lines).strip()

    try:
        data = json.loads(candidate)
    except json.JSONDecodeError as error:
        raise OpenAIError("수정 제안이 올바른 JSON 형식이 아닙니다. 다시 시도해 주세요.") from error

    if not isinstance(data, dict) or not isinstance(data.get("updates"), dict):
        raise OpenAIError("수정 제안에 updates 객체가 없습니다.")

    updates = {
        name: value
        for name, value in data["updates"].items()
        if name in valid_fields and isinstance(value, str)
    }
    if not updates:
        raise OpenAIError("적용 가능한 필드 수정안이 없습니다.")
    summary = data.get("summary", "AI가 카드 필드 수정을 제안했습니다.")
    return str(summary), updates


def _http_error_message(error: urllib.error.HTTPError) -> str:
    try:
        body = json.loads(error.read().decode("utf-8"))
        message = body.get("error", {}).get("message")
        if isinstance(message, str) and message:
            return message
    except Exception:
        pass
    return error.reason or "요청 실패"


def _friendly_http_error(status: int, detail: str) -> str:
    if status == 401:
        return "API 키가 유효하지 않습니다. Anki Assist 설정에서 키를 확인해 주세요."
    if status == 403:
        return "이 API 키에는 요청 권한이 없습니다. OpenAI 프로젝트 권한을 확인해 주세요."
    if status == 429:
        return "OpenAI 요청 한도 또는 크레딧을 확인해 주세요. 잠시 후 다시 시도할 수도 있습니다."
    if status >= 500:
        return "OpenAI 서버에서 일시적인 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
    return f"OpenAI API 오류 ({status}): {detail}"
