"""Interactive Image Viewer with zoom, pan, and ROI selection.

This module provides a fullscreen image viewer dialog for examining
construction drawings with support for:
- Mouse wheel zoom
- Click-and-drag pan
- ROI (Region of Interest) selection with rubber band
- Navigation between multiple images
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Callable

from PySide6.QtWidgets import (
    QDialog,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFrame,
    QGraphicsView,
    QGraphicsScene,
    QGraphicsPixmapItem,
    QRubberBand,
    QWidget,
    QSizePolicy,
)
from PySide6.QtCore import Qt, QRectF, QPointF, QRect, QSize, Signal
from PySide6.QtGui import QPixmap, QPainter, QWheelEvent, QMouseEvent, QKeyEvent


@dataclass
class SelectedROI:
    """Represents a user-selected region of interest."""

    image_path: str
    x0: float  # Normalized 0.0-1.0
    y0: float
    x1: float
    y1: float


class ZoomableGraphicsView(QGraphicsView):
    """A QGraphicsView with zoom and pan support."""

    # Signal emitted when ROI selection is complete
    roi_selected = Signal(float, float, float, float)  # x0, y0, x1, y1

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setRenderHint(QPainter.Antialiasing)
        self.setRenderHint(QPainter.SmoothPixmapTransform)
        self.setDragMode(QGraphicsView.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self.setResizeAnchor(QGraphicsView.AnchorViewCenter)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAsNeeded)

        # Zoom settings
        self._zoom_factor = 1.0
        self._min_zoom = 0.1
        self._max_zoom = 10.0

        # ROI selection
        self._roi_mode = False
        self._rubber_band: Optional[QRubberBand] = None
        self._roi_origin: Optional[QPointF] = None

        # Image dimensions for normalization
        self._image_width = 0
        self._image_height = 0

    def set_roi_mode(self, enabled: bool) -> None:
        """Enable or disable ROI selection mode."""
        self._roi_mode = enabled
        if enabled:
            self.setDragMode(QGraphicsView.NoDrag)
            self.setCursor(Qt.CrossCursor)
        else:
            self.setDragMode(QGraphicsView.ScrollHandDrag)
            self.setCursor(Qt.ArrowCursor)

    def set_image_dimensions(self, width: int, height: int) -> None:
        """Set image dimensions for coordinate normalization."""
        self._image_width = width
        self._image_height = height

    def wheelEvent(self, event: QWheelEvent) -> None:
        """Handle mouse wheel for zooming."""
        if event.angleDelta().y() > 0:
            zoom_in_factor = 1.15
            self._zoom_factor *= zoom_in_factor
        else:
            zoom_out_factor = 1 / 1.15
            self._zoom_factor *= zoom_out_factor

        # Clamp zoom factor
        self._zoom_factor = max(self._min_zoom, min(self._max_zoom, self._zoom_factor))

        self.setTransform(
            self.transform().scale(
                1.15 if event.angleDelta().y() > 0 else 1 / 1.15,
                1.15 if event.angleDelta().y() > 0 else 1 / 1.15
            )
        )

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """Handle mouse press for ROI selection."""
        if self._roi_mode and event.button() == Qt.LeftButton:
            self._roi_origin = self.mapToScene(event.pos())
            if self._rubber_band is None:
                self._rubber_band = QRubberBand(QRubberBand.Rectangle, self)
            self._rubber_band.setGeometry(QRect(event.pos(), QSize()))
            self._rubber_band.show()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """Handle mouse move for ROI selection."""
        if self._roi_mode and self._rubber_band and self._roi_origin:
            rect = QRect(
                self.mapFromScene(self._roi_origin),
                event.pos()
            ).normalized()
            self._rubber_band.setGeometry(rect)
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """Handle mouse release for ROI selection."""
        if self._roi_mode and event.button() == Qt.LeftButton and self._roi_origin:
            end_point = self.mapToScene(event.pos())

            # Calculate normalized coordinates
            if self._image_width > 0 and self._image_height > 0:
                x0 = max(0.0, min(1.0, self._roi_origin.x() / self._image_width))
                y0 = max(0.0, min(1.0, self._roi_origin.y() / self._image_height))
                x1 = max(0.0, min(1.0, end_point.x() / self._image_width))
                y1 = max(0.0, min(1.0, end_point.y() / self._image_height))

                # Ensure x0 < x1 and y0 < y1
                if x0 > x1:
                    x0, x1 = x1, x0
                if y0 > y1:
                    y0, y1 = y1, y0

                # Only emit if area is significant (at least 1% of image)
                if (x1 - x0) > 0.01 and (y1 - y0) > 0.01:
                    self.roi_selected.emit(x0, y0, x1, y1)

            # Clean up
            if self._rubber_band:
                self._rubber_band.hide()
            self._roi_origin = None
        else:
            super().mouseReleaseEvent(event)

    def fit_in_view(self) -> None:
        """Fit the entire image in the view."""
        self.fitInView(self.sceneRect(), Qt.KeepAspectRatio)
        self._zoom_factor = 1.0

    def actual_size(self) -> None:
        """Show image at actual (100%) size."""
        self.resetTransform()
        self._zoom_factor = 1.0


class ImageViewer(QDialog):
    """Dialog for interactive image viewing with zoom, pan, and ROI selection."""

    # Signal emitted when user selects an ROI and confirms
    roi_confirmed = Signal(str, float, float, float, float)  # path, x0, y0, x1, y1

    def __init__(
        self,
        parent=None,
        image_paths: Optional[list[str]] = None,
        initial_index: int = 0,
        block_id: Optional[str] = None,
    ):
        """Initialize ImageViewer.

        Args:
            parent: Parent widget.
            image_paths: List of image file paths to display.
            initial_index: Index of image to show first.
            block_id: Optional block ID for context display.
        """
        super().__init__(parent)

        self.image_paths = image_paths or []
        self.current_index = initial_index
        self.block_id = block_id

        # Selected ROI (pending confirmation)
        self._pending_roi: Optional[tuple] = None

        self._setup_ui()
        self._load_current_image()

    def _setup_ui(self) -> None:
        """Set up the user interface."""
        self.setWindowTitle("Image Viewer")
        self.setMinimumSize(800, 600)
        self.resize(1200, 900)

        # Make dialog resizable and maximizable
        self.setWindowFlags(
            self.windowFlags()
            | Qt.WindowMaximizeButtonHint
            | Qt.WindowMinimizeButtonHint
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Toolbar
        toolbar = QFrame()
        toolbar.setObjectName("toolbar")
        toolbar.setStyleSheet("""
            #toolbar {
                background-color: #263238;
                border-bottom: 1px solid #37474f;
                padding: 8px;
            }
            QPushButton {
                background-color: #37474f;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #455a64;
            }
            QPushButton:pressed {
                background-color: #546e7a;
            }
            QPushButton:checked {
                background-color: #1976d2;
            }
            QLabel {
                color: white;
                font-size: 13px;
            }
        """)

        toolbar_layout = QHBoxLayout(toolbar)
        toolbar_layout.setContentsMargins(8, 4, 8, 4)

        # Navigation buttons
        self.btn_prev = QPushButton("<")
        self.btn_prev.setFixedWidth(40)
        self.btn_prev.clicked.connect(self._prev_image)

        self.btn_next = QPushButton(">")
        self.btn_next.setFixedWidth(40)
        self.btn_next.clicked.connect(self._next_image)

        self.label_counter = QLabel()
        self._update_counter()

        # View controls
        self.btn_fit = QPushButton("Fit")
        self.btn_fit.clicked.connect(self._fit_view)

        self.btn_actual = QPushButton("100%")
        self.btn_actual.clicked.connect(self._actual_size)

        # ROI selection
        self.btn_roi = QPushButton("Select ROI")
        self.btn_roi.setCheckable(True)
        self.btn_roi.toggled.connect(self._toggle_roi_mode)

        self.btn_send_roi = QPushButton("Send ROI")
        self.btn_send_roi.setEnabled(False)
        self.btn_send_roi.clicked.connect(self._confirm_roi)
        self.btn_send_roi.setStyleSheet("""
            QPushButton {
                background-color: #2e7d32;
            }
            QPushButton:hover {
                background-color: #388e3c;
            }
            QPushButton:disabled {
                background-color: #455a64;
                color: #78909c;
            }
        """)

        # Close button
        self.btn_close = QPushButton("Close")
        self.btn_close.clicked.connect(self.close)

        # Info label
        self.label_info = QLabel()

        # Add to toolbar
        toolbar_layout.addWidget(self.btn_prev)
        toolbar_layout.addWidget(self.label_counter)
        toolbar_layout.addWidget(self.btn_next)
        toolbar_layout.addSpacing(20)
        toolbar_layout.addWidget(self.btn_fit)
        toolbar_layout.addWidget(self.btn_actual)
        toolbar_layout.addSpacing(20)
        toolbar_layout.addWidget(self.btn_roi)
        toolbar_layout.addWidget(self.btn_send_roi)
        toolbar_layout.addStretch()
        toolbar_layout.addWidget(self.label_info)
        toolbar_layout.addSpacing(20)
        toolbar_layout.addWidget(self.btn_close)

        layout.addWidget(toolbar)

        # Graphics view
        self.scene = QGraphicsScene()
        self.view = ZoomableGraphicsView()
        self.view.setScene(self.scene)
        self.view.setStyleSheet("background-color: #1e1e1e;")
        self.view.roi_selected.connect(self._on_roi_selected)

        layout.addWidget(self.view)

        # ROI info bar (hidden by default)
        self.roi_bar = QFrame()
        self.roi_bar.setObjectName("roiBar")
        self.roi_bar.setStyleSheet("""
            #roiBar {
                background-color: #1565c0;
                padding: 8px;
            }
            QLabel {
                color: white;
                font-size: 13px;
            }
        """)
        self.roi_bar.setVisible(False)

        roi_layout = QHBoxLayout(self.roi_bar)
        self.label_roi = QLabel("ROI: not selected")
        self.btn_clear_roi = QPushButton("Clear")
        self.btn_clear_roi.setFixedWidth(60)
        self.btn_clear_roi.clicked.connect(self._clear_roi)

        roi_layout.addWidget(self.label_roi)
        roi_layout.addStretch()
        roi_layout.addWidget(self.btn_clear_roi)

        layout.addWidget(self.roi_bar)

    def _update_counter(self) -> None:
        """Update image counter label."""
        total = len(self.image_paths)
        if total == 0:
            self.label_counter.setText("0 / 0")
        else:
            self.label_counter.setText(f"{self.current_index + 1} / {total}")

        self.btn_prev.setEnabled(self.current_index > 0)
        self.btn_next.setEnabled(self.current_index < total - 1)

    def _load_current_image(self) -> None:
        """Load and display the current image."""
        self.scene.clear()

        if not self.image_paths or self.current_index >= len(self.image_paths):
            self.label_info.setText("No image")
            return

        path = self.image_paths[self.current_index]
        pixmap = QPixmap(path)

        if pixmap.isNull():
            self.label_info.setText(f"Failed to load: {Path(path).name}")
            return

        item = QGraphicsPixmapItem(pixmap)
        self.scene.addItem(item)
        self.scene.setSceneRect(QRectF(pixmap.rect()))

        # Update view with image dimensions
        self.view.set_image_dimensions(pixmap.width(), pixmap.height())

        # Fit image in view
        self.view.fit_in_view()

        # Update info
        filename = Path(path).name
        size_info = f"{pixmap.width()}x{pixmap.height()}"
        if self.block_id:
            self.label_info.setText(f"{self.block_id} | {filename} | {size_info}")
        else:
            self.label_info.setText(f"{filename} | {size_info}")

        self._update_counter()

    def _prev_image(self) -> None:
        """Go to previous image."""
        if self.current_index > 0:
            self.current_index -= 1
            self._load_current_image()
            self._clear_roi()

    def _next_image(self) -> None:
        """Go to next image."""
        if self.current_index < len(self.image_paths) - 1:
            self.current_index += 1
            self._load_current_image()
            self._clear_roi()

    def _fit_view(self) -> None:
        """Fit image in view."""
        self.view.fit_in_view()

    def _actual_size(self) -> None:
        """Show at 100% size."""
        self.view.actual_size()

    def _toggle_roi_mode(self, enabled: bool) -> None:
        """Toggle ROI selection mode."""
        self.view.set_roi_mode(enabled)
        if not enabled:
            self._clear_roi()

    def _on_roi_selected(self, x0: float, y0: float, x1: float, y1: float) -> None:
        """Handle ROI selection from view."""
        self._pending_roi = (x0, y0, x1, y1)
        self.btn_send_roi.setEnabled(True)
        self.roi_bar.setVisible(True)
        self.label_roi.setText(
            f"ROI: ({x0:.2%}, {y0:.2%}) - ({x1:.2%}, {y1:.2%})"
        )

    def _clear_roi(self) -> None:
        """Clear pending ROI selection."""
        self._pending_roi = None
        self.btn_send_roi.setEnabled(False)
        self.roi_bar.setVisible(False)
        self.label_roi.setText("ROI: not selected")

    def _confirm_roi(self) -> None:
        """Confirm and emit ROI selection."""
        if self._pending_roi and self.image_paths:
            path = self.image_paths[self.current_index]
            x0, y0, x1, y1 = self._pending_roi
            self.roi_confirmed.emit(path, x0, y0, x1, y1)
            self._clear_roi()
            self.btn_roi.setChecked(False)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle keyboard shortcuts."""
        if event.key() == Qt.Key_Left:
            self._prev_image()
        elif event.key() == Qt.Key_Right:
            self._next_image()
        elif event.key() == Qt.Key_F:
            self._fit_view()
        elif event.key() == Qt.Key_1:
            self._actual_size()
        elif event.key() == Qt.Key_R:
            self.btn_roi.toggle()
        elif event.key() == Qt.Key_Escape:
            if self.btn_roi.isChecked():
                self.btn_roi.setChecked(False)
            else:
                self.close()
        else:
            super().keyPressEvent(event)

    def get_selected_roi(self) -> Optional[SelectedROI]:
        """Get the currently selected ROI if any."""
        if self._pending_roi and self.image_paths:
            x0, y0, x1, y1 = self._pending_roi
            return SelectedROI(
                image_path=self.image_paths[self.current_index],
                x0=x0,
                y0=y0,
                x1=x1,
                y1=y1,
            )
        return None
