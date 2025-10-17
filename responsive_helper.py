# responsive_helper.py
import math, re
from typing import Iterable, List, Optional, Sequence, Tuple
from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QWidget, QScrollArea, QGridLayout, QSizePolicy, QApplication, QLabel, QPushButton

class ResponsiveHelper:
    def __init__(self, parent: QWidget, base_w: int = 1200, base_h: int = 700,
                 breakpoints=((1920,4),(1400,3),(900,2),(0,1)),
                 compact_threshold=(1400,820), debounce_ms: int = 60):
        self.parent = parent
        self.base_w = base_w
        self.base_h = base_h
        self.breakpoints = tuple(sorted(breakpoints, key=lambda x: x[0], reverse=True))
        self.compact_threshold = compact_threshold
        self.title_label: Optional[QLabel] = None
        self.crumb_label: Optional[QLabel] = None
        self.clock_label: Optional[QLabel] = None
        self.scroll: Optional[QScrollArea] = None
        self.container: Optional[QWidget] = None
        self.grid: Optional[QGridLayout] = None
        self.buttons: List[QPushButton] = []
        self._last_sig = None
        self._resize_timer = QTimer(parent); self._resize_timer.setSingleShot(True)
        self._resize_timer.timeout.connect(self.apply)
        self._debounce_ms = debounce_ms

    def register_header(self, breadcrumb: Optional[QLabel]):
        self.crumb_label = breadcrumb

    def register_grid(self, scroll: QScrollArea, container: QWidget, grid_layout: QGridLayout, buttons: Iterable[QPushButton]):
        self.scroll = scroll; self.container = container; self.grid = grid_layout
        self.buttons = list(buttons)

    def schedule_apply(self):
        self._resize_timer.start(self._debounce_ms)

    def force_apply(self):
        self._last_sig = None
        self.apply()

    # --- scale helpers ---
    def _dpi_scale(self) -> float:
        screen = self.parent.windowHandle().screen() if self.parent.windowHandle() else None
        if screen is None: screen = QApplication.primaryScreen()
        dpi = screen.logicalDotsPerInch() if screen else 96
        return max(0.85, dpi / 96.0)
    def _w_scale(self) -> float:
        w = max(1, self.parent.width() or self.base_w)
        return max(0.6, min(1.8, w / float(self.base_w)))
    def _h_scale(self) -> float:
        h = max(1, self.parent.height() or self.base_h)
        return max(0.6, min(1.8, h / float(self.base_h)))
    def sp(self, pt: int) -> int:
        s = ((self._w_scale() + self._h_scale()) / 2.0) * self._dpi_scale()
        return max(9, int(pt * s))
    def _is_compact(self) -> bool:
        return (self.parent.width() <= self.compact_threshold[0]) or (self.parent.height() <= self.compact_threshold[1])

    # --- layout helpers ---
    def _calc_cols(self) -> int:
        w = max(1, self.parent.width())
        for min_w, cols in self.breakpoints:
            if w >= min_w: return cols
        return 1
    def _viewport_size(self) -> Tuple[int, int]:
        if self.scroll and self.scroll.viewport():
            vp = self.scroll.viewport()
            return max(1, vp.width()), max(1, vp.height())
        return max(1, self.parent.width()), max(1, self.parent.height())
    
    def _reflow_grid(self, cols: int):
        if not (self.grid and self.buttons): return
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w is not None:
                w.setParent(None)

        # Thêm lại theo số cột
        for i, w in enumerate(self.buttons):
            self.grid.addWidget(w, i // cols, i % cols)

        # Stretch đều cột/hàng
        for c in range(cols):
            self.grid.setColumnStretch(c, 1)

        rows = max(1, math.ceil(len(self.buttons) / float(cols)))
        for r in range(rows):
            self.grid.setRowStretch(r, 1)

    def apply(self):
        compact = self._is_compact()
        cols = self._calc_cols()

        # Nếu grid rỗng, bỏ cache để ép reflow
        if self.grid and self.grid.count() == 0:
            self._last_sig = None

        sig = (compact, cols, self.parent.width(), self.parent.height())
        if sig == self._last_sig: return
        self._last_sig = sig

        # Header
        if self.title_label:
            title_sz = 22 if compact else 26
            self.title_label.setStyleSheet(
                f"font-size:{self.sp(title_sz)}px; font-weight:bold; color:#333; font-family: Arial, sans-serif;")
        if self.crumb_label:
            crumb_sz = 14 if compact else 16
            self.crumb_label.setStyleSheet(
                f"font-size:{self.sp(crumb_sz)}px; color:#444; padding:6px 12px; font-family: Arial, sans-serif;")
        if self.clock_label:
            self.clock_label.setStyleSheet(
                f"font-size:{self.sp(12)}px; color:#666; padding:6px; font-family: Arial, sans-serif;")

        if not (self.grid and self.container and self.buttons): return

        # Reflow trước
        self._reflow_grid(cols)

        n = len(self.buttons)
        if not n: return
        rows = max(1, math.ceil(n / float(cols)))

        vp_w, vp_h = self._viewport_size()
        m = self.container.layout().contentsMargins()
        hspacing = self.grid.horizontalSpacing(); 
        if hspacing is None or hspacing < 0: hspacing = 12
        vspacing = self.grid.verticalSpacing(); 
        if vspacing is None or vspacing < 0: vspacing = 12

        avail_w = max(200, vp_w - (m.left() + m.right()))
        avail_h = max(200, vp_h - (m.top() + m.bottom()))
        per_col_w = (avail_w - (cols - 1) * hspacing) / float(cols)
        per_row_h = (avail_h - (rows - 1) * vspacing) / float(rows)

        base_font = 18 if compact else 22
        btn_font_px = self.sp(base_font)
        pad_v = max(6, int(10 * self._h_scale()))
        pad_h = max(8, int(14 * self._w_scale()))
        min_h = 72 if compact else 90
        max_h = 160 if compact else 200
        min_w = 240 if compact else 320

        for btn in self.buttons:
            if btn.property("_base_qss") is None:
                btn.setProperty("_base_qss", btn.styleSheet() or "")
            base_qss = btn.property("_base_qss") or ""
            # override có selector để giữ :hover/:disabled
            qss = f"""{base_qss}
QPushButton {{
  font-size:{btn_font_px}px;
  padding:{pad_v}px {pad_h}px;
}}
"""
            btn.setStyleSheet(qss)
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            btn.setMinimumWidth(min_w)
            btn.setMaximumWidth(max(200, int(per_col_w)))
            btn.setMinimumHeight(min_h)
            btn.setMaximumHeight(max_h)
