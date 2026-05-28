from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import QFileInfo, pyqtSignal
from PyQt6.QtWidgets import QFileIconProvider, QHBoxLayout, QLabel, QLineEdit, QPushButton, QVBoxLayout

from launcher.core.safe_cleanup import CleanupPlan
from launcher.ui.components.card import Card
from launcher.ui.safe_cleanup.risk_meter import RiskMeter


class TargetHeaderCard(Card):
    analyze_requested = pyqtSignal()
    refresh_requested = pyqtSignal()
    cancel_requested = pyqtSignal()
    one_click_requested = pyqtSignal()
    pick_app_requested = pyqtSignal()
    pick_file_requested = pyqtSignal()
    pick_folder_requested = pyqtSignal()

    def __init__(self, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent, padding=14)
        self._icon_provider = QFileIconProvider()

        top = QHBoxLayout()
        top.setContentsMargins(0, 0, 0, 0)
        top.setSpacing(12)

        self._icon = QLabel()
        self._icon.setFixedSize(30, 30)
        self._title = QLabel("安全清除工作台")
        self._title.setObjectName("H1")
        self._subtitle = QLabel("選一個目標開始分析。所有清除預設都會先進隔離區。")
        self._subtitle.setObjectName("Mono")
        self._subtitle.setWordWrap(True)

        title_box = QVBoxLayout()
        title_box.setContentsMargins(0, 0, 0, 0)
        title_box.setSpacing(3)
        title_box.addWidget(self._title)
        title_box.addWidget(self._subtitle)

        self._risk_meter = RiskMeter()

        self._one_click_button = QPushButton("一鍵安全清除")
        self._one_click_button.setObjectName("Primary")
        self._one_click_button.clicked.connect(self.one_click_requested)
        self._refresh_button = QPushButton("重新分析")
        self._refresh_button.setObjectName("Ghost")
        self._refresh_button.clicked.connect(self.refresh_requested)
        self._cancel_button = QPushButton("取消分析")
        self._cancel_button.setObjectName("Ghost")
        self._cancel_button.clicked.connect(self.cancel_requested)
        self._cancel_button.setEnabled(False)

        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(8)
        actions.addWidget(self._one_click_button)
        actions.addWidget(self._refresh_button)
        actions.addWidget(self._cancel_button)

        top.addWidget(self._icon)
        top.addLayout(title_box, 1)
        top.addWidget(self._risk_meter, 0)
        top.addLayout(actions)
        self.body().addLayout(top)

        target_row = QHBoxLayout()
        target_row.setContentsMargins(0, 0, 0, 0)
        target_row.setSpacing(8)
        self.target_path_edit = QLineEdit()
        self.target_path_edit.setPlaceholderText("可輸入舊 exe 路徑、資料夾路徑或產品名稱，例如 Tekla Structures 2026")
        self.target_path_edit.returnPressed.connect(self.analyze_requested)
        analyze_button = QPushButton("分析輸入")
        analyze_button.setObjectName("Ghost")
        analyze_button.clicked.connect(self.analyze_requested)
        app_button = QPushButton("選擇應用")
        app_button.setObjectName("Ghost")
        app_button.clicked.connect(self.pick_app_requested)
        file_button = QPushButton("選擇檔案")
        file_button.setObjectName("Ghost")
        file_button.clicked.connect(self.pick_file_requested)
        folder_button = QPushButton("選擇資料夾")
        folder_button.setObjectName("Ghost")
        folder_button.clicked.connect(self.pick_folder_requested)
        target_row.addWidget(QLabel("分析目標"))
        target_row.addWidget(self.target_path_edit, 1)
        target_row.addWidget(analyze_button)
        target_row.addWidget(app_button)
        target_row.addWidget(file_button)
        target_row.addWidget(folder_button)
        self.body().addLayout(target_row)

    def set_plan(self, plan: CleanupPlan) -> None:
        self.target_path_edit.setText(_target_path_text(plan.targets))
        self._risk_meter.set_plan(plan)
        if not plan.targets:
            self._title.setText("安全清除工作台")
            self._subtitle.setText("選一個目標開始分析。所有清除預設都會先進隔離區。")
            self._one_click_button.setEnabled(False)
            return
        target = plan.targets[0]
        self._title.setText(target.name or str(target))
        self._subtitle.setText(f"{target}｜{_path_type_text(target)}｜{_target_size_text(plan, target)}")
        icon = self._icon_provider.icon(QFileInfo(str(target)))
        if not icon.isNull():
            self._icon.setPixmap(icon.pixmap(32, 32))

    def set_one_click_enabled(self, enabled: bool) -> None:
        self._one_click_button.setEnabled(enabled)

    @property
    def refresh_button(self) -> QPushButton:
        return self._refresh_button

    @property
    def cancel_button(self) -> QPushButton:
        return self._cancel_button

    @property
    def one_click_button(self) -> QPushButton:
        return self._one_click_button

    def set_scanning(self, active: bool) -> None:
        self._cancel_button.setEnabled(active)
        self._refresh_button.setEnabled(not active)
        self._one_click_button.setEnabled(not active)

    def set_applying(self, active: bool) -> None:
        self._one_click_button.setEnabled(not active)
        self._refresh_button.setEnabled(not active)
        self._cancel_button.setEnabled(False)


def _target_path_text(targets: tuple[Path, ...]) -> str:
    if not targets:
        return ""
    if len(targets) == 1:
        return str(targets[0])
    return f"{len(targets)} 個項目，第一個為 {targets[0]}"


def _path_type_text(path: Path) -> str:
    if not path.exists():
        return "不存在"
    if path.is_dir():
        return "資料夾"
    suffix = path.suffix.upper().lstrip(".")
    return f"{suffix} 檔案" if suffix else "檔案"


def _target_size_text(plan: CleanupPlan, target: Path) -> str:
    item = next((entry for entry in plan.items if entry.path == str(target)), None)
    return _format_size(item.size_bytes) if item else "大小未知"


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"
