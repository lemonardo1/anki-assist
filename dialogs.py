from __future__ import annotations

from collections.abc import Callable

from aqt.qt import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    Qt,
)


class SettingsDialog(QDialog):
    def __init__(self, parent: QWidget, config: dict, on_save: Callable[[dict], None]):
        super().__init__(parent)
        self.setWindowTitle("Anki Assist 설정")
        self.setMinimumWidth(470)
        self._config = config
        self._on_save = on_save

        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.key = QLineEdit(str(config.get("api_key", "")))
        self.key.setEchoMode(QLineEdit.EchoMode.Password)
        self.key.setPlaceholderText("sk-proj-…")
        self.model = QLineEdit(str(config.get("model", "gpt-5-mini")))
        self.tokens = QSpinBox()
        self.tokens.setRange(128, 16000)
        self.tokens.setValue(int(config.get("max_output_tokens", 1800)))
        self.review_only = QCheckBox("리뷰 화면에서만 사이드바 표시")
        self.review_only.setChecked(bool(config.get("show_only_in_review", True)))
        form.addRow("OpenAI API 키", self.key)
        form.addRow("모델", self.model)
        form.addRow("최대 출력 토큰", self.tokens)
        form.addRow("표시", self.review_only)
        layout.addLayout(form)
        notice = QLabel("API 키는 Anki의 로컬 애드온 설정에 저장됩니다. 공유 컴퓨터에서는 사용하지 마세요.")
        notice.setWordWrap(True)
        layout.addWidget(notice)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self._save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _save(self) -> None:
        if not self.model.text().strip():
            QMessageBox.warning(self, "Anki Assist", "모델 이름을 입력해 주세요.")
            return
        updated = dict(self._config)
        updated.update(
            api_key=self.key.text().strip(),
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
        self.resize(720, 540)
        self._on_apply = on_apply
        self._editors: dict[str, tuple[QCheckBox, QPlainTextEdit]] = {}

        layout = QVBoxLayout(self)
        title = QLabel(summary)
        title.setTextFormat(Qt.TextFormat.PlainText)
        title.setWordWrap(True)
        layout.addWidget(title)
        for name, value in updates.items():
            enabled = QCheckBox(f"{name} 필드 적용")
            enabled.setChecked(True)
            layout.addWidget(enabled)
            before = QLabel(f"기존: {original.get(name, '')}")
            before.setTextFormat(Qt.TextFormat.PlainText)
            before.setWordWrap(True)
            before.setStyleSheet("color: palette(mid); padding-left: 6px;")
            layout.addWidget(before)
            edit = QPlainTextEdit(value)
            edit.setMinimumHeight(90)
            layout.addWidget(edit)
            self._editors[name] = (enabled, edit)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Save).setText("선택 필드 적용")
        buttons.accepted.connect(self._apply)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

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
