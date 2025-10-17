import sys
from pathlib import Path
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QMainWindow,
    QStackedWidget, QLabel, QHBoxLayout, QFrame,
    QSizePolicy, QSpacerItem, QGridLayout, QScrollArea
)
from PyQt5.QtCore import Qt, QTimer, QSize
from PyQt5.QtGui import QIcon

from tools.counter_files import Counter_File
from tools.counter_pdf import PDFCounter
from tools.pdf_resizer import PDFResizer
from tools.pdf_split import PDFSplitterApp
from tools.pdf_merger import PDFMergerTool
from tools.pdf_to_tiff import PDFtoTIFFApp
from responsive_helper import ResponsiveHelper

def rsrc_path(*parts):
    if hasattr(sys, "_MEIPASS"):
        base_path = Path(sys._MEIPASS)
    else:
        base_path = Path.cwd()
    return str(base_path.joinpath(*parts))

def asset_path(*more):
    return rsrc_path("assets", *more)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("TKT MULTIFORM")
        self.setMinimumSize(800, 400)
        self.setWindowIcon(QIcon(asset_path("logo.ico")))
        self.rh = None

        # ===== Khung chính =====
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # === [KHÔI PHỤC] Thanh menu ngang ===
        menu_frame = QFrame()
        menu_frame.setStyleSheet("QFrame { background:#ffffff; border-bottom:1px solid #ddd; }")
        menu_layout = QHBoxLayout(menu_frame)
        menu_layout.setContentsMargins(15, 8, 15, 8)
        menu_layout.setSpacing(14)
        menu_layout.addItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        main_layout.addWidget(menu_frame)

        # === [KHÔI PHỤC] Breadcrumb ===
        self.breadcrumb = QLabel()
        self.breadcrumb.setStyleSheet("font-size:16px; color:#444; padding:8px 12px;")
        self.breadcrumb.setTextFormat(Qt.RichText)
        self.breadcrumb.setOpenExternalLinks(False)
        self.breadcrumb.linkActivated.connect(self.on_breadcrumb_click)
        main_layout.addWidget(self.breadcrumb)

        # === Stack chính ===
        self.stack = QStackedWidget()
        main_layout.addWidget(self.stack)

        # === Trang home (bọc ScrollArea) ===
        self.home_container = QWidget()
        home_layout = QVBoxLayout(self.home_container)
        home_layout.setAlignment(Qt.AlignTop)
        home_layout.setContentsMargins(16, 12, 16, 12)

        self._grid_layout = QGridLayout()
        self._grid_layout.setHorizontalSpacing(16)
        self._grid_layout.setVerticalSpacing(16)
        home_layout.addLayout(self._grid_layout)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.NoFrame)
        self.scroll.setWidget(self.home_container)

        # [KHÔI PHỤC] Bọc scroll area trong một widget home riêng
        self.home = QWidget()
        wrapper_layout = QVBoxLayout(self.home)
        wrapper_layout.setContentsMargins(0, 0, 0, 0)
        wrapper_layout.addWidget(self.scroll)
        self.stack.addWidget(self.home)

        # === Nút tool ===
        tool_buttons = [
            ("Đếm file, thư mục", Counter_File, asset_path("icon", "file-and-folder.png")),
            ("Đếm Trang PDF", PDFCounter, asset_path("icon", "document.png")),
            ("Resize PDF", PDFResizer, asset_path("icon", "edition.png")),
            ("Tách PDF", PDFSplitterApp, asset_path("icon", "split.png")),
            ("Gộp PDF", PDFMergerTool, asset_path("icon", "merge.png")),
            ("PDF → TIFF", PDFtoTIFFApp, asset_path("icon", "convert.png")),
        ]

        self.tools = {}
        self._tool_btns = []
        for label, cls, icon_path in tool_buttons:
            btn = QPushButton(label)
            if icon_path:
                btn.setIcon(QIcon(icon_path))
                btn.setIconSize(QSize(48, 48))
            btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
            btn.setMinimumSize(320, 90)
            btn.setStyleSheet("""
                QPushButton {
                    padding: 16px; font-size: 22px; border: 1px solid #ccc;
                    border-radius: 10px; background: #f5f5f5;
                    color: #333; text-align: left;
                }
                QPushButton:hover { background:#e8e8e8; border:2px solid #000; }
                QPushButton:disabled { background:#eee; color:#aaa; border:1px solid #ddd; }
            """)

            instance = cls()
            # [KHÔI PHỤC] Bọc tool instance trong scroll area mà không có nút "Quay lại"
            page_scroll = QScrollArea()
            page_scroll.setWidgetResizable(True)
            page_scroll.setFrameShape(QFrame.NoFrame)
            page_scroll.setWidget(instance) # Đặt thẳng instance vào scroll
            self.stack.addWidget(page_scroll)

            btn.clicked.connect(lambda _, w=page_scroll, lbl=label: self.switch_page(w, lbl))
            self.tools[label] = (btn, page_scroll)
            self._tool_btns.append(btn)

        initial_cols = 3
        for i, btn in enumerate(self._tool_btns):
            self._grid_layout.addWidget(btn, i // initial_cols, i % initial_cols)

        # ===== ResponsiveHelper =====
        self.rh = ResponsiveHelper(parent=self, base_w=1200, base_h=700,
                                   breakpoints=((1920,4),(1400,3),(1000,3),(700,2),(0,1)))
        # Không cần register_header nữa vì helper đã được tinh gọn
        self.rh.register_grid(self.scroll, self.home_container, self._grid_layout, self._tool_btns)
        QTimer.singleShot(0, self.rh.force_apply)

        # Khởi động vào trang chủ và cập nhật breadcrumb
        self.switch_page(self.home)

    def showEvent(self, event):
        super().showEvent(event)
        self.showMaximized()
        if self.rh: self.rh.force_apply()

    def resizeEvent(self, e):
        super().resizeEvent(e)
        if self.rh: self.rh.schedule_apply()

    # [KHÔI PHỤC] Các hàm điều hướng
    def switch_page(self, widget, label=None):
        self.stack.setCurrentWidget(widget)
        if label:
            self.update_breadcrumb([(label, None)])
        else:
            self.update_breadcrumb()

    def update_breadcrumb(self, path=None):
        if not path:
            self.breadcrumb.setText("🏠 Trang chủ")
            return
        parts = ['<a href="home" style="text-decoration:none; color:black;">🏠 Trang chủ</a>']
        for label, link in path:
            if link:
                parts.append(f'<a href="{link}" style="text-decoration:none; color:black;">{label}</a>')
            else:
                parts.append(label)
        self.breadcrumb.setText(" → ".join(parts))

    def on_breadcrumb_click(self, link):
        if link == "home":
            self.switch_page(self.home)