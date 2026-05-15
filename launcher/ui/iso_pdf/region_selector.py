from __future__ import annotations

from PyQt6.QtCore import QRectF, Qt, pyqtSignal
from PyQt6.QtGui import QColor, QImage, QPainter, QPen
from PyQt6.QtWidgets import QWidget

from launcher.plugins.iso_tools.serial_vision import DEFAULT_SERIAL_REGION, SerialVisionRegion


class RegionSelector(QWidget):
    dragStarted = pyqtSignal()
    regionChanged = pyqtSignal(object)
    regionCommitted = pyqtSignal(object)

    def __init__(self) -> None:
        super().__init__()
        self.setObjectName("RegionSelector")
        self.setMinimumHeight(230)
        self.setMouseTracking(True)
        self._image: QImage | None = None
        self._region = DEFAULT_SERIAL_REGION
        self._drag_mode = ""
        self._drag_anchor: tuple[float, float] | None = None
        self._drag_start_region = DEFAULT_SERIAL_REGION

    def set_image(self, image: QImage) -> None:
        self._image = image
        self.update()

    def clear_image(self) -> None:
        self._image = None
        self.update()

    def set_region(self, region: SerialVisionRegion) -> None:
        self._region = _normalized_region(region)
        self.update()

    def paintEvent(self, _event) -> None:  # noqa: ANN001
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.fillRect(self.rect(), QColor("#f8fafc"))

        if self._image is None or self._image.isNull():
            painter.setPen(QColor("#627386"))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "尚未載入頁面")
            return

        image_rect = self._image_rect()
        painter.drawImage(image_rect, self._image)

        region_rect = self._region_rect(image_rect)
        painter.fillRect(region_rect, QColor(31, 111, 235, 42))
        pen = QPen(QColor("#1f6feb"), 2)
        painter.setPen(pen)
        painter.drawRect(region_rect)

        handle_size = 8.0
        painter.setBrush(QColor("#ffffff"))
        painter.setPen(QPen(QColor("#1f6feb"), 2))
        for point in (
            region_rect.topLeft(),
            region_rect.topRight(),
            region_rect.bottomLeft(),
            region_rect.bottomRight(),
        ):
            painter.drawRect(QRectF(point.x() - handle_size / 2, point.y() - handle_size / 2, handle_size, handle_size))

    def mousePressEvent(self, event) -> None:  # noqa: ANN001
        if self._image is None or self._image.isNull():
            return
        normalized = self._point_to_normalized(event.position().x(), event.position().y())
        if normalized is None:
            return
        image_rect = self._image_rect()
        region_rect = self._region_rect(image_rect)
        self._drag_mode = self._hit_test(event.position().x(), event.position().y(), region_rect)
        self._drag_anchor = normalized
        self._drag_start_region = self._region
        if self._drag_mode == "create":
            x, y = normalized
            self._region = SerialVisionRegion(left=x, top=y, width=0.01, height=0.01)
        self.dragStarted.emit()
        self.update()

    def mouseMoveEvent(self, event) -> None:  # noqa: ANN001
        if not self._drag_mode or self._drag_anchor is None:
            return
        normalized = self._point_to_normalized(event.position().x(), event.position().y())
        if normalized is None:
            return
        self._region = self._region_from_drag(normalized)
        self.regionChanged.emit(self._region)
        self.update()

    def mouseReleaseEvent(self, _event) -> None:  # noqa: ANN001
        if not self._drag_mode:
            return
        self._drag_mode = ""
        self._drag_anchor = None
        self.regionCommitted.emit(self._region)

    def _image_rect(self) -> QRectF:
        if self._image is None or self._image.isNull():
            return QRectF()
        available_width = max(1, self.width() - 2)
        available_height = max(1, self.height() - 2)
        image_ratio = self._image.width() / max(1, self._image.height())
        available_ratio = available_width / available_height
        if image_ratio > available_ratio:
            width = available_width
            height = width / image_ratio
        else:
            height = available_height
            width = height * image_ratio
        left = (self.width() - width) / 2
        top = (self.height() - height) / 2
        return QRectF(left, top, width, height)

    def _region_rect(self, image_rect: QRectF) -> QRectF:
        return QRectF(
            image_rect.left() + image_rect.width() * self._region.left,
            image_rect.top() + image_rect.height() * self._region.top,
            image_rect.width() * self._region.width,
            image_rect.height() * self._region.height,
        )

    def _point_to_normalized(self, x: float, y: float) -> tuple[float, float] | None:
        image_rect = self._image_rect()
        if image_rect.isNull():
            return None
        x = _clamp_float(x, image_rect.left(), image_rect.right())
        y = _clamp_float(y, image_rect.top(), image_rect.bottom())
        return (
            (x - image_rect.left()) / max(1.0, image_rect.width()),
            (y - image_rect.top()) / max(1.0, image_rect.height()),
        )

    def _hit_test(self, x: float, y: float, region_rect: QRectF) -> str:
        handles = {
            "resize_tl": region_rect.topLeft(),
            "resize_tr": region_rect.topRight(),
            "resize_bl": region_rect.bottomLeft(),
            "resize_br": region_rect.bottomRight(),
        }
        for mode, point in handles.items():
            if abs(x - point.x()) <= 10 and abs(y - point.y()) <= 10:
                return mode
        if region_rect.contains(x, y):
            return "move"
        return "create"

    def _region_from_drag(self, normalized: tuple[float, float]) -> SerialVisionRegion:
        x, y = normalized
        start = self._drag_start_region
        anchor = self._drag_anchor or (start.left, start.top)
        if self._drag_mode == "move":
            dx = x - anchor[0]
            dy = y - anchor[1]
            return _normalized_region(
                SerialVisionRegion(
                    left=start.left + dx,
                    top=start.top + dy,
                    width=start.width,
                    height=start.height,
                )
            )
        if self._drag_mode == "resize_tl":
            return _region_from_edges(x, y, start.left + start.width, start.top + start.height)
        if self._drag_mode == "resize_tr":
            return _region_from_edges(start.left, y, x, start.top + start.height)
        if self._drag_mode == "resize_bl":
            return _region_from_edges(x, start.top, start.left + start.width, y)
        if self._drag_mode == "resize_br":
            return _region_from_edges(start.left, start.top, x, y)
        return _region_from_edges(anchor[0], anchor[1], x, y)


def _region_from_edges(left: float, top: float, right: float, bottom: float) -> SerialVisionRegion:
    min_left, max_left = sorted((left, right))
    min_top, max_top = sorted((top, bottom))
    return _normalized_region(
        SerialVisionRegion(
            left=min_left,
            top=min_top,
            width=max_left - min_left,
            height=max_top - min_top,
        )
    )


def _normalized_region(region: SerialVisionRegion) -> SerialVisionRegion:
    minimum_size = 0.025
    left = _clamp_float(region.left, 0.0, 1.0 - minimum_size)
    top = _clamp_float(region.top, 0.0, 1.0 - minimum_size)
    width = _clamp_float(region.width, minimum_size, 1.0 - left)
    height = _clamp_float(region.height, minimum_size, 1.0 - top)
    return SerialVisionRegion(left=left, top=top, width=width, height=height)


def _clamp_float(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))
