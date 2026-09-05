from __future__ import annotations

import html
import json
import os
import threading
from collections import OrderedDict
from concurrent.futures import Future
from typing import Any

from aqt import gui_hooks, mw
from aqt.operations import CollectionOp
from aqt.qt import (
    QAction,
    QApplication,
    QComboBox,
    QDockWidget,
    QHBoxLayout,
    QKeySequence,
    QLabel,
    QMenu,
    QMessageBox,
    QPushButton,
    QShortcut,
    QStackedWidget,
    QTabWidget,
    QTextBrowser,
    QToolButton,
    QVBoxLayout,
    QWidget,
    Qt,
)

from .api_client import (
    OpenAIError,
    ResponseResult,
    create_response,
    create_streaming_response,
    parse_edit_proposal,
)
from .dialogs import EditPreviewDialog, SettingsDialog, TemplateDialog
from .formatting import safe_rich_text
from .widgets import SubmitTextEdit


ASK_INSTRUCTIONS = """당신은 Anki 학습 도우미입니다. 제공된 현재 카드만을 학습 문맥으로 사용하세요.
사용자의 언어로 정확하고 간결하게 답하세요. 카드 내용이 부정확해 보이면 불확실성을 명시하세요.
사용자가 카드 자체의 수정을 요청하더라도 질문 모드에서는 설명만 하고 실제 필드를 변경하지 마세요."""

EDIT_INSTRUCTIONS = """당신은 Anki 카드 편집자입니다. 사용자의 지시와 현재 카드 필드를 검토하세요.
반드시 JSON 하나만 출력하세요. 마크다운 코드 펜스를 사용하지 마세요.
형식: {"summary":"수정 이유", "updates":{"정확한 필드명":"필드 전체를 대체할 새 내용"}}
실제로 변경할 필드만 updates에 넣고, 제공된 필드명만 정확히 사용하세요.
HTML이 있으면 필요한 태그를 보존하세요. 사실을 확신할 수 없으면 임의로 추가하지 마세요."""


class AssistDock(QDockWidget):
    def __init__(self) -> None:
        super().__init__("Anki Assist", mw)
        self.setObjectName("anki_assist_ai_dock")
        self.setAllowedAreas(
            Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea
        )
        self.setMinimumWidth(340)
        self._card_id: int | None = None
        self._history: list[dict[str, str]] = []
        self._display_messages: list[dict[str, str]] = []
        self._sessions: OrderedDict[int, dict[str, Any]] = OrderedDict()
        self._conversation_started = False
        self._last_answer = ""
        self._last_question = ""
        self._busy = False
        self._request_serial = 0
        self._status_serial = 0
        self._request_future: Future | None = None
        self._cancel_event: threading.Event | None = None
        self._cancel_callback = None
        self._dialogs: list[QWidget] = []
        self.setWidget(self._build_ui())
        mw.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self)
        self.hide()

    def _build_ui(self) -> QWidget:
        root = QWidget()
        outer = QVBoxLayout(root)
        outer.setContentsMargins(10, 10, 10, 10)

        header = QHBoxLayout()
        title = QLabel("<b>AI 카드 도우미</b>")
        header.addWidget(title)
        header.addStretch(1)
        templates = QToolButton()
        templates.setText("템플릿")
        templates.clicked.connect(self.open_templates)
        settings = QToolButton()
        settings.setText("설정")
        settings.clicked.connect(self.open_settings)
        header.addWidget(templates)
        header.addWidget(settings)
        outer.addLayout(header)

        self.card_label = QLabel("리뷰할 카드를 열어 주세요.")
        self.card_label.setTextFormat(Qt.TextFormat.PlainText)
        self.card_label.setWordWrap(True)
        self.card_label.setStyleSheet("padding: 8px; background: palette(alternate-base); border-radius: 6px;")
        outer.addWidget(self.card_label)

        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_ask_tab(), "후속 질문")
        self.tabs.addTab(self._build_edit_tab(), "카드 수정")
        outer.addWidget(self.tabs, 1)

        status_row = QHBoxLayout()
        self.status_label = QLabel("")
        self.status_label.setTextFormat(Qt.TextFormat.PlainText)
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        self.cancel_button = QPushButton("요청 취소")
        self.cancel_button.clicked.connect(self.cancel_request)
        self.cancel_button.hide()
        status_row.addWidget(self.status_label, 1)
        status_row.addWidget(self.cancel_button)
        outer.addLayout(status_row)
        self._setup_shortcuts(root)
        return root

    def _build_ask_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        self.ask_templates = QComboBox()
        self.ask_templates.currentIndexChanged.connect(self._select_ask_template)
        layout.addWidget(self.ask_templates)

        self.ask_stack = QStackedWidget()
        self.initial_question = SubmitTextEdit()
        self.initial_question.setPlaceholderText(
            "현재 카드에 관해 질문을 바로 입력하세요.\n\n⌘+Enter로 전송"
        )
        self.transcript = QTextBrowser()
        self.transcript.setOpenExternalLinks(True)
        self.transcript.setPlaceholderText("대화 내용이 여기에 표시됩니다.")
        self.ask_stack.addWidget(self.initial_question)
        self.ask_stack.addWidget(self.transcript)
        layout.addWidget(self.ask_stack, 1)

        self.question = SubmitTextEdit()
        self.question.setPlaceholderText("후속 질문 입력…  (⌘+Enter로 전송)")
        self.question.setMaximumHeight(105)
        self.question.hide()
        layout.addWidget(self.question)
        row = QHBoxLayout()
        clear = QToolButton()
        clear.setText("대화 지우기")
        clear.clicked.connect(self.clear_chat)
        self.copy_button = QToolButton()
        self.copy_button.setText("답변 복사")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self.copy_last_answer)
        copy_menu = QMenu(self.copy_button)
        copy_conversation = copy_menu.addAction("전체 대화 복사")
        copy_conversation.triggered.connect(self.copy_conversation)
        self.copy_button.setMenu(copy_menu)
        self.copy_button.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.retry_button = QToolButton()
        self.retry_button.setText("재시도")
        self.retry_button.setToolTip("마지막 질문 다시 보내기")
        self.retry_button.setEnabled(False)
        self.retry_button.clicked.connect(self.retry_last_question)
        self.send_button = QPushButton("질문 보내기")
        self.send_button.setToolTip("질문 보내기 (⌘+Enter)")
        self.send_button.clicked.connect(self.send_question)
        row.addWidget(clear)
        row.addWidget(self.copy_button)
        row.addWidget(self.retry_button)
        row.addStretch(1)
        row.addWidget(self.send_button)
        layout.addLayout(row)
        self.initial_question.submit_requested.connect(self.send_question)
        self.question.submit_requested.connect(self.send_question)
        return page

    def _build_edit_tab(self) -> QWidget:
        page = QWidget()
        layout = QVBoxLayout(page)
        help_text = QLabel("AI 수정안을 만든 뒤 필드별로 검토하고 선택해서 적용합니다.")
        help_text.setWordWrap(True)
        layout.addWidget(help_text)
        self.edit_templates = QComboBox()
        self.edit_templates.currentIndexChanged.connect(self._select_edit_template)
        layout.addWidget(self.edit_templates)
        self.edit_prompt = SubmitTextEdit()
        self.edit_prompt.setPlaceholderText("어떻게 수정할지 입력…  (⌘+Enter로 생성)")
        self.edit_prompt.submit_requested.connect(self.request_edit)
        layout.addWidget(self.edit_prompt, 1)
        self.edit_button = QPushButton("수정안 만들기")
        self.edit_button.clicked.connect(self.request_edit)
        layout.addWidget(self.edit_button)
        layout.addStretch(1)
        return page

    def _setup_shortcuts(self, parent: QWidget) -> None:
        self._panel_shortcuts = []
        self.cancel_shortcut = QShortcut(QKeySequence("Escape"), parent)
        self.cancel_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.cancel_shortcut.activated.connect(self.cancel_request)
        self.cancel_shortcut.setEnabled(False)
        self._panel_shortcuts.append(self.cancel_shortcut)

        focus_shortcut = QShortcut(QKeySequence("Ctrl+L"), parent)
        focus_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        focus_shortcut.activated.connect(self.focus_active_input)
        self._panel_shortcuts.append(focus_shortcut)

    def focus_active_input(self) -> None:
        if self.tabs.currentIndex() == 1:
            self.edit_prompt.setFocus()
            return
        editor = self.question if self._conversation_started else self.initial_question
        editor.setFocus()

    def config(self) -> dict:
        return mw.addonManager.getConfig(__package__) or {}

    def save_config(self, config: dict) -> None:
        mw.addonManager.writeConfig(__package__, config)
        self.refresh_templates()

    def refresh_templates(self) -> None:
        templates = self.config().get("templates", [])
        self._populate_templates(self.ask_templates, templates, "ask")
        self._populate_templates(self.edit_templates, templates, "edit")

    def _populate_templates(self, combo: QComboBox, templates: list[dict], mode: str) -> None:
        combo.blockSignals(True)
        combo.clear()
        combo.addItem("템플릿 선택…", "")
        for item in templates:
            if item.get("mode") == mode:
                combo.addItem(str(item.get("name", "이름 없음")), str(item.get("prompt", "")))
        combo.setCurrentIndex(0)
        combo.blockSignals(False)

    def _select_ask_template(self, index: int) -> None:
        prompt = self.ask_templates.itemData(index)
        if prompt:
            editor = self.question if self._conversation_started else self.initial_question
            editor.setPlainText(prompt)
            editor.setFocus()

    def _select_edit_template(self, index: int) -> None:
        prompt = self.edit_templates.itemData(index)
        if prompt:
            self.edit_prompt.setPlainText(prompt)

    def on_card(self, card: Any) -> None:
        new_id = int(card.id)
        if new_id != self._card_id:
            if self._busy:
                self.cancel_request()
            self._save_current_session()
            self._card_id = new_id
            self._load_session(new_id)
        note = card.note()
        names = list(note.keys())
        preview = " · ".join(
            f"{name}: {self._plain_preview(note[name])}" for name in names[:2]
        )
        self.card_label.setText(preview or f"카드 {new_id}")
        if self.config().get("show_only_in_review", True):
            self.show()

    def on_state_change(self, new_state: str, _old_state: str) -> None:
        if self.config().get("show_only_in_review", True):
            self.setVisible(new_state == "review")

    def clear_chat(self) -> None:
        if self._busy:
            self.cancel_request()
        if self._card_id is not None:
            self._sessions.pop(self._card_id, None)
        self._history.clear()
        self._display_messages.clear()
        self._conversation_started = False
        self._last_answer = ""
        self._last_question = ""
        self._render_transcript()
        self.initial_question.clear()
        self.question.clear()
        self.question.hide()
        self.ask_stack.setCurrentWidget(self.initial_question)
        self.ask_templates.setCurrentIndex(0)
        self.copy_button.setEnabled(False)
        self.retry_button.setEnabled(False)

    def _save_current_session(self) -> None:
        if self._card_id is None or not self._conversation_started:
            return
        self._sessions[self._card_id] = {
            "history": [dict(item) for item in self._history],
            "display": [dict(item) for item in self._display_messages],
            "last_answer": self._last_answer,
            "last_question": self._last_question,
            "draft": self.question.toPlainText(),
        }
        self._sessions.move_to_end(self._card_id)
        while len(self._sessions) > 20:
            self._sessions.popitem(last=False)

    def _load_session(self, card_id: int) -> None:
        session = self._sessions.get(card_id)
        self.initial_question.clear()
        self.question.clear()
        self.ask_templates.setCurrentIndex(0)
        if not session:
            self._history = []
            self._display_messages = []
            self._conversation_started = False
            self._last_answer = ""
            self._last_question = ""
            self.ask_stack.setCurrentWidget(self.initial_question)
            self.question.hide()
            self.copy_button.setEnabled(False)
            self.retry_button.setEnabled(False)
            self._render_transcript()
            return
        self._sessions.move_to_end(card_id)
        self._history = [dict(item) for item in session.get("history", [])]
        self._display_messages = [dict(item) for item in session.get("display", [])]
        self._conversation_started = True
        self._last_answer = str(session.get("last_answer", ""))
        self._last_question = str(session.get("last_question", ""))
        self.question.setPlainText(str(session.get("draft", "")))
        self.ask_stack.setCurrentWidget(self.transcript)
        self.question.show()
        self.copy_button.setEnabled(bool(self._last_answer))
        self.retry_button.setEnabled(bool(self._last_question))
        self._render_transcript()

    def send_question(self) -> None:
        editor = self.question if self._conversation_started else self.initial_question
        prompt = editor.toPlainText().strip()
        if not prompt or not self._ensure_ready():
            return
        context = self._card_context()
        history = [dict(item) for item in self._history]
        input_items: list[dict[str, str]] = [
            {"role": "user", "content": "현재 카드:\n" + json.dumps(context, ensure_ascii=False)}
        ]
        input_items.extend(history)
        input_items.append({"role": "user", "content": prompt})
        self._last_question = prompt
        self._conversation_started = True
        self.ask_stack.setCurrentWidget(self.transcript)
        self.question.show()
        self._append_message("나", prompt, "#3b82f6")
        assistant_index = self._append_message("AI", "답변을 시작하는 중…", "#10b981")
        editor.clear()
        self.question.setFocus()
        request_card_id = self._card_id
        self._run_request(
            instructions=ASK_INSTRUCTIONS,
            input_items=input_items,
            status="답변 생성 중…",
            stream=True,
            on_delta=lambda delta: self._question_delta(
                request_card_id, assistant_index, delta
            ),
            on_success=lambda result: self._question_done(
                request_card_id, assistant_index, prompt, result
            ),
            on_error=lambda message: self._question_failed(
                request_card_id, assistant_index, prompt, message
            ),
            on_cancel=lambda: self._question_cancelled(
                request_card_id, assistant_index, prompt
            ),
        )

    def _question_delta(
        self, request_card_id: int | None, message_index: int, delta: str
    ) -> None:
        if request_card_id != self._card_id:
            return
        current = self._display_messages[message_index]["text"]
        if current == "답변을 시작하는 중…":
            current = ""
        self._update_message(message_index, current + delta)

    def _question_done(
        self,
        request_card_id: int | None,
        message_index: int,
        prompt: str,
        result: ResponseResult,
    ) -> None:
        if request_card_id != self._card_id:
            return
        self._history.append({"role": "user", "content": prompt})
        self._history.append({"role": "assistant", "content": result.text})
        self._last_answer = result.text
        self.copy_button.setEnabled(True)
        self._update_message(message_index, result.text)
        usage = f" · {result.total_tokens:,} 토큰" if result.total_tokens else ""
        self._set_status(f"답변 완료{usage}", error=False, temporary=True)

    def _question_failed(
        self,
        request_card_id: int | None,
        message_index: int,
        prompt: str,
        message: str,
    ) -> None:
        self._restore_question(request_card_id, prompt)
        if request_card_id == self._card_id:
            self._update_message(message_index, f"오류: {message}", speaker="오류", color="#ef4444")
        self._set_status(message, error=True)

    def _question_cancelled(
        self, request_card_id: int | None, message_index: int, prompt: str
    ) -> None:
        self._restore_question(request_card_id, prompt)
        if request_card_id == self._card_id:
            self._update_message(message_index, "응답 생성을 취소했습니다.", color="#9ca3af")

    def _restore_question(self, request_card_id: int | None, prompt: str) -> None:
        if request_card_id == self._card_id and not self.question.toPlainText().strip():
            self.question.setPlainText(prompt)
            self.question.setFocus()

    def copy_last_answer(self) -> None:
        if self._last_answer:
            QApplication.clipboard().setText(self._last_answer)
            self._set_status("마지막 AI 답변을 복사했습니다.", temporary=True)

    def copy_conversation(self) -> None:
        if not self._display_messages:
            return
        transcript = "\n\n".join(
            f"{message.get('speaker', '')}:\n{message.get('text', '')}"
            for message in self._display_messages
        )
        QApplication.clipboard().setText(transcript)
        self._set_status("전체 대화를 복사했습니다.", temporary=True)

    def retry_last_question(self) -> None:
        if not self._last_question or self._busy:
            return
        if (
            len(self._history) >= 2
            and self._history[-2].get("role") == "user"
            and self._history[-2].get("content") == self._last_question
            and self._history[-1].get("role") == "assistant"
        ):
            self._history = self._history[:-2]
        editor = self.question if self._conversation_started else self.initial_question
        editor.setPlainText(self._last_question)
        self.send_question()

    def request_edit(self) -> None:
        prompt = self.edit_prompt.toPlainText().strip()
        if not prompt or not self._ensure_ready():
            return
        context = self._card_context()
        input_items = [{
            "role": "user",
            "content": "현재 카드와 수정 지시:\n"
            + json.dumps({"card": context, "request": prompt}, ensure_ascii=False),
        }]
        request_card_id = self._card_id
        self._run_request(
            instructions=EDIT_INSTRUCTIONS,
            input_items=input_items,
            status="수정안 생성 중…",
            stream=False,
            on_success=lambda result: self._edit_done(request_card_id, result.text),
            on_error=lambda message: self._set_status(message, error=True),
        )

    def _edit_done(self, request_card_id: int | None, text: str) -> None:
        if request_card_id != self._card_id:
            self._show_error("요청 중 카드가 바뀌어 수정안을 열지 않았습니다.")
            return
        note = self._current_note()
        if note is None:
            return
        original = {name: note[name] for name in note.keys()}
        try:
            summary, updates = parse_edit_proposal(text, set(original))
        except OpenAIError as error:
            self._show_error(str(error))
            return
        dialog = EditPreviewDialog(self, summary, original, updates, self._apply_updates)
        self._keep_dialog(dialog)
        dialog.show()
        self._set_status("수정안을 만들었습니다. 내용을 검토해 주세요.", temporary=True)

    def _apply_updates(self, updates: dict[str, str]) -> None:
        note = self._current_note()
        if note is None:
            self._show_error("현재 카드가 바뀌었습니다. 수정안을 다시 만들어 주세요.")
            return
        note_id = int(note.id)

        def op(col):
            target = col.get_note(note_id)
            for name, value in updates.items():
                if name in target:
                    target[name] = value
            return col.update_note(target)

        def success(_changes) -> None:
            if mw.state == "review":
                # Keep the active Card object: replacing it resets reviewer-only
                # state such as timer_started and breaks the next answer action.
                mw.reviewer._redraw_current_card()
            QMessageBox.information(self, "Anki Assist", "카드 수정이 적용되었습니다. 실행 취소할 수 있습니다.")
            self._set_status("카드 수정이 적용되었습니다.", temporary=True)

        CollectionOp(parent=self, op=op).success(success).run_in_background()

    def _run_request(
        self,
        *,
        instructions: str,
        input_items: list[dict],
        status: str,
        stream: bool,
        on_success,
        on_error,
        on_delta=None,
        on_cancel=None,
    ) -> None:
        config = self.config()
        api_key = os.environ.get("OPENAI_API_KEY", "").strip() or str(config.get("api_key", "")).strip()
        model = str(config.get("model", "gpt-5-mini"))
        max_tokens = int(config.get("max_output_tokens", 1800))
        self._request_serial += 1
        request_serial = self._request_serial
        self._cancel_callback = on_cancel
        cancel_event = threading.Event()
        self._cancel_event = cancel_event
        self._set_busy(True, status)

        def task():
            if stream:
                return create_streaming_response(
                    api_key=api_key,
                    model=model,
                    instructions=instructions,
                    input_items=input_items,
                    max_output_tokens=max_tokens,
                    cancel_event=cancel_event,
                    on_delta=lambda delta: mw.taskman.run_on_main(
                        lambda: self._deliver_delta(request_serial, on_delta, delta)
                    ),
                )
            return create_response(
                api_key=api_key,
                model=model,
                instructions=instructions,
                input_items=input_items,
                max_output_tokens=max_tokens,
            )

        def done(future: Future) -> None:
            if request_serial != self._request_serial:
                return
            self._request_future = None
            self._cancel_event = None
            self._cancel_callback = None
            self._set_busy(False)
            try:
                result = future.result()
            except Exception as error:
                on_error(str(error))
                return
            on_success(result)

        self._request_future = mw.taskman.run_in_background(
            task, done, uses_collection=False
        )

    def _deliver_delta(self, request_serial: int, on_delta, delta: str) -> None:
        if request_serial == self._request_serial and on_delta:
            on_delta(delta)

    def cancel_request(self) -> None:
        if not self._busy:
            return
        self._request_serial += 1
        if self._cancel_event:
            self._cancel_event.set()
        if self._request_future:
            self._request_future.cancel()
        callback = self._cancel_callback
        self._request_future = None
        self._cancel_event = None
        self._cancel_callback = None
        self._set_busy(False)
        if callback:
            callback()
        self._set_status("요청을 취소했습니다.", temporary=True)

    def _ensure_ready(self) -> bool:
        if self._busy:
            return False
        if self._current_note() is None:
            self._show_error("먼저 리뷰 화면에서 카드를 열어 주세요.")
            return False
        config = self.config()
        if not (os.environ.get("OPENAI_API_KEY", "").strip() or str(config.get("api_key", "")).strip()):
            self.open_settings()
            return False
        return True

    def _current_note(self):
        if mw.state != "review" or not getattr(mw.reviewer, "card", None):
            return None
        card = mw.reviewer.card
        if self._card_id is not None and int(card.id) != self._card_id:
            return None
        return card.note()

    def _card_context(self) -> dict:
        card = mw.reviewer.card
        note = card.note()
        notetype = note.note_type()
        return {
            "card_id": int(card.id),
            "note_type": notetype.get("name", "") if notetype else "",
            "fields": {name: note[name] for name in note.keys()},
        }

    def _set_busy(self, busy: bool, status: str = "") -> None:
        self._busy = busy
        self.cancel_shortcut.setEnabled(busy)
        self.send_button.setEnabled(not busy)
        self.edit_button.setEnabled(not busy)
        self.retry_button.setEnabled(not busy and bool(self._last_question))
        self.send_button.setText("답변 생성 중…" if busy else "질문 보내기")
        self.edit_button.setText("수정안 생성 중…" if busy else "수정안 만들기")
        self.cancel_button.setVisible(busy)
        if busy:
            self._set_status(status)

    def _set_status(self, message: str, *, error: bool = False, temporary: bool = False) -> None:
        self._status_serial += 1
        status_serial = self._status_serial
        self.status_label.setText(message)
        self.status_label.setStyleSheet(
            "color: #ef4444; padding: 3px;" if error else "color: palette(mid); padding: 3px;"
        )
        self.status_label.setVisible(bool(message))
        if temporary and message:
            def clear_if_current() -> None:
                if status_serial == self._status_serial and not self._busy:
                    self.status_label.hide()

            from aqt.qt import QTimer

            QTimer.singleShot(2500, clear_if_current)

    def _append_message(self, speaker: str, text: str, color: str) -> int:
        self._display_messages.append(
            {"speaker": speaker, "text": text, "color": color}
        )
        self._render_transcript()
        return len(self._display_messages) - 1

    def _update_message(
        self,
        index: int,
        text: str,
        *,
        speaker: str | None = None,
        color: str | None = None,
    ) -> None:
        if not 0 <= index < len(self._display_messages):
            return
        message = self._display_messages[index]
        message["text"] = text
        if speaker is not None:
            message["speaker"] = speaker
        if color is not None:
            message["color"] = color
        self._render_transcript()

    def _render_transcript(self) -> None:
        blocks = []
        for message in self._display_messages:
            speaker = html.escape(message.get("speaker", ""))
            color = html.escape(message.get("color", "#9ca3af"), quote=True)
            body = safe_rich_text(message.get("text", ""))
            blocks.append(
                f'<div style="margin:8px 0"><b style="color:{color}">{speaker}</b><br>{body}</div>'
            )
        self.transcript.setHtml("".join(blocks))
        bar = self.transcript.verticalScrollBar()
        bar.setValue(bar.maximum())

    def _plain_preview(self, value: str) -> str:
        text = value.replace("<br>", " ").replace("<br />", " ")
        import re
        text = re.sub(r"<[^>]+>", "", text)
        text = html.unescape(text).strip()
        return text[:70] + ("…" if len(text) > 70 else "")

    def _show_error(self, message: str) -> None:
        QMessageBox.warning(self, "Anki Assist", message)

    def _keep_dialog(self, dialog: QWidget) -> None:
        self._dialogs.append(dialog)
        dialog.destroyed.connect(lambda: self._dialogs.remove(dialog) if dialog in self._dialogs else None)

    def open_settings(self) -> None:
        dialog = SettingsDialog(
            self,
            self.config(),
            self.save_config,
            environment_key_active=bool(os.environ.get("OPENAI_API_KEY", "").strip()),
        )
        self._keep_dialog(dialog)
        dialog.show()

    def open_templates(self) -> None:
        config = self.config()

        def save(templates: list[dict]) -> None:
            updated = dict(config)
            updated["templates"] = templates
            self.save_config(updated)

        dialog = TemplateDialog(self, config.get("templates", []), save)
        self._keep_dialog(dialog)
        dialog.show()


def setup() -> AssistDock:
    dock = AssistDock()
    dock.refresh_templates()
    gui_hooks.reviewer_did_show_question.append(dock.on_card)
    gui_hooks.reviewer_did_show_answer.append(dock.on_card)
    gui_hooks.state_did_change.append(dock.on_state_change)

    action = QAction("Anki Assist 사이드바", mw)
    action.setCheckable(True)
    action.setShortcut("Ctrl+Shift+A")
    action.toggled.connect(dock.setVisible)
    dock.visibilityChanged.connect(action.setChecked)
    mw.form.menuTools.addAction(action)
    mw.anki_assist_dock = dock
    return dock
