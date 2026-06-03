from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtWidgets import QStyle

from launcher.core.safe_cleanup import BLOCKED_LAYER, PROCESS_LAYER, REGISTRY_LAYER, REVIEW_LAYER, SAFE_LAYER, confidence_band

SAFETY_GUARANTEE_TEXT = "所有檔案會先移到隔離區，保留 30 天可還原。"


@dataclass(frozen=True)
class LayerLanguage:
    title: str
    subtitle: str
    tooltip: str
    color: str
    icon: QStyle.StandardPixmap


_LANGUAGES = {
    SAFE_LAYER: LayerLanguage(
        title="可安全清除",
        subtitle="高信心殘留，會先移到隔離區，30 天內可還原",
        tooltip="明確可歸屬且低後果的檔案、捷徑或暫存項目。",
        color="#047857",
        icon=QStyle.StandardPixmap.SP_DialogApplyButton,
    ),
    REVIEW_LAYER: LayerLanguage(
        title="建議你看一眼",
        subtitle="可能是殘留，也可能是你保留的資料，清前請確認",
        tooltip="關聯性足夠高而被列出，但不應在未確認前自動處理。",
        color="#b45309",
        icon=QStyle.StandardPixmap.SP_MessageBoxWarning,
    ),
    PROCESS_LAYER: LayerLanguage(
        title="正在使用中",
        subtitle="程式還開著；只會在你允許後嘗試正常關閉",
        tooltip="目標或相關檔案可能被程序佔用，清理前需要先關閉。",
        color="#0369a1",
        icon=QStyle.StandardPixmap.SP_ComputerIcon,
    ),
    REGISTRY_LAYER: LayerLanguage(
        title="Windows 設定殘留",
        subtitle="可能影響偏好、檔案關聯、授權或重裝判斷，需逐項確認",
        tooltip="HKCU 登錄值可備份後清理；HKLM / Installer 系統層只列出。",
        color="#be123c",
        icon=QStyle.StandardPixmap.SP_FileDialogDetailedView,
    ),
    BLOCKED_LAYER: LayerLanguage(
        title="系統層・只列出",
        subtitle="需要管理員與額外備份流程；此處不會清理",
        tooltip="系統層、HKLM 或 Windows Installer 相關項目，一般模式永遠不可勾選。",
        color="#475569",
        icon=QStyle.StandardPixmap.SP_MessageBoxWarning,
    ),
}


def language_for_layer(layer: str) -> LayerLanguage:
    return _LANGUAGES.get(
        layer,
        LayerLanguage(
            title=layer,
            subtitle="未分類項目",
            tooltip="此項目沒有對應的使用者語言。",
            color="#475569",
            icon=QStyle.StandardPixmap.SP_FileIcon,
        ),
    )


def confidence_label(confidence: float) -> str:
    band = confidence_band(confidence)
    if band == "high":
        return f"高信心 {int(confidence * 100)}%"
    if band == "medium":
        return f"中信心 {int(confidence * 100)}%"
    return f"弱關聯 {int(confidence * 100)}%"


def format_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{value:.1f} GB"
