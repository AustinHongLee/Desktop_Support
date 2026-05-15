from __future__ import annotations

from PyQt6.QtWidgets import QButtonGroup, QDialog, QDialogButtonBox, QGroupBox, QRadioButton, QVBoxLayout

from launcher.ui.theme import Theme, preferences_stylesheet


class CopySelectionOptionsDialog(QDialog):
    def __init__(self, *, parent=None, theme: Theme | None = None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.setWindowTitle("複製選取項目")
        mode_box, self._mode_group = _radio_group(
            "複製內容",
            (
                ("完整路徑", "path"),
                ("檔名", "name"),
                ("檔名不含副檔名", "basename"),
            ),
        )
        self._mode_group.button(0).setChecked(True)
        self._finish_layout(mode_box, theme=theme)

    def options(self) -> dict[str, str]:
        return {"mode": str(self._mode_group.checkedButton().property("value"))}

    @classmethod
    def default_options(cls) -> dict[str, str]:
        return {"mode": "path"}

    def _finish_layout(self, group: QGroupBox, *, theme: Theme | None) -> None:
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("執行")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(group)
        layout.addWidget(buttons)
        self.setStyleSheet(preferences_stylesheet(theme) if theme is not None else preferences_stylesheet())


class CopyFolderListingOptionsDialog(QDialog):
    def __init__(self, *, parent=None, theme: Theme | None = None) -> None:  # noqa: ANN001
        super().__init__(parent)
        self.setWindowTitle("複製資料夾清單")
        include_box, self._include_group = _radio_group(
            "範圍",
            (
                ("全部項目", "all"),
                ("只含檔案", "files"),
            ),
        )
        self._include_group.button(0).setChecked(True)
        mode_box, self._mode_group = _radio_group(
            "複製內容",
            (
                ("檔名 / 項目名稱", "name"),
                ("檔名不含副檔名", "basename"),
                ("完整路徑", "path"),
            ),
        )
        self._mode_group.button(0).setChecked(True)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("執行")
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)
        layout.addWidget(include_box)
        layout.addWidget(mode_box)
        layout.addWidget(buttons)
        self.setStyleSheet(preferences_stylesheet(theme) if theme is not None else preferences_stylesheet())

    def options(self) -> dict[str, str]:
        return {
            "include": str(self._include_group.checkedButton().property("value")),
            "mode": str(self._mode_group.checkedButton().property("value")),
        }

    @classmethod
    def default_options(cls) -> dict[str, str]:
        return {"include": "all", "mode": "name"}


def _radio_group(title: str, options: tuple[tuple[str, str], ...]) -> tuple[QGroupBox, QButtonGroup]:
    group = QButtonGroup()
    box = QGroupBox(title)
    layout = QVBoxLayout(box)
    layout.setContentsMargins(10, 12, 10, 10)
    layout.setSpacing(8)
    for index, (label, value) in enumerate(options):
        button = QRadioButton(label)
        button.setProperty("value", value)
        group.addButton(button, index)
        layout.addWidget(button)
    return box, group
