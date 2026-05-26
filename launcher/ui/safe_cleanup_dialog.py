from __future__ import annotations

from pathlib import Path

from PyQt6.QtCore import Qt
from PyQt6.QtGui import QBrush, QColor, QIcon
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QStyle,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
)

from launcher.core.context_model import LauncherContext
from launcher.core.safe_cleanup import (
    BLOCKED_LAYER,
    REGISTRY_LAYER,
    REVIEW_LAYER,
    SAFE_LAYER,
    CleanupPlan,
    CleanupPlanItem,
    apply_cleanup_plan,
    build_cleanup_plan,
)
from launcher.ui.theme import preferences_stylesheet


class SafeCleanupDialog(QDialog):
    def __init__(self, context: LauncherContext, parent=None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self._context = context
        self._plan: CleanupPlan = build_cleanup_plan(context)
        self._item_by_id: dict[str, CleanupPlanItem] = {}

        self.setWindowTitle("安全清除工作台")
        self.setMinimumSize(980, 650)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

        title = QLabel("安全清除工作台")
        title.setObjectName("PreferenceTitle")
        hint = QLabel("先產生清除計畫，再用分層、圖示與註解判斷是否執行。預設只移到隔離區，不直接永久刪除。")
        hint.setObjectName("PreferenceHint")
        hint.setWordWrap(True)

        self._summary = QLabel()
        self._summary.setObjectName("PreferenceHint")
        self._target_label = QLabel()
        self._target_label.setObjectName("PreferenceHint")
        self._target_label.setWordWrap(True)

        self._tree = QTreeWidget()
        self._tree.setColumnCount(5)
        self._tree.setHeaderLabels(["套用", "項目", "動作", "判斷註解", "位置 / 登錄檔"])
        self._tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self._tree.itemSelectionChanged.connect(self._update_detail)
        self._tree.itemChanged.connect(self._on_item_changed)

        self._detail = QPlainTextEdit()
        self._detail.setReadOnly(True)
        self._detail.setMinimumHeight(110)

        self._include_review = QCheckBox("允許執行需確認層")
        self._include_review.setToolTip("資料夾與疑似衍生檔需要人工確認才可加入隔離。")
        self._include_review.stateChanged.connect(lambda _state: self._refresh_item_flags())
        self._include_registry = QCheckBox("允許登錄檔 HKCU 清理")
        self._include_registry.setToolTip("只允許刪除 HKCU 值；HKLM / 系統層只列出。")
        self._include_registry.stateChanged.connect(lambda _state: self._refresh_item_flags())
        self._system_guard = QCheckBox("我確認沒有勾選系統保護路徑")
        self._system_guard.setToolTip("系統保護路徑仍不會執行；這個確認用來避免使用者忽略 blocked 層警告。")

        refresh_button = QPushButton("重新掃描")
        refresh_button.clicked.connect(self.refresh_plan)
        apply_button = QPushButton("隔離 / 清理勾選項目")
        apply_button.setDefault(True)
        apply_button.clicked.connect(self.apply_selected)
        close_button = QPushButton("關閉")
        close_button.clicked.connect(self.accept)

        toggles = QHBoxLayout()
        toggles.addWidget(self._include_review)
        toggles.addWidget(self._include_registry)
        toggles.addWidget(self._system_guard)
        toggles.addStretch(1)

        buttons = QHBoxLayout()
        buttons.addWidget(refresh_button)
        buttons.addStretch(1)
        buttons.addWidget(apply_button)
        buttons.addWidget(close_button)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addWidget(self._target_label)
        layout.addWidget(self._summary)
        layout.addWidget(self._tree, 1)
        layout.addLayout(toggles)
        layout.addWidget(self._detail)
        layout.addLayout(buttons)

        self.setStyleSheet(preferences_stylesheet())
        self._populate()

    def refresh_plan(self) -> None:
        self._plan = build_cleanup_plan(self._context)
        self._populate()

    def apply_selected(self) -> None:
        selected_ids = self._selected_item_ids()
        if not selected_ids:
            QMessageBox.information(self, "安全清除工作台", "目前沒有勾選可執行項目。")
            return
        selected = [self._item_by_id[item_id] for item_id in selected_ids if item_id in self._item_by_id]
        registry_count = sum(1 for item in selected if item.layer == REGISTRY_LAYER)
        review_count = sum(1 for item in selected if item.layer == REVIEW_LAYER)
        blocked_count = sum(1 for item in selected if item.layer == BLOCKED_LAYER)
        if blocked_count:
            QMessageBox.warning(self, "安全清除工作台", "Blocked / 系統保護項目不可執行，請取消勾選。")
            return
        if review_count and not self._include_review.isChecked():
            QMessageBox.warning(self, "安全清除工作台", "需確認層尚未允許執行。")
            return
        if registry_count and not self._include_registry.isChecked():
            QMessageBox.warning(self, "安全清除工作台", "登錄檔 HKCU 清理尚未允許執行。")
            return
        if registry_count and not self._system_guard.isChecked():
            QMessageBox.warning(self, "安全清除工作台", "請先確認沒有勾選系統保護路徑。")
            return
        answer = QMessageBox.question(
            self,
            "確認安全清除",
            f"將處理 {len(selected)} 個項目。\n檔案/資料夾會移到隔離區；HKCU 登錄值會被刪除並寫入 manifest。\n確定執行？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        result = apply_cleanup_plan(self._plan, selected_ids, include_registry=self._include_registry.isChecked())
        lines = [
            f"隔離資料夾：{result.quarantine_dir}",
            f"Manifest：{result.manifest_path}",
            f"已隔離檔案/資料夾：{result.moved_count}",
            f"已刪 HKCU 登錄值：{result.registry_deleted_count}",
            f"已清工具列近期紀錄：{'是' if result.state_cleaned else '否'}",
        ]
        if result.errors:
            lines.append("")
            lines.extend(f"錯誤：{error}" for error in result.errors)
        self._detail.setPlainText("\n".join(lines))
        QMessageBox.information(self, "安全清除工作台", "\n".join(lines[:5]))
        self.refresh_plan()

    def _populate(self) -> None:
        self._tree.blockSignals(True)
        self._tree.clear()
        self._item_by_id = {item.id: item for item in self._plan.items}
        self._target_label.setText(_target_text(self._plan.targets))
        self._summary.setText(_summary_text(self._plan))
        for layer in (SAFE_LAYER, REVIEW_LAYER, REGISTRY_LAYER, BLOCKED_LAYER):
            layer_items = [item for item in self._plan.items if item.layer == layer]
            if not layer_items:
                continue
            group = QTreeWidgetItem([_layer_title(layer, len(layer_items)), "", "", "", ""])
            group.setIcon(0, self._layer_icon(layer))
            group.setFirstColumnSpanned(True)
            self._tree.addTopLevelItem(group)
            for item in layer_items:
                child = QTreeWidgetItem(["", item.label, item.action, item.note, _item_location(item)])
                child.setData(0, Qt.ItemDataRole.UserRole, item.id)
                child.setIcon(1, self._item_icon(item))
                child.setCheckState(0, Qt.CheckState.Checked if item.checked_default and item.executable else Qt.CheckState.Unchecked)
                _apply_row_style(child, item)
                group.addChild(child)
        self._tree.expandAll()
        self._tree.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.header().setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self._tree.header().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self._tree.header().setSectionResizeMode(4, QHeaderView.ResizeMode.Stretch)
        self._tree.blockSignals(False)
        self._refresh_item_flags()
        if self._tree.topLevelItemCount() > 0 and self._tree.topLevelItem(0).childCount() > 0:
            self._tree.setCurrentItem(self._tree.topLevelItem(0).child(0))

    def _refresh_item_flags(self) -> None:
        self._tree.blockSignals(True)
        for index in range(self._tree.topLevelItemCount()):
            group = self._tree.topLevelItem(index)
            for child_index in range(group.childCount()):
                child = group.child(child_index)
                item = self._item_by_id.get(str(child.data(0, Qt.ItemDataRole.UserRole)))
                if item is None:
                    continue
                enabled = item.executable
                if item.layer == REVIEW_LAYER:
                    enabled = enabled and self._include_review.isChecked()
                if item.layer == REGISTRY_LAYER:
                    enabled = enabled and self._include_registry.isChecked()
                flags = child.flags() | Qt.ItemFlag.ItemIsUserCheckable
                if enabled:
                    flags |= Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable
                else:
                    flags &= ~Qt.ItemFlag.ItemIsEnabled
                    child.setCheckState(0, Qt.CheckState.Unchecked)
                child.setFlags(flags)
        self._tree.blockSignals(False)

    def _on_item_changed(self, item: QTreeWidgetItem, column: int) -> None:
        if column != 0:
            return
        plan_item = self._item_by_id.get(str(item.data(0, Qt.ItemDataRole.UserRole)))
        if plan_item is None or plan_item.executable:
            return
        self._tree.blockSignals(True)
        item.setCheckState(0, Qt.CheckState.Unchecked)
        self._tree.blockSignals(False)

    def _selected_item_ids(self) -> set[str]:
        selected: set[str] = set()
        for index in range(self._tree.topLevelItemCount()):
            group = self._tree.topLevelItem(index)
            for child_index in range(group.childCount()):
                child = group.child(child_index)
                if child.checkState(0) == Qt.CheckState.Checked:
                    selected.add(str(child.data(0, Qt.ItemDataRole.UserRole)))
        return selected

    def _update_detail(self) -> None:
        current = self._tree.currentItem()
        if current is None:
            return
        item = self._item_by_id.get(str(current.data(0, Qt.ItemDataRole.UserRole)))
        if item is None:
            return
        lines = [
            f"項目：{item.label}",
            f"層級：{_layer_label(item.layer)}",
            f"類型：{item.kind}",
            f"動作：{item.action}",
            f"註解：{item.note}",
            f"可執行：{'是' if item.executable else '否'}",
        ]
        if item.path:
            lines.append(f"路徑：{item.path}")
            lines.append(f"大小：{_format_size(item.size_bytes)}")
        if item.registry_key:
            lines.append(f"登錄檔：{item.root_name}\\{item.registry_key}")
            lines.append(f"值：{item.registry_value_name or '(Default)'}")
            lines.append(f"內容：{item.registry_value_data}")
        self._detail.setPlainText("\n".join(lines))

    def _layer_icon(self, layer: str) -> QIcon:
        pixmap = {
            SAFE_LAYER: QStyle.StandardPixmap.SP_DialogApplyButton,
            REVIEW_LAYER: QStyle.StandardPixmap.SP_MessageBoxWarning,
            REGISTRY_LAYER: QStyle.StandardPixmap.SP_FileDialogDetailedView,
            BLOCKED_LAYER: QStyle.StandardPixmap.SP_MessageBoxCritical,
        }.get(layer, QStyle.StandardPixmap.SP_FileIcon)
        return self.style().standardIcon(pixmap)

    def _item_icon(self, item: CleanupPlanItem) -> QIcon:
        if item.layer == REGISTRY_LAYER:
            return self.style().standardIcon(QStyle.StandardPixmap.SP_FileDialogDetailedView)
        if item.kind.endswith("folder"):
            return self.style().standardIcon(QStyle.StandardPixmap.SP_DirIcon)
        if item.kind == "state_record":
            return self.style().standardIcon(QStyle.StandardPixmap.SP_DriveFDIcon)
        return self.style().standardIcon(QStyle.StandardPixmap.SP_FileIcon)


def _target_text(targets: tuple[Path, ...]) -> str:
    if not targets:
        return "目標：目前沒有檔案或資料夾"
    if len(targets) == 1:
        return f"目標：{targets[0]}"
    return f"目標：{len(targets)} 個項目，第一個為 {targets[0]}"


def _summary_text(plan: CleanupPlan) -> str:
    return (
        f"安全 {plan.count_by_layer(SAFE_LAYER)}｜"
        f"需確認 {plan.count_by_layer(REVIEW_LAYER)}｜"
        f"登錄檔 {plan.count_by_layer(REGISTRY_LAYER)}｜"
        f"Blocked {plan.count_by_layer(BLOCKED_LAYER)}｜"
        f"估計大小 {_format_size(plan.total_size_bytes)}"
    )


def _layer_title(layer: str, count: int) -> str:
    return f"{_layer_label(layer)} ({count})"


def _layer_label(layer: str) -> str:
    labels = {
        SAFE_LAYER: "安全可隔離",
        REVIEW_LAYER: "需要人工確認",
        REGISTRY_LAYER: "登錄檔 HKCU 高風險",
        BLOCKED_LAYER: "系統保護 / 不執行",
    }
    return labels.get(layer, layer)


def _item_location(item: CleanupPlanItem) -> str:
    if item.path:
        return item.path
    if item.registry_key:
        return f"{item.root_name}\\{item.registry_key}\\{item.registry_value_name or '(Default)'}"
    return ""


def _apply_row_style(row: QTreeWidgetItem, item: CleanupPlanItem) -> None:
    color = {
        SAFE_LAYER: "#155e36",
        REVIEW_LAYER: "#8a4b00",
        REGISTRY_LAYER: "#7c2d12",
        BLOCKED_LAYER: "#991b1b",
    }.get(item.layer, "#0c1320")
    for column in range(5):
        row.setForeground(column, QBrush(QColor(color)))


def _format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"
