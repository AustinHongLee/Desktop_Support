from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QSpinBox,
    QVBoxLayout,
)

from launcher.core.state_store import AppStateStore
from launcher.ui.theme import THEME_OPTIONS, preferences_stylesheet, theme_by_name


@dataclass(frozen=True)
class DockPreferences:
    edge: str
    screen_name: str | None
    auto_hide_enabled: bool
    auto_hide_delay_ms: int
    theme_name: str
    developer_mode: bool


class PreferencesDialog(QDialog):
    def __init__(
        self,
        state_store: AppStateStore,
        *,
        screen_names: list[str],
        parent=None,  # noqa: ANN001
    ) -> None:
        super().__init__(parent)
        self._state_store = state_store
        self._screen_names = screen_names

        self.setWindowTitle("偏好設定")
        self.setMinimumWidth(420)

        hint = QLabel("調整工具列常駐位置與收合行為。設定套用後會立即更新工具列。")
        hint.setObjectName("PreferenceHint")
        hint.setWordWrap(True)

        dock_group = QGroupBox("工具列")
        dock_form = QFormLayout(dock_group)
        dock_form.setContentsMargins(10, 12, 10, 10)
        dock_form.setHorizontalSpacing(12)
        dock_form.setVerticalSpacing(10)

        self._edge_combo = QComboBox()
        for edge, label in _EDGE_LABELS:
            self._edge_combo.addItem(label, edge)
        self._edge_combo.setCurrentIndex(max(0, self._edge_combo.findData(state_store.edge)))

        self._screen_combo = QComboBox()
        self._screen_combo.addItem("使用主螢幕 / 自動", None)
        for screen_name in screen_names:
            self._screen_combo.addItem(screen_name, screen_name)
        current_screen = state_store.screen_name
        if current_screen:
            index = self._screen_combo.findData(current_screen)
            if index < 0:
                self._screen_combo.addItem(f"{current_screen}（目前未連接）", current_screen)
                index = self._screen_combo.findData(current_screen)
            self._screen_combo.setCurrentIndex(index)

        self._auto_hide_check = QCheckBox("自動收合，只留尾巴")
        self._auto_hide_check.setChecked(state_store.auto_hide_enabled)

        self._delay_spin = QSpinBox()
        self._delay_spin.setRange(300, 10000)
        self._delay_spin.setSingleStep(100)
        self._delay_spin.setSuffix(" ms")
        self._delay_spin.setValue(state_store.auto_hide_delay_ms)
        self._delay_spin.setEnabled(state_store.auto_hide_enabled)
        self._auto_hide_check.toggled.connect(self._delay_spin.setEnabled)

        dock_form.addRow("停靠位置", self._edge_combo)
        dock_form.addRow("目標螢幕", self._screen_combo)
        dock_form.addRow("收合模式", self._auto_hide_check)
        dock_form.addRow("收合延遲", self._delay_spin)

        theme_group = QGroupBox("介面")
        theme_form = QFormLayout(theme_group)
        theme_form.setContentsMargins(10, 12, 10, 10)
        theme_form.setHorizontalSpacing(12)
        theme_form.setVerticalSpacing(10)

        self._theme_combo = QComboBox()
        for theme_name, label in THEME_OPTIONS:
            self._theme_combo.addItem(label, theme_name)
        self._theme_combo.setCurrentIndex(max(0, self._theme_combo.findData(state_store.theme_name)))
        self._theme_combo.currentIndexChanged.connect(self._apply_selected_theme)
        theme_form.addRow("主題", self._theme_combo)

        self._developer_mode_check = QCheckBox("顯示開發者測試指令")
        self._developer_mode_check.setChecked(state_store.developer_mode)
        theme_form.addRow("開發者模式", self._developer_mode_check)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("套用")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(hint)
        layout.addWidget(dock_group)
        layout.addWidget(theme_group)
        layout.addWidget(buttons)

        self._apply_selected_theme()

    def preferences(self) -> DockPreferences:
        return DockPreferences(
            edge=str(self._edge_combo.currentData()),
            screen_name=self._screen_combo.currentData(),
            auto_hide_enabled=self._auto_hide_check.isChecked(),
            auto_hide_delay_ms=self._delay_spin.value(),
            theme_name=str(self._theme_combo.currentData()),
            developer_mode=self._developer_mode_check.isChecked(),
        )

    def _apply_selected_theme(self) -> None:
        self.setStyleSheet(preferences_stylesheet(theme_by_name(str(self._theme_combo.currentData()))))


_EDGE_LABELS = (
    ("top", "貼上方"),
    ("bottom", "貼下方"),
    ("left", "貼左側"),
    ("right", "貼右側"),
)
