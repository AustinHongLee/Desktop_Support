from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from launcher.ui.theme import preferences_stylesheet
from launcher.windows.context_menu_registry import (
    CUSTOM_CONTEXT_MENU_TARGETS,
    ContextMenuCreateRequest,
    ContextMenuEntry,
    ContextMenuTarget,
    create_context_menu_entry,
    default_pythonw_path,
    expected_context_menu_command,
    expected_file_lock_checker_command,
    expected_iso_workbench_command,
    expected_safe_cleanup_command,
    open_with_program_command,
    power_shell_here_command,
    run_script_command,
)


@dataclass(frozen=True)
class _ActionTemplate:
    id: str
    title: str
    default_label: str
    hint: str
    default_target_label: str = "檔案"
    needs_path: bool = False
    path_title: str = ""
    path_filter: str = "所有檔案 (*.*)"
    editable_command: bool = False


_TEMPLATES = (
    _ActionTemplate(
        "set_context",
        "送到工程工具列",
        "送到工程工具列",
        "把目前右鍵位置交給工具列，後續用工具列執行命令。",
        default_target_label="資料夾空白處",
    ),
    _ActionTemplate(
        "open_iso",
        "開啟 ISO PDF 命名工作台",
        "ISO PDF 命名",
        "設定目前位置後直接叫出 ISO PDF 工作台。",
        default_target_label="資料夾空白處",
    ),
    _ActionTemplate(
        "safe_cleanup",
        "安全清除工作台",
        "安全清除...",
        "針對右鍵目標產生多層清除計畫，可隔離檔案並列出登錄檔候選項。",
        default_target_label="檔案",
    ),
    _ActionTemplate(
        "file_lock_checker",
        "檔案佔用檢查器",
        "誰佔用這個檔案...",
        "針對右鍵目標列出正在佔用的程序，可定位、正常關閉或強制結束。",
        default_target_label="檔案",
    ),
    _ActionTemplate(
        "powershell_here",
        "在此開啟 PowerShell",
        "在此開啟 PowerShell",
        "從目前資料夾、檔案所在資料夾或磁碟位置開啟終端機。",
        default_target_label="資料夾空白處",
    ),
    _ActionTemplate(
        "open_program",
        "用指定程式開啟",
        "用指定程式開啟",
        "把右鍵選取路徑交給指定 exe，例如 Code、Cursor、PyCharm。",
        needs_path=True,
        path_title="選擇程式",
        path_filter="程式 (*.exe);;所有檔案 (*.*)",
    ),
    _ActionTemplate(
        "run_script",
        "執行腳本",
        "執行工程腳本",
        "把右鍵選取路徑交給 ps1、bat、cmd 或 py 腳本。",
        needs_path=True,
        path_title="選擇腳本",
        path_filter="腳本 (*.ps1 *.bat *.cmd *.py);;所有檔案 (*.*)",
    ),
    _ActionTemplate(
        "custom_command",
        "自訂命令",
        "自訂右鍵動作",
        "保留 {target} 佔位符，建立時會替換成 Windows 右鍵路徑參數。",
        editable_command=True,
    ),
)


class ContextMenuActionDialog(QDialog):
    def __init__(self, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.setWindowTitle("新增右鍵快速動作")
        self.setMinimumSize(660, 500)
        self._created_entry: ContextMenuEntry | None = None

        title = QLabel("新增右鍵快速動作")
        title.setObjectName("PreferenceTitle")
        hint = QLabel("用模板建立目前使用者 HKCU 的右鍵項目；不需要管理員權限，也不碰 COM shell extension。")
        hint.setObjectName("PreferenceHint")
        hint.setWordWrap(True)

        self._template_combo = QComboBox()
        for template in _TEMPLATES:
            self._template_combo.addItem(template.title, template.id)
        self._template_combo.currentIndexChanged.connect(self._refresh_template_state)

        self._target_combo = QComboBox()
        for target in CUSTOM_CONTEXT_MENU_TARGETS:
            self._target_combo.addItem(target.label, target.label)
        self._target_combo.currentIndexChanged.connect(self._refresh_command_preview)

        self._label = QLineEdit()
        self._label.setPlaceholderText("右鍵選單顯示名稱")
        self._shift_only = QCheckBox("只在 Shift + 右鍵時顯示")

        self._path_row = QWidget()
        path_layout = QHBoxLayout(self._path_row)
        path_layout.setContentsMargins(0, 0, 0, 0)
        path_layout.setSpacing(6)
        self._path = QLineEdit()
        self._path.setPlaceholderText("選擇程式或腳本")
        self._path.textChanged.connect(self._refresh_command_preview)
        browse_button = QPushButton("瀏覽...")
        browse_button.clicked.connect(self._browse_path)
        path_layout.addWidget(self._path, 1)
        path_layout.addWidget(browse_button)

        self._template_hint = QLabel()
        self._template_hint.setObjectName("PreferenceHint")
        self._template_hint.setWordWrap(True)

        self._command_preview = QPlainTextEdit()
        self._command_preview.setMinimumHeight(104)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignmentFlag.AlignRight)
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(10)
        form.addRow("模板", self._template_combo)
        form.addRow("出現位置", self._target_combo)
        form.addRow("顯示名稱", self._label)
        form.addRow("程式 / 腳本", self._path_row)
        form.addRow("顯示方式", self._shift_only)
        form.addRow("說明", self._template_hint)
        form.addRow("指令預覽", self._command_preview)

        create_button = QPushButton("建立右鍵項目")
        create_button.setDefault(True)
        create_button.clicked.connect(self._create_entry)
        cancel_button = QPushButton("取消")
        cancel_button.clicked.connect(self.reject)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        buttons.addWidget(cancel_button)
        buttons.addWidget(create_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addLayout(form, 1)
        layout.addLayout(buttons)

        self.setStyleSheet(preferences_stylesheet())
        self._refresh_template_state()

    @property
    def created_entry(self) -> ContextMenuEntry | None:
        return self._created_entry

    def build_request(self) -> ContextMenuCreateRequest:
        target = self._selected_target()
        command = self._command_preview.toPlainText().strip()
        if self._selected_template().id == "custom_command":
            command = command.replace("{target}", target.argument_token)
        icon = self._suggested_icon()
        return ContextMenuCreateRequest(
            label=self._label.text(),
            target=target,
            command=command,
            icon=icon,
            shift_only=self._shift_only.isChecked(),
        )

    def _refresh_template_state(self) -> None:
        template = self._selected_template()
        self._template_hint.setText(template.hint)
        self._path_row.setVisible(template.needs_path)
        self._set_target_by_label(template.default_target_label)
        if not self._label.text().strip() or self._label.text() in {item.default_label for item in _TEMPLATES}:
            self._label.setText(template.default_label)
        self._command_preview.setReadOnly(not template.editable_command)
        if template.editable_command:
            self._command_preview.setPlainText('你的命令.exe "{target}"')
            return
        self._refresh_command_preview()

    def _refresh_command_preview(self) -> None:
        template = self._selected_template()
        if template.editable_command:
            return
        try:
            command = self._render_command(template, self._selected_target())
        except ValueError as exc:
            command = f"尚未完成設定：{exc}"
        self._command_preview.blockSignals(True)
        self._command_preview.setPlainText(command)
        self._command_preview.blockSignals(False)

    def _browse_path(self) -> None:
        template = self._selected_template()
        file_path, _selected_filter = QFileDialog.getOpenFileName(
            self,
            template.path_title or "選擇檔案",
            str(Path.home()),
            template.path_filter,
        )
        if file_path:
            self._path.setText(file_path)

    def _create_entry(self) -> None:
        try:
            self._created_entry = create_context_menu_entry(self.build_request())
        except Exception as exc:
            QMessageBox.critical(self, "新增右鍵快速動作", str(exc))
            return
        self.accept()

    def _selected_template(self) -> _ActionTemplate:
        template_id = str(self._template_combo.currentData())
        for template in _TEMPLATES:
            if template.id == template_id:
                return template
        return _TEMPLATES[0]

    def _selected_target(self) -> ContextMenuTarget:
        label = str(self._target_combo.currentData())
        for target in CUSTOM_CONTEXT_MENU_TARGETS:
            if target.label == label:
                return target
        return CUSTOM_CONTEXT_MENU_TARGETS[0]

    def _set_target_by_label(self, label: str) -> None:
        for index in range(self._target_combo.count()):
            if self._target_combo.itemData(index) == label:
                self._target_combo.setCurrentIndex(index)
                return

    def _render_command(self, template: _ActionTemplate, target: ContextMenuTarget) -> str:
        pythonw = default_pythonw_path()
        if template.id == "set_context":
            return expected_context_menu_command(pythonw, target.argument_token)
        if template.id == "open_iso":
            return expected_iso_workbench_command(pythonw, target.argument_token)
        if template.id == "safe_cleanup":
            return expected_safe_cleanup_command(pythonw, target.argument_token)
        if template.id == "file_lock_checker":
            return expected_file_lock_checker_command(pythonw, target.argument_token)
        if template.id == "powershell_here":
            return power_shell_here_command(target)
        if template.id == "open_program":
            return open_with_program_command(self._path.text(), target.argument_token)
        if template.id == "run_script":
            return run_script_command(self._path.text(), target.argument_token)
        return '你的命令.exe "{target}"'

    def _suggested_icon(self) -> str:
        template = self._selected_template()
        if template.id in {"set_context", "open_iso", "safe_cleanup", "file_lock_checker"}:
            return str(default_pythonw_path())
        if template.id == "powershell_here":
            return "powershell.exe"
        if template.needs_path:
            return self._path.text().strip()
        return ""
