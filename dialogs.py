from __future__ import annotations

from collections.abc import Callable

from aqt.qt import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    Qt,
)


class SettingsDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        config: dict,
        on_save: Callable[[dict], None],
        environment_key_active: bool = False,
    ):
        super().__init__(parent)
        self.setWindowTitle("Anki Assist 설정")
        self.setMinimumWidth(470)
        self._config = config
        self._on_save = on_save
        self._existing_key = str(config.get("api_key", ""))

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.key = QLineEdit()
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        if environment_key_active:
            self.key.setPlaceholderText("환경 변수 OPENAI_API_KEY 사용 중")
        elif self._existing_key:
            self.key.setPlaceholderText("저장된 키 있음 — 변경할 때만 입력")
        else:
            self.key.setPlaceholderText("sk-proj-…")
        self.clear_key = QCheckBox("저장된 로컬 API 키 삭제")
        self.clear_key.setEnabled(bool(self._existing_key))
        self.clear_key.toggled.connect(self._toggle_clear_key)
        self.key.textChanged.connect(self._key_changed)
        self.model = QLineEdit(str(config.get("model", "gpt-5-mini")))
        self.tokens = QSpinBox()
        self.tokens.setRange(128, 16000)
        self.tokens.setValue(int(config.get("max_output_tokens", 1800)))
        self.review_only = QCheckBox("리뷰 화면에서만 사이드바 표시")
        self.review_only.setChecked(bool(config.get("show_only_in_review", True)))
        form.addRow("OpenAI API 키", self.key)
        form.addRow("", self.clear_key)
        form.addRow("모델", self.model)
        form.addRow("최대 출력 토큰", self.tokens)
        form.addRow("표시", self.review_only)
        layout.addLayout(form)
        notice_text = (
            "OPENAI_API_KEY 환경 변수가 로컬 설정보다 우선 사용됩니다. "
            "아래에 새 키를 저장해도 환경 변수를 제거하기 전에는 사용되지 않습니다."
            if environment_key_active
            else "API 키는 Anki의 로컬 애드온 설정에 저장됩니다. 공유 컴퓨터에서는 사용하지 마세요."
        )
        notice = QLabel(notice_text)
        notice.setWordWrap(True)
        layout.addWidget(notice)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _toggle_clear_key(self, checked: bool) -> None:
        self.key.setEnabled(not checked)

    def _key_changed(self, text: str) -> None:
        if text and self.clear_key.isChecked():
            self.clear_key.setChecked(False)

    def _save(self) -> None:
        if not self.model.text().strip():
            QMessageBox.warning(self, "Anki Assist", "모델 이름을 입력해 주세요.")
            return
        entered_key = self.key.text().strip()
        if self.clear_key.isChecked():
            api_key = ""
        elif entered_key:
            api_key = entered_key
        else:
            api_key = self._existing_key
        updated = dict(self._config)
        updated.update(
            api_key=api_key,
            model=self.model.text().strip(),
            max_output_tokens=self.tokens.value(),
            show_only_in_review=self.review_only.isChecked(),
        )
        self._on_save(updated)
        self.accept()


class TemplateDialog(QDialog):
    def __init__(self, parent: QWidget, templates: list[dict], on_save: Callable[[list[dict]], None]):
        super().__init__(parent)
        self.setWindowTitle("프롬프트 템플릿")
        self.resize(650, 430)
        self._templates = [dict(item) for item in templates]
        self._on_save = on_save

        outer = QVBoxLayout(self)
        body = QHBoxLayout()
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        body.addWidget(self.list, 2)
        editor = QVBoxLayout()
        form = QFormLayout()
        self.name = QLineEdit()
        self.mode = QComboBox()
        self.mode.addItem("질문", "ask")
        self.mode.addItem("카드 수정", "edit")
        form.addRow("이름", self.name)
        form.addRow("용도", self.mode)
        editor.addLayout(form)
        self.prompt = QPlainTextEdit()
        self.prompt.setPlaceholderText("프롬프트 내용")
        editor.addWidget(self.prompt, 1)
        row = QHBoxLayout()
        add = QPushButton("새로 추가")
        update = QPushButton("선택 항목 저장")
        delete = QPushButton("삭제")
        add.clicked.connect(self._add)
        update.clicked.connect(self._update)
        delete.clicked.connect(self._delete)
        row.addWidget(add)
        row.addWidget(update)
        row.addWidget(delete)
        editor.addLayout(row)
        body.addLayout(editor, 4)
        outer.addLayout(body)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._finish)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)
        self.list.currentRowChanged.connect(self._load_row)
        self._refresh()

    def _refresh(self, row: int = 0) -> None:
        self.list.clear()
        for item in self._templates:
            kind = "질문" if item.get("mode") == "ask" else "수정"
            self.list.addItem(f"[{kind}] {item.get('name', '')}")
        if self._templates:
            self.list.setCurrentRow(max(0, min(row, len(self._templates) - 1)))
        else:
            self._clear_editor()

    def _load_row(self, row: int) -> None:
        if not 0 <= row < len(self._templates):
            return
        item = self._templates[row]
        self.name.setText(str(item.get("name", "")))
        self.prompt.setPlainText(str(item.get("prompt", "")))
        index = self.mode.findData(item.get("mode", "ask"))
        self.mode.setCurrentIndex(max(0, index))

    def _values(self) -> dict | None:
        name = self.name.text().strip()
        prompt = self.prompt.toPlainText().strip()
        if not name or not prompt:
            QMessageBox.warning(self, "Anki Assist", "이름과 프롬프트를 모두 입력해 주세요.")
            return None
        return {"name": name, "mode": self.mode.currentData(), "prompt": prompt}

    def _add(self) -> None:
        values = self._values()
        if values:
            self._templates.append(values)
            self._refresh(len(self._templates) - 1)

    def _update(self) -> None:
        row = self.list.currentRow()
        values = self._values()
        if values and row >= 0:
            self._templates[row] = values
            self._refresh(row)

    def _delete(self) -> None:
        row = self.list.currentRow()
        if row >= 0:
            del self._templates[row]
            self._refresh(max(0, row - 1))

    def _clear_editor(self) -> None:
        self.name.clear()
        self.prompt.clear()
        self.mode.setCurrentIndex(0)

    def _finish(self) -> None:
        self._on_save(self._templates)
        self.accept()


class EditPreviewDialog(QDialog):
    def __init__(
        self,
        parent: QWidget,
        summary: str,
        original: dict[str, str],
        updates: dict[str, str],
        on_apply: Callable[[dict[str, str]], None],
    ):
        super().__init__(parent)
        self.setWindowTitle("AI 수정안 미리보기")
        self.resize(820, 620)
        self._on_apply = on_apply
        self._editors: dict[str, tuple[QCheckBox, QPlainTextEdit]] = {}

        layout = QVBoxLayout(self)
        title = QLabel(summary)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        layout.addWidget(title)

        selection_row = QHBoxLayout()
        select_all = QPushButton("전체 선택")
        select_none = QPushButton("전체 해제")
        select_all.clicked.connect(lambda: self._set_all_checked(True))
        select_none.clicked.connect(lambda: self._set_all_checked(False))
        selection_row.addWidget(select_all)
        selection_row.addWidget(select_none)
        selection_row.addStretch(1)
        layout.addLayout(selection_row)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll_body = QWidget()
        scroll_layout = QVBoxLayout(scroll_body)
        for name, value in updates.items():
            group = QGroupBox(name)
            group_layout = QVBoxLayout(group)
            enabled = QCheckBox(f"{name} 필드 적용")
            enabled.setChecked(True)
            group_layout.addWidget(enabled)
            comparison = QHBoxLayout()
            before_column = QVBoxLayout()
            before_column.addWidget(QLabel("기존"))
            before = QPlainTextEdit(original.get(name, ""))
            before.setReadOnly(True)
            before.setMinimumHeight(110)
            before_column.addWidget(before)
            after_column = QVBoxLayout()
            after_column.addWidget(QLabel("AI 제안 — 적용 전 편집 가능"))
            edit = QPlainTextEdit(value)
            edit.setMinimumHeight(110)
            after_column.addWidget(edit)
            comparison.addLayout(before_column, 1)
            comparison.addLayout(after_column, 1)
            group_layout.addLayout(comparison)
            scroll_layout.addWidget(group)
            self._editors[name] = (enabled, edit)
        scroll_layout.addStretch(1)
        scroll.setWidget(scroll_body)
        layout.addWidget(scroll, 1)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("선택 필드 적용")
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _set_all_checked(self, checked: bool) -> None:
        for checkbox, _editor in self._editors.values():
            checkbox.setChecked(checked)

    def _apply(self) -> None:
        selected = {
            name: editor.toPlainText()
            for name, (checkbox, editor) in self._editors.items()
            if checkbox.isChecked()
        }
        if not selected:
            QMessageBox.information(self, "Anki Assist", "적용할 필드를 선택해 주세요.")
            return
        self._on_apply(selected)
        self.accept()
