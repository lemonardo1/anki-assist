from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any


API_URL = "https://api.openai.com/v1/responses"


class OpenAIError(RuntimeError):
    pass


@dataclass(frozen=True)
class ResponseResult:
    text: str
    response_id: str | None = None


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

    payload = {
        "model": model.strip(),
        "instructions": instructions,
        "input": input_items,
        "max_output_tokens": max_output_tokens,
        "store": False,
    }
    request = urllib.request.Request(
        API_URL,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        detail = _http_error_message(error)
        raise OpenAIError(f"OpenAI API 오류 ({error.code}): {detail}") from error
    except urllib.error.URLError as error:
        raise OpenAIError(f"네트워크 연결에 실패했습니다: {error.reason}") from error
    except (UnicodeDecodeError, json.JSONDecodeError) as error:
        raise OpenAIError("OpenAI 응답을 읽지 못했습니다.") from error

    text = extract_output_text(body)
    if not text:
        raise OpenAIError("OpenAI가 빈 응답을 반환했습니다.")
    return ResponseResult(text=text, response_id=body.get("id"))


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
