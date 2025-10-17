import os
import re
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QPushButton, QLabel,
    QFileDialog, QRadioButton, QHBoxLayout, QLineEdit, QMessageBox,
    QTableWidget, QTableWidgetItem, QSpinBox, QTextEdit, QCheckBox,
    QGroupBox, QSizePolicy, QHeaderView, QComboBox, QAbstractItemView
)
from PyQt5.QtGui import QFont
from PyQt5.QtCore import Qt, QThread, pyqtSignal
from openpyxl import Workbook


# ========== Worker chạy trong QThread ==========
class CountWorker(QThread):
    progress = pyqtSignal(str, int)   # (folder, count)
    finished = pyqtSignal(list, list) # (results, missing_numbers)
    message = pyqtSignal(str)

    def __init__(self, folder, extensions, root_only, max_depth, check_lien_mach):
        super().__init__()
        self.folder = folder
        self.extensions = extensions
        self.root_only = root_only
        self.max_depth = max_depth
        self.check_lien_mach = check_lien_mach
        self._is_running = True
        self.results = []
        self.missing_numbers = []

    def stop(self):
        self._is_running = False

    def run(self):
        try:
            if self.root_only:
                count = self.countInFolder(self.folder)
                self.results.append((self.folder, count))
            else:
                base_depth = self.folder.rstrip(os.sep).count(os.sep)
                for root, dirs, files in os.walk(self.folder):
                    if not self._is_running:
                        break
                    current_depth = root.count(os.sep) - base_depth
                    if self.max_depth != -1 and current_depth > self.max_depth:
                        dirs[:] = []
                        continue
                    if self.max_depth != -1 and current_depth == self.max_depth:
                        dirs[:] = []

                    count = self.countInFolder(root)
                    self.results.append((root, count))
                    self.progress.emit(root, count)

            # kiểm tra liền mạch nếu cần
            if self._is_running and self.check_lien_mach:
                self.checkLienMach()

        except Exception as e:
            self.message.emit(f"Lỗi: {str(e)}")

        self.finished.emit(self.results, self.missing_numbers)

    def countInFolder(self, folder):
        count = 0
        try:
            for file in os.listdir(folder):
                if not self._is_running:
                    break
                path = os.path.join(folder, file)
                if os.path.isfile(path):
                    if any(file.lower().endswith(ext) for ext in self.extensions):
                        count += 1
        except PermissionError:
            pass
        return count

    def extract_number(self, name):
        match = re.search(r'(\d+)$', name)
        if match:
            return int(match.group(1))
        return None

    def checkLienMach(self):
        base_depth = self.folder.rstrip(os.sep).count(os.sep)
        for root, dirs, files in os.walk(self.folder):
            if not self._is_running:
                break
            current_depth = root.count(os.sep) - base_depth
            if self.max_depth != -1 and current_depth > self.max_depth:
                dirs[:] = []
                continue
            if self.max_depth != -1 and current_depth == self.max_depth:
                dirs[:] = []

            numbers = []
            for f in files:
                if any(f.lower().endswith(ext) for ext in self.extensions):
                    num = self.extract_number(os.path.splitext(f)[0])
                    if num is not None:
                        numbers.append(num)
            self.find_missing(numbers, root)

            folder_numbers = []
            for d in dirs:
                num = self.extract_number(d)
                if num is not None:
                    folder_numbers.append(num)
            self.find_missing(folder_numbers, root)

    def find_missing(self, numbers, path):
        if not numbers:
            return
        numbers.sort()
        start = numbers[0]
        number_set = set(numbers)
        for expected in range(start, numbers[-1] + 1):
            if not self._is_running:
                break
            if expected not in number_set:
                self.missing_numbers.append((path, expected))


# ========== Giao diện chính ==========
class Counter_File(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.results = []
        self.missing_numbers = []
        self.worker = None
        self.initUI()

    def initUI(self):
        layout = QVBoxLayout()

        # font mặc định
        font = QFont("Arial", 9)
        self.setFont(font)
        self.setStyleSheet("""
            QWidget { color: #000; font-family: Arial, sans-serif; }
            QPushButton {
                padding: 4px 8px;
                min-width: 90px;
                max-width: 100px;
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
                font-family: Arial;
                font-size: 9pt;         
                gridline-color: #dcdcdc;
            }
            QHeaderView::section {
                background-color: #fff;
                font-size: 9pt;            
                padding: 4px;
                border: none;
            }
        """)

        # --- Chọn thư mục ---
        folderGroup = QGroupBox("Thư mục")
        fLayout = QHBoxLayout()
        self.folderLabel = QLabel("Chưa chọn thư mục")
        self.folderLabel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)
        self.selectBtn = QPushButton("Chọn thư mục"); self.selectBtn.setObjectName("selectBtn")
        fLayout.addWidget(self.folderLabel)
        fLayout.addWidget(self.selectBtn)
        folderGroup.setLayout(fLayout)
        layout.addWidget(folderGroup)

        self.selectBtn.clicked.connect(self.selectFolder)

        # --- Bộ lọc file + Tùy chọn (cùng hàng) ---
        filterOptGroup = QGroupBox("Bộ lọc và Tùy chọn")
        foLayout = QHBoxLayout()
        foLayout.addWidget(QLabel("Loại file:"))
        self.filterCombo = QComboBox()
        self.filterCombo.setMaximumWidth(200)
        self.filterCombo.addItems([".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
        ".odt", ".ods", ".odp",".txt",".jpg", ".png"])
        foLayout.addWidget(self.filterCombo)
        self.chkLienMach = QCheckBox("Kiểm tra liền mạch")
        foLayout.addWidget(self.chkLienMach)
        foLayout.addStretch()
        filterOptGroup.setLayout(foLayout)
        layout.addWidget(filterOptGroup)

        # --- Phạm vi ---
        depthGroup = QGroupBox("Phạm vi quét (-1 là tất cả)")
        dLayout = QHBoxLayout()
        dLayout.setSpacing(10)

        self.radioRoot = QRadioButton("Chỉ thư mục gốc")
        self.radioAll = QRadioButton("Bao gồm thư mục con")
        self.radioAll.setChecked(True)

        self.depthSpinBox = QSpinBox()
        self.depthSpinBox.setRange(-1, 99)
        self.depthSpinBox.setValue(-1)
        self.depthSpinBox.setFixedWidth(50)

        dLayout.addWidget(QLabel("Độ sâu thư mục:"))
        dLayout.addWidget(self.depthSpinBox)
        dLayout.addStretch()
        dLayout.addWidget(self.radioRoot)
        dLayout.addWidget(self.radioAll)

        self.radioRoot.toggled.connect(self.updateDepthMode)
        self.radioAll.toggled.connect(self.updateDepthMode)
        self.depthSpinBox.valueChanged.connect(self.syncRadioWithDepth)


        depthGroup.setLayout(dLayout)
        layout.addWidget(depthGroup)

        # --- Nút chức năng ---
        btnLayout = QHBoxLayout()
        btnLayout.addStretch()
        self.countBtn = QPushButton("Bắt đầu"); self.countBtn.setObjectName("countBtn")
        self.stopBtn = QPushButton("Dừng"); self.stopBtn.setObjectName("stopBtn")
        self.exportBtn = QPushButton("Xuất Excel"); self.exportBtn.setObjectName("exportBtn")
        self.stopBtn.setEnabled(False)
        btnLayout.setSpacing(6)  
        btnLayout.addWidget(self.countBtn)
        btnLayout.addWidget(self.stopBtn)
        btnLayout.addWidget(self.exportBtn)
        layout.addLayout(btnLayout)

        self.countBtn.clicked.connect(self.startCount)
        self.stopBtn.clicked.connect(self.stopCount)
        self.exportBtn.clicked.connect(self.exportExcel)

        # --- Bảng kết quả ---
        self.result_table = QTableWidget()
        self.result_table.verticalHeader().setVisible(False)
        self.result_table.setColumnCount(4)
        self.result_table.setHorizontalHeaderLabels(["STT", "Thư mục", "Số file", "Số thư mục / File thiếu"])
        self.result_table.setMinimumHeight(220)

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
        for i in range(4):
            if i != 1:
                header.setSectionResizeMode(i, QHeaderView.ResizeToContents)

        self.result_table.setSortingEnabled(True)
        self.result_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)

        layout.addWidget(self.result_table)
        # --- Text ---
        self.text_result = QTextEdit()
        self.text_result.setReadOnly(True)
        self.text_result.setFont(QFont("Consolas", 9))
        self.text_result.setMinimumHeight(100)
        layout.addWidget(self.text_result)

        self.setLayout(layout)

    # === Các hàm xử lý ===
    def selectFolder(self):
        folder = QFileDialog.getExistingDirectory(self, "Chọn thư mục")
        if folder:
            self.folderLabel.setText(folder)
            self.folderPath = folder

    def startCount(self):
        if not hasattr(self, 'folderPath'):
            QMessageBox.warning(self, "Cảnh báo", "Bạn chưa chọn thư mục")
            return
        self.result_table.setRowCount(0)
        self.text_result.clear()
        self.missing_numbers.clear()
        extensions = [self.filterCombo.currentText().lower()]
        root_only = self.radioRoot.isChecked()
        max_depth = 0 if root_only else self.depthSpinBox.value()
        check_lien = self.chkLienMach.isChecked()

        self.worker = CountWorker(self.folderPath, extensions, root_only, max_depth, check_lien)
        self.worker.progress.connect(self.updateProgress)
        self.worker.finished.connect(self.finishCount)
        self.worker.message.connect(self.text_result.append)

        self.countBtn.setEnabled(False)
        self.stopBtn.setEnabled(True)
        self.worker.start()

    def stopCount(self):
        if self.worker:
            self.worker.stop()
            self.text_result.append("⚠️ Đã yêu cầu dừng quá trình...")

    def updateProgress(self, folder, count):
        row = self.result_table.rowCount()
        self.result_table.insertRow(row)
        self.result_table.setItem(row, 0, QTableWidgetItem(str(row + 1)))
        self.result_table.setItem(row, 1, QTableWidgetItem(folder))
        self.result_table.setItem(row, 2, QTableWidgetItem(str(count)))
        self.result_table.setItem(row, 3, QTableWidgetItem("0"))


    def finishCount(self, results, missing_numbers):
        self.results = results
        self.missing_numbers = missing_numbers

        missing_map = {}
        for p, m in self.missing_numbers:
            missing_map[p] = missing_map.get(p, 0) + 1

        self.text_result.append("=== Kết quả thống kê ===")
        for folder, count in self.results:
            self.text_result.append(f"[OK] {folder} có {count} file")

        if self.missing_numbers:
            self.text_result.append("\n⚠️ Phát hiện thiếu số:")
            for p, m in self.missing_numbers:
                self.text_result.append(f"[Thiếu] {p} thiếu {m:03d}")
        else:
            self.text_result.append("\n✅ Không phát hiện thiếu số")

        for row in range(self.result_table.rowCount()):
            folder = self.result_table.item(row, 1).text()
            self.result_table.setItem(row, 3, QTableWidgetItem(str(missing_map.get(folder, 0))))


        self.countBtn.setEnabled(True)
        self.stopBtn.setEnabled(False)
        self.text_result.append("\n=== Hoàn tất ===\n")

    def updateDepthMode(self):
        if self.radioRoot.isChecked():
            self.depthSpinBox.setValue(0)
        else:
            if self.depthSpinBox.value() == 0:
                self.depthSpinBox.setValue(-1)
            self.depthSpinBox.setEnabled(True)

    def syncRadioWithDepth(self):
        val = self.depthSpinBox.value()
        if val == 0:
            self.radioRoot.setChecked(True)
        else:
            self.radioAll.setChecked(True)

    def exportExcel(self):
        if not self.results:
            QMessageBox.warning(self, "Cảnh báo", "Chưa có dữ liệu")
            return
        saveFolder = QFileDialog.getExistingDirectory(self, "Chọn thư mục lưu")
        if not saveFolder:
            return

        wb = Workbook()
        ws1 = wb.active; ws1.title = "Thống kê"
        ws1.append(["Thư mục", "Tổng file", "Số thư mục / File thiếu"])
        missing_map = {}
        for p, m in self.missing_numbers:
            missing_map[p] = missing_map.get(p, 0) + 1
        for folder, count in self.results:
            ws1.append([folder, count, missing_map.get(folder, 0)])

        ws2 = wb.create_sheet("Chi tiết")
        ws2.append(["Thư mục", "Số thiếu"])
        for p, m in self.missing_numbers:
            ws2.append([p, f"{m:03d}"])

        # --- Lấy tên thư mục cuối cùng để đặt tên file ---
        folder_name = os.path.basename(os.path.normpath(self.folderPath))
        if not folder_name:  
            folder_name = "root"

        base_name = f"thong_ke_file_{folder_name}"
        ext = ".xlsx"
        savePath = os.path.join(saveFolder, base_name + ext)

        # --- Nếu file trùng thì thêm (1), (2)... ---
        i = 1
        while os.path.exists(savePath):
            savePath = os.path.join(saveFolder, f"{base_name}({i}){ext}")
            i += 1

        wb.save(savePath)
        QMessageBox.information(self, "OK", f"Đã lưu tại:\n{savePath}")

