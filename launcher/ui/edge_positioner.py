from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ScreenArea:
    x: int
    y: int
    width: int
    height: int


@dataclass(frozen=True)
class DockPlacement:
    x: int
    y: int
    width: int
    height: int
    orientation: str


class EdgePositioner:
    VALID_EDGES = {"top", "bottom", "left", "right"}

    def compute(
        self,
        area: ScreenArea,
        *,
        edge: str,
        collapsed: bool,
        tail_offset: float = 0.5,
    ) -> DockPlacement:
        edge = self.normalize_edge(edge)
        orientation = "vertical" if edge in {"left", "right"} else "horizontal"
        if collapsed:
            width, height, x, y = self._collapsed_geometry(area, edge, tail_offset)
        else:
            width, height, x, y = self._expanded_geometry(area, edge)
        return DockPlacement(x=x, y=y, width=width, height=height, orientation=orientation)

    def nearest_edge(self, area: ScreenArea, point_x: int, point_y: int) -> str:
        distances = {
            "top": abs(point_y - area.y),
            "bottom": abs(point_y - (area.y + area.height)),
            "left": abs(point_x - area.x),
            "right": abs(point_x - (area.x + area.width)),
        }
        return min(distances, key=distances.get)

    def normalize_edge(self, edge: str) -> str:
        return edge if edge in self.VALID_EDGES else "top"

    def _expanded_geometry(self, area: ScreenArea, edge: str) -> tuple[int, int, int, int]:
        width = min(900, max(700, int(area.width * 0.72)))
        height = 40
        if edge in {"top", "bottom"}:
            width = area.width
            x = area.x
            y = area.y if edge == "top" else area.y + area.height - height
        elif edge == "left":
            width = 118
            height = area.height
            x = area.x
            y = area.y
        else:
            width = 118
            height = area.height
            x = area.x + area.width - width
            y = area.y
        return width, height, x, y

    def _collapsed_geometry(self, area: ScreenArea, edge: str, tail_offset: float) -> tuple[int, int, int, int]:
        offset = _clamp_offset(tail_offset)
        if edge in {"top", "bottom"}:
            width = 160
            height = 18
            x = area.x + round(max(0, area.width - width) * offset)
            y = area.y if edge == "top" else area.y + area.height - height
            return width, height, x, y
        width = 18
        height = 132
        x = area.x if edge == "left" else area.x + area.width - width
        y = area.y + round(max(0, area.height - height) * offset)
        return width, height, x, y


def screen_area_from_qrect(rect) -> ScreenArea:  # noqa: ANN001
    return ScreenArea(x=rect.x(), y=rect.y(), width=rect.width(), height=rect.height())


def _clamp_offset(offset: float) -> float:
    try:
        value = float(offset)
    except (TypeError, ValueError):
        return 0.5
    return min(max(value, 0.0), 1.0)
