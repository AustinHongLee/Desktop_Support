from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from launcher.plugins.iso_tools.serial_vision import DEFAULT_SERIAL_REGION, SerialVisionRegion

DEFAULT_DRAWING_REGION = SerialVisionRegion(left=0.50, top=0.66, width=0.50, height=0.34)


@dataclass(frozen=True)
class IsoNamingProfile:
    serial_region: SerialVisionRegion = DEFAULT_SERIAL_REGION
    drawing_region: SerialVisionRegion = DEFAULT_DRAWING_REGION
    confidence_threshold: float = 0.70
    pattern: str = "{serial}--{line}.pdf"
    iso_list_path: Path | None = None
    sheet_name: str | None = None
    serial_col: int | None = None
    line_col: int | None = None

    @classmethod
    def from_payload(cls, payload: dict[str, Any] | None) -> "IsoNamingProfile":
        payload = payload or {}
        return cls(
            serial_region=_region_from_payload(payload.get("serial_region")),
            drawing_region=_region_from_payload(payload.get("drawing_region"), default=DEFAULT_DRAWING_REGION),
            confidence_threshold=_float_value(payload.get("confidence_threshold"), 0.70),
            pattern=str(payload.get("pattern") or "{serial}--{line}.pdf"),
            iso_list_path=_optional_path(payload.get("iso_list_path")),
            sheet_name=_optional_str(payload.get("sheet_name")),
            serial_col=_optional_int(payload.get("serial_col")),
            line_col=_optional_int(payload.get("line_col")),
        )

    def to_payload(self) -> dict[str, Any]:
        return {
            "serial_region": {
                "left": self.serial_region.left,
                "top": self.serial_region.top,
                "width": self.serial_region.width,
                "height": self.serial_region.height,
            },
            "drawing_region": {
                "left": self.drawing_region.left,
                "top": self.drawing_region.top,
                "width": self.drawing_region.width,
                "height": self.drawing_region.height,
            },
            "confidence_threshold": self.confidence_threshold,
            "pattern": self.pattern,
            "iso_list_path": str(self.iso_list_path) if self.iso_list_path else None,
            "sheet_name": self.sheet_name,
            "serial_col": self.serial_col,
            "line_col": self.line_col,
        }


def load_iso_naming_profile(state_store: Any, folder: Path) -> IsoNamingProfile | None:
    payload = state_store.iso_naming_profile(folder)
    return IsoNamingProfile.from_payload(payload) if payload else None


def save_iso_naming_profile(state_store: Any, folder: Path, profile: IsoNamingProfile) -> None:
    state_store.set_iso_naming_profile(folder, profile.to_payload())


def _region_from_payload(payload: Any, *, default: SerialVisionRegion = DEFAULT_SERIAL_REGION) -> SerialVisionRegion:
    if not isinstance(payload, dict):
        return default
    return SerialVisionRegion(
        left=_float_value(payload.get("left"), default.left),
        top=_float_value(payload.get("top"), default.top),
        width=_float_value(payload.get("width"), default.width),
        height=_float_value(payload.get("height"), default.height),
    )


def _float_value(value: Any, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _optional_path(value: Any) -> Path | None:
    text = _optional_str(value)
    return Path(text) if text else None


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
