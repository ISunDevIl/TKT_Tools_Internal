import sys
from PyQt5.QtWidgets import (
    QApplication, QWidget, QPushButton, QFileDialog,
    QListWidget, QVBoxLayout, QComboBox, QMessageBox,
    QLabel, QListWidgetItem, QGroupBox, QHBoxLayout,
    QTextEdit, QProgressBar, QSizePolicy
)
from PyQt5.QtGui import QColor, QFont
from PyPDF2 import PdfReader, PdfWriter

PAGE_SIZES = {
    'A0': (2383.94, 3370.39),
    'A1': (1683.78, 2383.94),
    'A2': (1190.55, 1683.78),
    'A3': (841.89, 1190.55),
    'A4': (595.28, 841.89),
    'A5': (419.53, 595.28),
    'A6': (297.64, 419.53),
}

# Convert point sang mm
def pt_to_mm(pt):
    return pt * 25.4 / 72

# Nhận diện khổ giấy gần nhất
def identify_paper_size(width_mm, height_mm):
    tolerance = 10  # mm
    for name, (w_pt, h_pt) in PAGE_SIZES.items():
        w_mm = pt_to_mm(w_pt)
        h_mm = pt_to_mm(h_pt)
        # check cả ngang và dọc
        if abs(width_mm - w_mm) < tolerance and abs(height_mm - h_mm) < tolerance:
            return name
        if abs(width_mm - h_mm) < tolerance and abs(height_mm - w_mm) < tolerance:
            return name + " ngang"
    return "không chuẩn"

class PDFResizer(QWidget):
    def __init__(self):
        super().__init__()
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("PDF Resizer - Thay đổi khổ giấy PDF")
        self.resize(850, 600)

        main_layout = QVBoxLayout()

        # Font + CSS đồng bộ
        font = QFont("Arial", 9)
        self.setFont(font)
        self.setStyleSheet("""
            QWidget { color: #000; font-family: Arial, sans-serif; }
            QPushButton {
                padding: 4px 8px;
                min-width: 90px;
                max-width: 120px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton#openBtn {
                background-color: #007bff;
                color: #fff;
            }
            QPushButton#openBtn:hover {
                background-color: #0056b3;
            }
            QPushButton#startBtn {
                background-color: #28a745;
                color: #fff;
            }
            QPushButton#startBtn:hover {
                background-color: #127329;
            }
            QPushButton#selectAllBtn {
                background-color: #17a2b8;
                color: #fff;
            }
            QPushButton#selectAllBtn:hover {
                background-color: #11707f;
            }
            QPushButton#clearAllBtn {
                background-color: #ffc107;
                color: #000;
            }
            QPushButton#clearAllBtn:hover {
                background-color: #cc9a06;
            }

        """)

        # --- Nhóm chọn file ---
        file_group = QGroupBox("File PDF")
        file_layout = QHBoxLayout()
        self.file_label = QLabel("Chưa chọn file")
        self.file_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.open_button = QPushButton("Chọn file PDF"); self.open_button.setObjectName("openBtn")
        self.open_button.clicked.connect(self.open_file)
        file_layout.addWidget(self.file_label)
        file_layout.addWidget(self.open_button)
        file_group.setLayout(file_layout)
        main_layout.addWidget(file_group)

        # --- Nhóm danh sách trang ---
        list_group = QGroupBox("Danh sách trang PDF")
        list_layout = QVBoxLayout()
        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QListWidget.MultiSelection)
        list_layout.addWidget(self.list_widget)
        list_group.setLayout(list_layout)
        main_layout.addWidget(list_group)

        # --- Nút chọn trang ---
        select_layout = QHBoxLayout()
        select_layout.addStretch()  # đẩy nút sang phải
        self.select_all_btn = QPushButton("Chọn tất cả")
        self.select_all_btn.setObjectName("selectAllBtn")
        self.clear_all_btn = QPushButton("Bỏ chọn tất cả")
        self.clear_all_btn.setObjectName("clearAllBtn")
        select_layout.addWidget(self.select_all_btn)
        select_layout.addWidget(self.clear_all_btn)
        main_layout.addLayout(select_layout)

        self.select_all_btn.clicked.connect(self.select_all_pages)
        self.clear_all_btn.clicked.connect(self.clear_all_pages)

        # --- Nhóm chọn khổ giấy ---
        size_group = QGroupBox("Khổ giấy mục tiêu")
        size_layout = QHBoxLayout()
        self.size_combo = QComboBox()
        self.size_combo.addItems(PAGE_SIZES.keys())
        size_layout.addWidget(QLabel("Chọn khổ:"))
        size_layout.addWidget(self.size_combo)
        self.start_button = QPushButton("Bắt đầu"); self.start_button.setObjectName("startBtn")
        self.start_button.clicked.connect(self.resize_pages)
        size_layout.addWidget(self.start_button)
        size_group.setLayout(size_layout)
        main_layout.addWidget(size_group)

        # --- Log ---
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFont(QFont("Consolas", 9))
        self.log_box.setMinimumHeight(120)
        main_layout.addWidget(self.log_box)

        # --- Tiến trình ---
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress_label = QLabel("Tiến trình: 0/0 trang")

        # Ẩn ban đầu
        self.progress.hide()
        self.progress_label.hide()

        main_layout.addWidget(self.progress)
        main_layout.addWidget(self.progress_label)

        self.setLayout(main_layout)

    # --- Hàm chọn tất cả ---
    def select_all_pages(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setSelected(True)

    # --- Hàm bỏ chọn tất cả ---
    def clear_all_pages(self):
        for i in range(self.list_widget.count()):
            item = self.list_widget.item(i)
            item.setSelected(False)

    def open_file(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Chọn file PDF", "", "PDF Files (*.pdf)"
        )
        if file_path:
            self.pdf_path = file_path
            self.reader = PdfReader(file_path)
            self.list_widget.clear()
            for i, page in enumerate(self.reader.pages):
                media_box = page.mediabox
                width_pt = float(media_box.width)
                height_pt = float(media_box.height)
                width_mm = pt_to_mm(width_pt)
                height_mm = pt_to_mm(height_pt)
                paper_name = identify_paper_size(width_mm, height_mm)
                item_text = f'Trang {i + 1} — {width_mm:.1f} x {height_mm:.1f} mm ({paper_name})'
                item = QListWidgetItem(item_text)
                if paper_name == "không chuẩn":
                    item.setForeground(QColor('red'))
                self.list_widget.addItem(item)
            self.file_label.setText(file_path)

    def resize_pages(self):
        selected_indexes = [i.row() for i in self.list_widget.selectedIndexes()]
        if not selected_indexes:
            QMessageBox.warning(self, "Cảnh báo", "Hãy chọn ít nhất 1 trang!")
            return

        # Hiện thanh tiến trình khi bắt đầu
        self.progress.show()
        self.progress_label.show()
        self.progress.setValue(0)
        self.progress_label.setText(f"Tiến trình: 0/{len(self.reader.pages)} trang")

        target_size = PAGE_SIZES[self.size_combo.currentText()]
        target_width, target_height = target_size

        save_path, _ = QFileDialog.getSaveFileName(
            self, "Chọn nơi lưu file", "", "PDF Files (*.pdf)"
        )
        if not save_path:
        # Ẩn lại nếu người dùng hủy
            self.progress.hide()
            self.progress_label.hide()
            return

        writer = PdfWriter()
        total_pages = len(self.reader.pages)
        processed = 0

        for i, page in enumerate(self.reader.pages):
            media_box = page.mediabox
            page_width = float(media_box.width)
            page_height = float(media_box.height)

            # giữ orientation (ngang/dọc)
            if page_width > page_height:
                width, height = max(target_width, target_height), min(target_width, target_height)
            else:
                width, height = min(target_width, target_height), max(target_width, target_height)

            if i in selected_indexes:
                page.scale_to(width, height)
                self.log_box.append(f"✔ File: {self.pdf_path}, Trang {i+1}: đổi về {self.size_combo.currentText()}")
            else:
                self.log_box.append(f"- File: {self.pdf_path}, Trang {i+1}: giữ nguyên")
            writer.add_page(page)

            processed += 1
            self.progress.setValue(int(processed / total_pages * 100))
            self.progress_label.setText(f"Tiến trình: {processed}/{total_pages} trang")

        with open(save_path, 'wb') as f:
            writer.write(f)

        QMessageBox.information(self, "Hoàn thành", f"Đã lưu file tại: {save_path}")
        # Sau khi người dùng bấm OK thì ẩn thanh tiến trình
        self.progress.hide()
        self.progress_label.hide()
