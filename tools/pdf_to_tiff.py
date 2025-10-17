import time
import io
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QLabel, QPushButton, QFileDialog,
    QProgressBar, QTextEdit, QHBoxLayout
)
from PyQt5.QtCore import QThread, pyqtSignal
from pathlib import Path
import fitz  # PyMuPDF
from PIL import Image
import datetime


class ConvertWorker(QThread):
    log_signal = pyqtSignal(str)
    progress_signal = pyqtSignal(int, int)
    time_remaining_signal = pyqtSignal(str)

    def __init__(self, input_folder, output_folder):
        super().__init__()
        self.input_folder = Path(input_folder)
        self.output_folder = Path(output_folder)
        self.start_time = None

    def run(self):
        all_pdf_paths = sorted(list(self.input_folder.rglob("*.pdf")))
        total_pdfs = len(all_pdf_paths)
        processed_pdfs = 0
        self.start_time = time.time()

        all_subdirs = sorted(set(p.parent for p in all_pdf_paths))

        for subdir in all_subdirs:
            counter = 1
            pdf_files = sorted(list(subdir.glob("*.pdf")))
            relative_path = subdir.relative_to(self.input_folder)

            for pdf_path in pdf_files:
                pdf_stem = pdf_path.stem
                target_folder = self.output_folder / relative_path / pdf_stem
                target_folder.mkdir(parents=True, exist_ok=True)

                try:
                    doc = fitz.open(str(pdf_path))
                    for page in doc:
                        pix = page.get_pixmap(dpi=300)
                        img_data = pix.tobytes("ppm")
                        image = Image.open(io.BytesIO(img_data))
                        tiff_filename = f"{counter:03d}.tiff"
                        image.save(str(target_folder / tiff_filename), format="TIFF")
                        counter += 1
                    processed_pdfs += 1
                    self.progress_signal.emit(processed_pdfs, total_pdfs)

                    elapsed = time.time() - self.start_time
                    remaining = (elapsed / processed_pdfs) * (total_pdfs - processed_pdfs)
                    remaining_str = str(datetime.timedelta(seconds=int(remaining)))
                    self.time_remaining_signal.emit(remaining_str)

                    self.log_signal.emit(f"✅ Đã xử lý: {pdf_path}")
                except Exception as e:
                    self.log_signal.emit(f"❌ Lỗi với {pdf_path}: {e}")


class PDFtoTIFFApp(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Chuyển PDF sang TIFF - TKT")
        self.resize(720, 540)

        self.layout = QVBoxLayout()
        self.setLayout(self.layout)

        # Input folder selection
        self.input_label = QLabel("Thư mục đầu vào: Chưa chọn")
        self.layout.addWidget(self.input_label)

        self.choose_input_button = QPushButton("Chọn thư mục đầu vào")
        self.choose_input_button.clicked.connect(self.choose_input_folder)
        self.layout.addWidget(self.choose_input_button)

        # Output folder selection
        self.output_label = QLabel("Thư mục lưu kết quả: Chưa chọn")
        self.layout.addWidget(self.output_label)

        self.choose_output_button = QPushButton("Chọn thư mục lưu kết quả")
        self.choose_output_button.clicked.connect(self.choose_output_folder)
        self.choose_output_button.setEnabled(False)
        self.layout.addWidget(self.choose_output_button)

        # Start button
        self.start_button = QPushButton("Bắt đầu chuyển đổi")
        self.start_button.clicked.connect(self.start_conversion)
        self.start_button.setEnabled(False)
        self.layout.addWidget(self.start_button)

        # Progress and status
        self.progress_bar = QProgressBar()
        self.layout.addWidget(self.progress_bar)

        self.status_label = QLabel("Đã chuyển: 0 / 0")
        self.layout.addWidget(self.status_label)

        self.time_label = QLabel("Ước tính thời gian còn lại: --:--:--")
        self.layout.addWidget(self.time_label)

        # Log box
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.layout.addWidget(self.log_box)

        self.input_folder = None
        self.output_folder = None

    def choose_input_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục chứa PDF")
        if folder:
            self.input_folder = Path(folder)
            self.input_label.setText(f"Thư mục đầu vào: {folder}")
            self.choose_output_button.setEnabled(True)

    def choose_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn nơi lưu kết quả")
        if folder:
            self.output_folder = Path(folder)
            self.output_label.setText(f"Thư mục lưu kết quả: {folder}")
            self.start_button.setEnabled(True)

    def start_conversion(self):
        self.worker = ConvertWorker(self.input_folder, self.output_folder)
        self.worker.log_signal.connect(self.append_log)
        self.worker.progress_signal.connect(self.update_progress)
        self.worker.time_remaining_signal.connect(self.update_time_remaining)
        self.progress_bar.setValue(0)
        self.log_box.clear()
        self.worker.start()

    def append_log(self, text):
        self.log_box.append(text)

    def update_progress(self, done, total):
        self.progress_bar.setMaximum(total)
        self.progress_bar.setValue(done)
        self.status_label.setText(f"Đã chuyển: {done} / {total}")

    def update_time_remaining(self, time_str):
        self.time_label.setText(f"Ước tính thời gian còn lại: {time_str}")
