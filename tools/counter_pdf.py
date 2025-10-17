import sys
import os
import time
from PyQt5.QtWidgets import (
    QWidget, QPushButton, QLineEdit, QTextEdit, QVBoxLayout, QTableWidgetItem, QAbstractItemView,
    QHBoxLayout, QFileDialog, QLabel, QProgressBar, QMessageBox, QGroupBox, QSizePolicy, QTableWidget, QHeaderView)
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from PyQt5.QtGui import QFont
import pandas as pd
from PyPDF2 import PdfReader

A_SIZES = [
    ('A0', 841, 1189),
    ('A1', 594, 841),
    ('A2', 420, 594),
    ('A3', 297, 420),
    ('A4', 210, 297),
    ('A5', 148, 210),
]

def find_a_size(width_mm, height_mm):
    w, h = sorted([width_mm, height_mm])
    for i, (name, std_w, std_h) in enumerate(A_SIZES[::-1]):  # A5->A0
        tol_w = std_w * 1.15
        tol_h = std_h * 1.15
        if w <= tol_w and h <= tol_h:
            std_i = len(A_SIZES) - 1 - i
            if w > std_w * 1.15 or h > std_h * 1.15:
                if std_i > 0:
                    return A_SIZES[std_i - 1][0]
            return name
    return "Ngoài chuẩn"

def quydoi_a4(count_dict):
    quydoi = 0
    he_so = {"A0": 16, "A1": 8, "A2": 4, "A3": 2, "A4": 1, "A5": 1}
    for k, v in count_dict.items():
        if k in he_so:
            quydoi += he_so[k]*v
    return quydoi

class PDFCountWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int, int, dict, float) 
    done_signal = pyqtSignal(list)

    def __init__(self, folder):
        super().__init__()
        self.folder = folder
        self.is_running = True

    def run(self):
        files = []
        for root, dirs, fs in os.walk(self.folder):
            for file in fs:
                if file.lower().endswith('.pdf'):
                    files.append(os.path.join(root, file))

        total_files = len(files)
        files_done = 0
        total_pages = 0
        sum_dict = {"A0":0, "A1":0, "A2":0, "A3":0, "A4":0, "A5":0}
        result_data = []
        start_time = time.time()
        for idx, file_path in enumerate(files):
            if not self.is_running:
                break
            try:
                reader = PdfReader(file_path)
                size_list = []
                for page in reader.pages:
                    mb = page.mediabox
                    w = float(mb.width) * 25.4 / 72
                    h = float(mb.height) * 25.4 / 72
                    size = find_a_size(w, h)
                    size_list.append(size)
                a_counts = {k: size_list.count(k) for k in sum_dict}
                for k in sum_dict:
                    sum_dict[k] += a_counts[k]
                page_count = len(size_list)
                total_pages += page_count
                quydoi = quydoi_a4(a_counts)
                result_data.append([idx+1, file_path] + [a_counts[k] for k in sum_dict] + [quydoi])
                self.log_signal.emit(f"✔ Đã đếm: {os.path.basename(file_path)}")
            except Exception as e:
                result_data.append([idx+1, file_path] + [0]*6 + [0])
                self.log_signal.emit(f"✖ Lỗi: {os.path.basename(file_path)} - {e}")

            files_done += 1
            elapsed = time.time() - start_time
            avg_time = elapsed / (files_done if files_done > 0 else 1)
            est_remain = (total_files - files_done) * avg_time
            self.progress_signal.emit(files_done, total_files, total_pages, sum_dict.copy(), est_remain)
        self.done_signal.emit(result_data)

    def stop(self):
        self.is_running = False

class PDFCounter(QWidget):
    def __init__(self):
        super().__init__()
        self.result_data = []
        self.worker = None
        self.current_folder = ""
        self.init_ui()

    def init_ui(self):
        self.setWindowTitle("PDF Counter - Đếm khổ giấy PDF")
        self.resize(850, 500)

        layout = QVBoxLayout()

        font = QFont("Arial", 9)
        self.setFont(font)

        # --- Chọn thư mục ---
        folder_group = QGroupBox("Thư mục")
        folder_layout = QHBoxLayout()
        self.folder_label = QLabel("Chưa chọn thư mục")
        self.folder_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.select_btn = QPushButton("Chọn thư mục"); self.select_btn.setObjectName("selectBtn")
        folder_layout.addWidget(self.folder_label)
        folder_layout.addWidget(self.select_btn)
        folder_group.setLayout(folder_layout)
        layout.addWidget(folder_group)
        self.select_btn.clicked.connect(self.select_folder)

        # --- Nút chức năng ---
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.count_btn = QPushButton("Bắt đầu"); self.count_btn.setObjectName("countBtn")
        self.stop_btn = QPushButton("Dừng"); self.stop_btn.setObjectName("stopBtn")
        self.export_btn = QPushButton("Xuất Excel"); self.export_btn.setObjectName("exportBtn")

        # Style cho nút
        font = QFont("Arial", 9)
        self.setFont(font)
        self.setStyleSheet("""
            QWidget { color: #000; font-family: Arial, sans-serif; }
            QPushButton {
                padding: 4px 8px;
                min-width: 90px;
                max-width: 110px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton#selectBtn {
                background-color: #007bff;
                color: #fff;
            }
            QPushButton#selectBtn:hover {
                background-color: #0056b3;
            }
            QPushButton#countBtn {
                background-color: #28a745;
                color: #fff;
            }
            QPushButton#countBtn:hover {
                background-color: #127329;
            }
            QPushButton#stopBtn {
                background-color: #e03;
                color: #fff;
            }
            QPushButton#stopBtn:hover {
                background-color: #B9082C;
            }
            QPushButton#stopBtn:disabled {
                background-color: #cccccc;
                color: #666666;
            }

            QPushButton#exportBtn {
                background-color: #28a745;
                color: #fff;
            }
            QPushButton#exportBtn:hover {
                background-color: #127329;
            }
            QTableWidget {
                font-family: Arial, sans-serif;
                font-size: 9pt;
                gridline-color: #dcdcdc;
            }
            QHeaderView::section {
                background-color: #f8f9fa;
                font-size: 9pt;
                padding: 4px;
                border: none;
            }
        """)

        # Đặt width vừa đủ nội dung
        for btn in (self.count_btn, self.stop_btn, self.export_btn):
            btn.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.stop_btn.setEnabled(False)
        self.export_btn.setEnabled(False)
        btn_layout.addWidget(self.count_btn)
        btn_layout.addWidget(self.stop_btn)
        btn_layout.addWidget(self.export_btn)


        layout.addLayout(btn_layout)

        self.count_btn.clicked.connect(self.count_pages)
        self.stop_btn.clicked.connect(self.stop_count)
        self.export_btn.clicked.connect(self.export_excel)

        # --- Lọc file ---
        filter_layout = QHBoxLayout()
        filter_layout.addWidget(QLabel("Lọc file:"))
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Nhập từ khóa để lọc theo tên file…")
        self.filter_input.textChanged.connect(self.apply_filter)
        filter_layout.addWidget(self.filter_input)
        layout.addLayout(filter_layout)

        # --- Bảng kết quả ---
        self.result_table = QTableWidget()
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.setColumnCount(9)
        self.result_table.setHorizontalHeaderLabels(
            ["STT","File","A0","A1","A2","A3","A4","A5","A4 quy đổi"]
        )

        # Bật đường kẻ ô
        self.result_table.setShowGrid(True)
        self.result_table.setStyleSheet("""
            QTableWidget {
                gridline-color: #a0a0a0;
            }
            QHeaderView::section {
                border: 1px solid #dcdcdc;
                background-color: #f8f9fa;
                font-weight: bold;
                font-size: 9pt;
                padding: 4px;
            }
        """)

        # Cột "File" co giãn, cột khác tự động vừa nội dung
        header = self.result_table.horizontalHeader()
        header.setSectionResizeMode(1, QHeaderView.Stretch)
        for i in range(9):
            if i != 1:
                header.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        self.result_table.setSortingEnabled(True)
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        layout.addWidget(self.result_table)


        # --- Log ---
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFont(QFont("Consolas", 9))
        layout.addWidget(self.log_box)

        # --- Tiến trình ---
        self.progress = QProgressBar()
        self.progress.setValue(0)
        self.progress_label = QLabel("Đã đếm: 0/0 file | Ước tính còn lại: --")
        self.progress.hide()
        self.progress_label.hide()
        layout.addWidget(self.progress)
        layout.addWidget(self.progress_label)

        # --- Bộ đếm tổng ---
        self.counter_label = QLabel(
            "Kết quả đếm: | A0: 0 | A1: 0 | A2: 0 | A3: 0 | A4: 0 | A5: 0 | Tổng A4 quy đổi: 0"
        )
        self.counter_label.hide()
        layout.addWidget(self.counter_label)

        self.setLayout(layout)

    def select_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục chứa file PDF")
        if folder:
            self.folder_label.setText(folder)
            self.current_folder = folder

    def count_pages(self):
        folder = getattr(self, "current_folder", "").strip()
        if not os.path.isdir(folder):
            QMessageBox.warning(self, "Lỗi", "Vui lòng chọn đúng thư mục!")
            return

        self.log_box.clear()
        self.progress.show()
        self.progress_label.show()
        self.counter_label.show()
        self.progress.setValue(0)
        self.progress_label.setText("Đã đếm: 0/0 file | Ước tính còn lại: --")
        self.counter_label.setText(
            "Kết quả đếm: | A0: 0 | A1: 0 | A2: 0 | A3: 0 | A4: 0 | A5: 0 | Tổng A4 quy đổi: 0"
        )
        self.count_btn.setEnabled(False)
        self.stop_btn.setEnabled(True)
        self.export_btn.setEnabled(False)
        self.result_data.clear()
        self.result_table.setRowCount(0)

        self.worker = PDFCountWorker(folder)
        self.worker.log_signal.connect(self.update_log)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.done_signal.connect(self.on_done)
        self.worker.start()

    def stop_count(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.log_box.append("⏹ Đã dừng quá trình đếm.")
            self.stop_btn.setEnabled(False)
            self.count_btn.setEnabled(True)

    def on_done(self, data):
        self.result_data = data
        self.count_btn.setEnabled(True)
        self.stop_btn.setEnabled(False)
        self.export_btn.setEnabled(True)
        self.log_box.append("----- Đã hoàn thành đếm tất cả file PDF -----")

        # Ẩn progress bar + label khi xong
        self.progress.hide()
        self.progress_label.hide()

        self.result_table.setRowCount(0)
        for row_idx, row in enumerate(self.result_data):
            # row = [stt, file_path, A0, A1, A2, A3, A4, A5, quydoi]
            stt = row[0]
            file_path = row[1]
            a_counts = row[2:8]
            quydoi   = row[8]

            self.result_table.insertRow(row_idx)

            # --- Cột STT ---
            item_stt = QTableWidgetItem(str(stt))
            item_stt.setTextAlignment(Qt.AlignCenter)
            self.result_table.setItem(row_idx, 0, item_stt)

            # --- Cột file ---
            item_file = QTableWidgetItem(os.path.basename(file_path))
            item_file.setToolTip(file_path)
            self.result_table.setItem(row_idx, 1, item_file)

            # --- Các cột A0..A5 ---
            for i, val in enumerate(a_counts, start=2):
                item = QTableWidgetItem(str(val))
                item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                item.setData(Qt.EditRole, int(val))
                self.result_table.setItem(row_idx, i, item)

            # --- Cột Tổng A4 ---
            item_qd = QTableWidgetItem(str(quydoi))
            item_qd.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            item_qd.setData(Qt.EditRole, int(quydoi))
            self.result_table.setItem(row_idx, 8, item_qd)

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.worker.stop()
            self.worker.wait()
        event.accept()

    def update_log(self, text):
        self.log_box.append(text)

    def update_progress(self, files_done, total_files, total_pages, sum_dict, est_remain):
        self.progress.setMaximum(total_files)
        self.progress.setValue(files_done)
        self.progress_label.setText(
            f"Đã đếm: {files_done}/{total_files} file | Ước tính còn lại: {int(est_remain)} giây"
        )
        tong_quydoi = quydoi_a4(sum_dict)
        
        self.counter_label.setText(
            f"Kết quả đếm: "
            f"A0: {sum_dict['A0']} | A1: {sum_dict['A1']} | A2: {sum_dict['A2']} | "
            f"A3: {sum_dict['A3']} | A4: {sum_dict['A4']} | A5: {sum_dict['A5']} | "
            f"Tổng A4 quy đổi: {tong_quydoi}"
        )

    def export_excel(self):
        path, _ = QFileDialog.getSaveFileName(self, "Lưu kết quả", "", "Excel File (*.xlsx)")
        if not path:
            return
        columns = ["STT", "Đường dẫn File", "A0", "A1", "A2", "A3", "A4", "A5", "Tổng A4 Quy đổi"]
        df = pd.DataFrame(self.result_data, columns=columns)
        tong_a = df[["A0", "A1", "A2", "A3", "A4", "A5"]].sum()
        tong_quydoi = df["Tổng A4 Quy đổi"].sum()
        sum_row = pd.DataFrame([["Tổng", ""] + tong_a.tolist() + [tong_quydoi]], columns=columns)
        df = pd.concat([df, sum_row], ignore_index=True)
        df.to_excel(path, index=False)
        QMessageBox.information(self, "Hoàn tất", "Đã xuất kết quả ra Excel!")

    def apply_filter(self):
        text = self.filter_input.text().lower().strip()
        for r in range(self.result_table.rowCount()):
            file_item = self.result_table.item(r, 1)
            visible = (text in file_item.text().lower()) if file_item else True
            self.result_table.setRowHidden(r, not visible)
