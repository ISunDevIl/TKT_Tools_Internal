import os
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, 
    QListWidget, QFileDialog, QMessageBox, QProgressBar, QTextEdit, 
    QGroupBox, QSplitter, QScrollArea
)
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QDragEnterEvent, QDropEvent
from PyPDF2 import PdfMerger


class PDFMergerTool(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("📎 TKT - Ghép File PDF")
        self.resize(900, 550)

        # === Toolbar ===
        toolbar = QHBoxLayout()
        self.add_button = QPushButton("➕ Thêm file")
        self.merge_button = QPushButton("📎 Ghép PDF")
        self.clear_button = QPushButton("🗑 Xoá danh sách")
        toolbar.addWidget(self.add_button)
        toolbar.addWidget(self.merge_button)
        toolbar.addWidget(self.clear_button)
        toolbar.addStretch()

        # === File list (trái) với ScrollArea ===
        self.file_list_widget = QWidget()
        self.file_list_layout = QVBoxLayout(self.file_list_widget)
        self.file_list_layout.setAlignment(Qt.AlignTop)

        self.file_list = QListWidget()
        self.file_list.setAcceptDrops(True)
        self.file_list_layout.addWidget(self.file_list)

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setWidget(self.file_list_widget)

        # === Right Panel ===
        right_panel = QVBoxLayout()
        self.up_button = QPushButton("⬆️ Di chuyển lên")
        self.down_button = QPushButton("⬇️ Di chuyển xuống")
        self.delete_button = QPushButton("❌ Xoá file")
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress.setAlignment(Qt.AlignCenter)

        # Log box
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(200)

        log_group = QGroupBox("📜 Nhật ký hoạt động")
        log_layout = QVBoxLayout()
        log_layout.addWidget(self.log_box)
        log_group.setLayout(log_layout)

        right_panel.addWidget(self.up_button)
        right_panel.addWidget(self.down_button)
        right_panel.addWidget(self.delete_button)
        right_panel.addStretch()
        right_panel.addWidget(self.progress)
        right_panel.addWidget(log_group)

        # === Nội dung chính ===
        content_layout = QHBoxLayout()
        content_layout.addWidget(self.scroll_area, 4)
        content_layout.addLayout(right_panel, 1)

        # === Main Layout ===
        main_layout = QVBoxLayout()
        main_layout.addLayout(toolbar)
        main_layout.addLayout(content_layout)
        self.setLayout(main_layout)

        # === Connect ===
        self.add_button.clicked.connect(self.add_files)
        self.clear_button.clicked.connect(self.clear_files)
        self.up_button.clicked.connect(self.move_up)
        self.down_button.clicked.connect(self.move_down)
        self.delete_button.clicked.connect(self.delete_selected)
        self.merge_button.clicked.connect(self.merge_files)

        self.file_list.keyPressEvent = self.keyPressEventOverride
        self.setAcceptDrops(True)
        self.log("Ứng dụng sẵn sàng.")

    # === Logging ===
    def log(self, msg):
        self.log_box.append(msg)

    # === Drag & Drop ===
    def dragEnterEvent(self, event: QDragEnterEvent):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event: QDropEvent):
        for url in event.mimeData().urls():
            file_path = url.toLocalFile()
            if file_path.lower().endswith(".pdf"):
                self.add_file_if_not_exists(file_path)

    def add_file_if_not_exists(self, file_path):
        current_files = [self.file_list.item(i).text() for i in range(self.file_list.count())]
        if file_path not in current_files:
            self.file_list.addItem(file_path)
            self.log(f"➕ Đã thêm file: {file_path}")

    def add_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Chọn các file PDF", "", "PDF Files (*.pdf)")
        for file in files:
            self.add_file_if_not_exists(file)

    def clear_files(self):
        self.file_list.clear()
        self.progress.setValue(0)
        self.log("🗑 Đã xoá toàn bộ danh sách.")

    def move_up(self):
        current_row = self.file_list.currentRow()
        if current_row > 0:
            current_item = self.file_list.takeItem(current_row)
            self.file_list.insertItem(current_row - 1, current_item)
            self.file_list.setCurrentRow(current_row - 1)
            self.log("⬆️ Di chuyển file lên.")

    def move_down(self):
        current_row = self.file_list.currentRow()
        if current_row < self.file_list.count() - 1:
            current_item = self.file_list.takeItem(current_row)
            self.file_list.insertItem(current_row + 1, current_item)
            self.file_list.setCurrentRow(current_row + 1)
            self.log("⬇️ Di chuyển file xuống.")

    def delete_selected(self):
        row = self.file_list.currentRow()
        if row != -1:
            file_name = self.file_list.item(row).text()
            self.file_list.takeItem(row)
            self.log(f"❌ Đã xoá: {file_name}")

    def keyPressEventOverride(self, event):
        if event.key() == Qt.Key_Delete:
            self.delete_selected()
        else:
            QListWidget.keyPressEvent(self.file_list, event)

    def merge_files(self):
        count = self.file_list.count()
        if count == 0:
            QMessageBox.warning(self, "Lỗi", "Bạn chưa chọn file nào!")
            return
        if count < 2:
            QMessageBox.warning(self, "Lỗi", "Cần ít nhất 2 file để ghép!")
            return

        merger = PdfMerger()
        file_paths = [self.file_list.item(i).text() for i in range(count)]

        self.progress.setMaximum(count)
        self.progress.setValue(0)

        try:
            for i, file in enumerate(file_paths, 1):
                try:
                    merger.append(file)
                    self.log(f"📎 Đã thêm: {file}")
                except Exception as e:
                    QMessageBox.warning(self, "Lỗi", f"Không thể thêm file:\n{file}\n{e}")
                self.progress.setValue(i)

            base_name = os.path.splitext(os.path.basename(file_paths[0]))[0]
            folder_hint = os.path.dirname(file_paths[0])

            save_path, _ = QFileDialog.getSaveFileName(
                self,
                "Lưu file PDF đã ghép",
                os.path.join(folder_hint, f"{base_name}_merged.pdf"),
                "PDF Files (*.pdf)"
            )
            if save_path:
                merger.write(save_path)
                merger.close()
                self.progress.setValue(count)
                self.log(f"✅ Đã ghép và lưu file: {save_path}")
                QMessageBox.information(self, "Thành công", f"Đã lưu file:\n{save_path}")

        except Exception as e:
            QMessageBox.critical(self, "Lỗi", f"Đã xảy ra lỗi:\n{str(e)}")
            self.progress.setValue(0)
