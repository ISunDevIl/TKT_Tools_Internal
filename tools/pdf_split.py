import os
import fitz
import tempfile
import shutil
from PyQt5.QtWidgets import (
    QApplication, QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QLabel,
    QFileDialog, QMessageBox, QScrollArea, QLineEdit, QFrame,
    QInputDialog, QTextEdit, QGroupBox
)
from PyQt5.QtGui import QPixmap, QImage, QCursor
from PyQt5.QtCore import Qt, QSize, QTimer

class PDFSplitterApp(QWidget):
    def __init__(self):
        super().__init__()
        self.doc = None
        self.pdf_path = None
        self.original_page_map = []
        self.next_start_page_index = 0
        self.page_labels = {}

        self.manual_mode = False
        self.delete_mode = False
        self.temp_dir = tempfile.mkdtemp()
        self.split_count = 1
        self.last_dir = os.path.expanduser("~")
        self.loaded_pages = 0
        self.resize_timer = QTimer(self)
        self.resize_timer.setSingleShot(True)
        self.resize_timer.timeout.connect(self._on_resize_timer)
        self.used_pages = set()
        self.thumb_width = 280
        self.thumb_height = 360

        self.initUI()
        self.setWindowTitle("PDF Splitter - TKT")

    def initUI(self):
        toolbar = QHBoxLayout()
        self.open_btn = QPushButton("📂 Chọn PDF")
        self.open_btn.setToolTip("Mở một file PDF mới từ máy tính của bạn.")
        self.open_btn.clicked.connect(self.open_pdf)

        self.manual_btn = QPushButton("✂ Tách thủ công")
        self.manual_btn.setToolTip("Bật/Tắt chế độ tách thủ công bằng cách nhấp chuột.")
        self.manual_btn.clicked.connect(self.toggle_manual_mode)

        self.delete_btn = QPushButton("🗑️ Xóa trang")
        self.delete_btn.setToolTip("Bật/Tắt chế độ xóa trang bằng cách nhấp chuột.")
        self.delete_btn.clicked.connect(self.toggle_delete_mode)
        
        self.reset_delete_btn = QPushButton("↩️ Phục hồi trang")
        self.reset_delete_btn.setToolTip("Tải lại file PDF gốc, hủy mọi thay đổi (xóa trang, tách dở dang).")
        self.reset_delete_btn.clicked.connect(self.revert_deletions)
        self.reset_delete_btn.setEnabled(False)

        self.reset_manual_btn = QPushButton("🔄 Reset Tách")
        self.reset_manual_btn.setToolTip("Xóa tiến trình tách thủ công, không phục hồi trang đã xóa.")
        self.reset_manual_btn.clicked.connect(self.reset_manual_split)
        self.reset_manual_btn.setEnabled(False)

        self.save_btn = QPushButton("💾 Lưu kết quả")
        self.save_btn.setToolTip("Lưu các file đã được tách vào thư mục chứa file PDF gốc.")
        self.save_btn.clicked.connect(self.save_results)

        toolbar.addWidget(self.open_btn)
        toolbar.addWidget(self.manual_btn)
        toolbar.addWidget(self.delete_btn)
        toolbar.addWidget(self.reset_delete_btn)
        toolbar.addWidget(self.reset_manual_btn)
        toolbar.addWidget(self.save_btn)
        toolbar.addStretch()

        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.page_container = QWidget()
        self.page_layout = QVBoxLayout(self.page_container)
        self.page_layout.setAlignment(Qt.AlignTop)
        self.scroll_area.setWidget(self.page_container)

        # --- Bảng điều khiển bên phải ---
        self.range_container = QWidget()
        self.range_layout = QVBoxLayout(self.range_container)
        self.range_layout.setAlignment(Qt.AlignTop)
        self.range_scroll = QScrollArea()
        self.range_scroll.setWidgetResizable(True)
        self.range_scroll.setFixedHeight(220)
        self.range_scroll.setWidget(self.range_container)
        self.add_btn = QPushButton("+ Thêm khoảng")
        self.add_btn.setToolTip("Thêm một dòng mới để nhập khoảng trang cần tách.")
        self.add_btn.clicked.connect(self.add_split_row)
        self.start_btn = QPushButton("🚀 Tách PDF")
        self.start_btn.setToolTip("Bắt đầu tách PDF theo các khoảng trang đã nhập ở trên.")
        self.start_btn.clicked.connect(self.start_auto_split)
        self.split_single_btn = QPushButton("⚡ Tách từng trang")
        self.split_single_btn.setToolTip("Tách tất cả các trang trong file thành các file PDF riêng lẻ.")
        self.split_single_btn.clicked.connect(self.split_single_pages)
        range_group = QGroupBox("📑 Tách tự động theo khoảng")
        range_group_layout = QVBoxLayout()
        range_group_layout.addWidget(self.range_scroll)
        range_group_layout.addWidget(self.add_btn)
        range_group_layout.addWidget(self.start_btn)
        range_group_layout.addWidget(self.split_single_btn)
        range_group.setLayout(range_group_layout)
        
        self.log_box = QTextEdit()
        self.log_box.setReadOnly(True)
        self.log_box.setFixedHeight(200)
        self.log("Ứng dụng sẵn sàng.")
        log_group = QGroupBox("📜 Nhật ký hoạt động")
        log_group_layout = QVBoxLayout()
        log_group_layout.addWidget(self.log_box)
        log_group.setLayout(log_group_layout)
        
        right_panel = QVBoxLayout()
        right_panel.addWidget(range_group)
        right_panel.addStretch()
        right_panel.addWidget(log_group)
        
        content_layout = QHBoxLayout()
        content_layout.addWidget(self.scroll_area, 4)
        content_layout.addLayout(right_panel, 1)
        
        main_layout = QVBoxLayout()
        main_layout.addLayout(toolbar)
        main_layout.addLayout(content_layout)
        self.setLayout(main_layout)

    def _load_pdf_data(self, file_path):
        """Hàm helper để tải và hiển thị dữ liệu từ một file PDF."""
        try:
            self.doc = fitz.open(file_path)
            self.pdf_path = file_path
            self.original_page_map = list(range(len(self.doc)))
            
            self.reset_temp_dir()
            self.loaded_pages = 0
            self.used_pages.clear()
            self.page_labels.clear()
            self.next_start_page_index = 0
            
            if self.manual_mode: self.toggle_manual_mode()
            if self.delete_mode: self.toggle_delete_mode()
            self.reset_delete_btn.setEnabled(True)

            self.show_pages()
            self.scroll_area.verticalScrollBar().valueChanged.connect(self.check_scroll_position)
            self.log(f"✅ Đã tải lại PDF: {file_path} ({len(self.doc)} trang)")

        except Exception as e:
            self.log(f"❌ Lỗi khi tải PDF: {e}")
            QMessageBox.critical(self, "Lỗi", f"Không thể mở hoặc tải lại PDF:\n{str(e)}")

    def _on_resize_timer(self):
        """Hàm bao bọc để khóa giao diện khi vẽ lại lúc resize."""
        self._reflow_grid_on_resize()

    def _reflow_grid_on_resize(self):
        """Chỉ sắp xếp lại các widget đã hiển thị khi resize cửa sổ."""
        if not self.doc or not self.page_labels:
            return

        self.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            scrollbar = self.scroll_area.verticalScrollBar()
            old_scroll_value = scrollbar.value()

            old_rows = []
            while self.page_layout.count():
                row_widget = self.page_layout.takeAt(0).widget()
                if row_widget:
                    old_rows.append(row_widget)
            
            pages_per_row = max(1, (self.scroll_area.width() - 30) // (self.thumb_width + 20))
            row_layout = None
            
            visible_indices = []
            for i in range(self.loaded_pages):
                original_num = self.original_page_map[i]
                if original_num not in self.used_pages:
                    visible_indices.append(i)

            for i, page_index in enumerate(visible_indices):
                if i % pages_per_row == 0:
                    row_widget = QWidget()
                    row_layout = QHBoxLayout(row_widget)
                    row_layout.setAlignment(Qt.AlignLeft)
                    self.page_layout.addWidget(row_widget)
                
                label = self.page_labels.get(page_index)
                if label and row_layout is not None:
                    label.setParent(row_widget)
                    row_layout.addWidget(label)
            
            if row_layout is not None:
                row_layout.addStretch()

            for row in old_rows:
                row.deleteLater()

            QTimer.singleShot(0, lambda: scrollbar.setValue(old_scroll_value))
        finally:
            self.setEnabled(True)
            QApplication.restoreOverrideCursor()
            
    def log(self, msg):
        self.log_box.append(msg)
        self.log_box.verticalScrollBar().setValue(self.log_box.verticalScrollBar().maximum())

    def open_pdf(self):
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Chọn PDF", self.last_dir, "PDF Files (*.pdf)")
        if not file_path:
            return
        self.last_dir = os.path.dirname(file_path)
        
        self.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self._load_pdf_data(file_path)
        finally:
            self.setEnabled(True)
            QApplication.restoreOverrideCursor()

    def check_scroll_position(self, value):
        scrollbar = self.scroll_area.verticalScrollBar()
        if value >= scrollbar.maximum() - 300: 
            if self.loaded_pages < len(self.doc):
                self.show_pages(more=True)

    def show_pages(self, more=False):
        if not self.doc:
            return

        self.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        
        try:
            if not more:
                while self.page_layout.count():
                    child = self.page_layout.takeAt(0)
                    if child.widget():
                        child.widget().deleteLater()
                self.loaded_pages = 0
            
            pages_per_row = max(1, (self.scroll_area.width() - 30) // (self.thumb_width + 20))
            row_layout = None
            
            # Lấy row_layout cuối cùng nếu có để thêm trang vào tiếp
            if self.page_layout.count() > 0:
                last_row_widget = self.page_layout.itemAt(self.page_layout.count() - 1).widget()
                if last_row_widget:
                    row_layout = last_row_widget.layout()
            
            # Mục tiêu là hiển thị thêm khoảng 30 trang MỚI
            pages_shown_this_run = 0
            target_pages = 30

            # Vòng lặp chính: Tiếp tục cho đến khi hiển thị đủ trang hoặc hết tài liệu
            while pages_shown_this_run < target_pages and self.loaded_pages < len(self.doc):
                
                # Xác định lô tiếp theo để quét
                start_scan_index = self.loaded_pages
                end_scan_index = min(start_scan_index + 30, len(self.doc))

                for i in range(start_scan_index, end_scan_index):
                    # Nếu đã hiển thị đủ trang trong lần chạy này thì dừng lại
                    if pages_shown_this_run >= target_pages:
                        break

                    original_num = self.original_page_map[i]
                    if original_num in self.used_pages:
                        continue  # Bỏ qua các trang đã tách

                    # Đếm số widget trong hàng cuối để xác định khi nào cần tạo hàng mới
                    widgets_in_current_row = 0
                    if row_layout:
                        # Trừ 1 nếu item cuối là stretch
                        count = row_layout.count()
                        if count > 0 and row_layout.itemAt(count - 1).spacerItem():
                            widgets_in_current_row = count - 1
                        else:
                            widgets_in_current_row = count

                    # Tạo hàng mới nếu hàng hiện tại đã đầy hoặc chưa có hàng nào
                    if row_layout is None or widgets_in_current_row >= pages_per_row:
                        row_widget = QWidget()
                        row_layout = QHBoxLayout(row_widget)
                        row_layout.setAlignment(Qt.AlignLeft)
                        self.page_layout.addWidget(row_widget)

                    # --- Tạo và hiển thị ảnh thumbnail ---
                    page = self.doc[i]
                    pix = page.get_pixmap()
                    image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                    scaled_pixmap = QPixmap.fromImage(image).scaled(
                        self.thumb_width, self.thumb_height, Qt.KeepAspectRatio, Qt.SmoothTransformation)

                    label = QLabel()
                    label.setPixmap(scaled_pixmap)
                    label.setAlignment(Qt.AlignCenter)
                    label.setFixedSize(self.thumb_width + 10, self.thumb_height + 10)
                    label.setCursor(Qt.PointingHandCursor)
                    label.mousePressEvent = lambda e, num=i: self.page_clicked(num)
                    
                    self.page_labels[i] = label
                    row_layout.addWidget(label)
                    
                    pages_shown_this_run += 1

                # Cập nhật bộ đếm với số trang đã QUÉT qua
                self.loaded_pages = end_scan_index
            
            # Thêm stretch vào hàng cuối cùng để căn lề trái
            if row_layout is not None:
                # Xóa stretch cũ đi nếu có
                if row_layout.count() > 0 and row_layout.itemAt(row_layout.count() - 1).spacerItem():
                    row_layout.takeAt(row_layout.count() - 1)
                row_layout.addStretch()

        except Exception as e:
            self.log(f"❌ Lỗi khi hiển thị trang: {e}")
        finally:
            self.setEnabled(True)
            QApplication.restoreOverrideCursor()

    def toggle_manual_mode(self):
        self.manual_mode = not self.manual_mode
        if self.manual_mode:
            if self.delete_mode:
                self.toggle_delete_mode()
            self.manual_btn.setStyleSheet("background:#ffd966;")
            self.setCursor(QCursor(Qt.CrossCursor))
            self.reset_manual_btn.setEnabled(True)
            start_page_log = ""
            if self.doc and self.next_start_page_index < len(self.original_page_map):
                original_start_num = self.original_page_map[self.next_start_page_index]
                start_page_log = f" Bắt đầu từ trang gốc: {original_start_num + 1}"
            
            self.log(f"✂ Bật chế độ tách thủ công.{start_page_log}")
        else:
            self.manual_btn.setStyleSheet("")
            self.setCursor(QCursor(Qt.ArrowCursor))
            self.reset_manual_btn.setEnabled(False)
            self.log("✂ Tắt chế độ tách thủ công.")
    
    def revert_deletions(self):
        if not self.doc: return

        reply = QMessageBox.question(self, "Xác nhận phục hồi",
                                     "Bạn có chắc muốn hủy tất cả các trang đã xóa và reset lại tiến trình không?",
                                     QMessageBox.Yes | QMessageBox.No, QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.setEnabled(False)
            QApplication.setOverrideCursor(Qt.WaitCursor)
            try:
                self._load_pdf_data(self.pdf_path)
            finally:
                self.setEnabled(True)
                QApplication.restoreOverrideCursor()

    def reset_manual_split(self):
        if not self.doc: return

        self.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            self.next_start_page_index = 0
            self.used_pages.clear()
            self.page_labels.clear()
            self.loaded_pages = 0

            self.show_pages()

            self.reset_temp_dir() 

            self.log(f"🔄 Đã reset. Bắt đầu tách lại từ đầu.")
        finally:
            self.setEnabled(True)
            QApplication.restoreOverrideCursor()

    def page_clicked(self, page_num):
        if self.delete_mode:
            self.delete_page(page_num)
            return

        if not self.manual_mode or not self.doc:
            return

        start = self.next_start_page_index
        end = page_num

        if start > end:
            original_start_num = self.original_page_map[start]
            QMessageBox.warning(self, "Lỗi", f"Vui lòng chọn trang kết thúc sau trang bắt đầu hiện tại (Trang gốc {original_start_num + 1}).")
            return
        
        self.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            # --- Phần 1: Tách file và lưu tạm ---
            new_doc = fitz.open()
            for i in range(start, end + 1):
                new_doc.insert_pdf(self.doc, from_page=i, to_page=i)
            
            new_path = os.path.join(self.temp_dir, f"split_{self.split_count}.pdf")
            new_doc.save(new_path)
            self.split_count += 1
            
            # --- Phần 2: Cập nhật trạng thái ---
            for i in range(start, end + 1):
                original_num = self.original_page_map[i]
                self.used_pages.add(original_num)
            
            self.next_start_page_index = end + 1

            def refresh_and_check_lazy_load():
                scrollbar = self.scroll_area.verticalScrollBar()
                scrollbar.setValue(old_scroll_value)
                # Nếu màn hình trống (thanh cuộn biến mất) và vẫn còn trang, tải thêm
                if scrollbar.maximum() == 0 and self.loaded_pages < len(self.doc):
                    self.show_pages(more=True)

            # --- Phần 3: Làm mới toàn bộ giao diện ---
            old_scroll_value = self.scroll_area.verticalScrollBar().value()
            self.page_labels.clear()
            self.loaded_pages = 0
            self.show_pages() 
            QTimer.singleShot(50, refresh_and_check_lazy_load)

            # --- Phần 4: Ghi log ---
            original_start = self.original_page_map[start]
            original_end = self.original_page_map[end]
            self.log(f"✂ Đã tách trang gốc {original_start+1} → {original_end+1}.")

            if self.next_start_page_index >= len(self.doc):
                self.log("✅ Đã tách tất cả các trang.")
                QMessageBox.information(self, "Hoàn tất", "Đã tách tất cả các trang!")
            else:
                next_original_start = self.original_page_map[self.next_start_page_index]
                self.log(f"Trang bắt đầu tiếp theo là trang gốc: {next_original_start + 1}")
        
        except Exception as e:
            self.log(f"❌ Lỗi khi tách thủ công: {e}")
            QMessageBox.critical(self, "Lỗi", f"Đã có lỗi xảy ra: {e}")
        finally:
            self.setEnabled(True)
            QApplication.restoreOverrideCursor()

    def save_results(self):
        if not os.listdir(self.temp_dir):
            QMessageBox.warning(self, "Lỗi", "Chưa có file nào được tách để lưu.")
            return

        if not self.pdf_path:
            QMessageBox.warning(self, "Lỗi", "Không tìm thấy đường dẫn file PDF gốc.")
            return

        dir_path = os.path.dirname(self.pdf_path)
        
        base_name = os.path.splitext(os.path.basename(self.pdf_path))[0]
        save_dir = os.path.join(dir_path, f"{base_name}_split")
        
        counter = 1
        final_save_dir = save_dir
        while os.path.exists(final_save_dir):
            final_save_dir = f"{save_dir} ({counter})"
            counter += 1
        os.makedirs(final_save_dir)

        files = [f for f in os.listdir(self.temp_dir) if f.endswith(".pdf")]
        try:
            files.sort(key=lambda f: int(f.replace("split_", "").replace("page_", "").replace(".pdf", "")))
        except ValueError:
            files.sort()

        for idx, f in enumerate(files, 1):
            src = os.path.join(self.temp_dir, f)
            dst = os.path.join(final_save_dir, f"{base_name}_{idx:03}.pdf")
            shutil.copy(src, dst)
            self.log(f"💾 Đã lưu file: {dst}")

        QMessageBox.information(
            self, "Hoàn tất", f"Đã lưu {len(files)} file vào thư mục:\n{final_save_dir}")
        
        self.reset_manual_split()

    def reset_temp_dir(self):
        if os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir)
        self.temp_dir = tempfile.mkdtemp()
        self.split_count = 1
    
    def toggle_delete_mode(self):
        self.delete_mode = not self.delete_mode
        if self.delete_mode:
            if self.manual_mode:
                self.toggle_manual_mode()

            self.delete_btn.setStyleSheet("background:#f4cccc;")
            self.setCursor(QCursor(Qt.ForbiddenCursor))
            self.log("🗑️ Bật chế độ xóa trang. Nhấp vào trang để xóa.")
        else:
            self.delete_btn.setStyleSheet("")
            self.setCursor(QCursor(Qt.ArrowCursor))
            self.log("🗑️ Tắt chế độ xóa trang.")

    def delete_page(self, page_num):
        if not self.doc: return

        self.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            def refresh_and_check_lazy_load():
                scrollbar = self.scroll_area.verticalScrollBar()
                scrollbar.setValue(old_scroll_value)
                if scrollbar.maximum() == 0 and self.loaded_pages < len(self.doc):
                    self.show_pages(more=True)
            
            old_scroll_value = self.scroll_area.verticalScrollBar().value()
            
            if page_num < self.next_start_page_index:
                self.next_start_page_index -= 1

            original_page_number = self.original_page_map[page_num]
            self.doc.delete_page(page_num)
            self.original_page_map.pop(page_num)
            self.log(f"✅ Đã xóa trang gốc {original_page_number + 1}. Tổng số trang còn lại: {len(self.doc)}.")
            
            self.page_labels.clear()
            self.loaded_pages = 0
            self.show_pages()
            
            QTimer.singleShot(50, refresh_and_check_lazy_load)

        except Exception as e:
            self.log(f"❌ Lỗi khi xóa trang: {e}")
            QMessageBox.critical(self, "Lỗi", f"Không thể xóa trang: {e}")
        finally:
            self.setEnabled(True)
            QApplication.restoreOverrideCursor()

    def resizeEvent(self, event):
        self.thumb_width = max(150, self.scroll_area.width() // 3 - 30) 
        self.thumb_height = int(self.thumb_width * 1.414)
        self.resize_timer.start(200)
        super().resizeEvent(event)

    def closeEvent(self, event):
        self.reset_temp_dir()
        event.accept()
    
    def add_split_row(self):
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        from_input = QLineEdit()
        from_input.setPlaceholderText("Từ trang")
        to_input = QLineEdit()
        to_input.setPlaceholderText("Đến trang")
        del_btn = QPushButton("🗑")
        del_btn.setFixedWidth(30)
        del_btn.clicked.connect(lambda: row_widget.deleteLater())
        row_layout.addWidget(from_input)
        row_layout.addWidget(to_input)
        row_layout.addWidget(del_btn)
        row_layout.setContentsMargins(0,0,0,0)
        self.range_layout.addWidget(row_widget)

    def start_auto_split(self):
        if not self.doc:
            QMessageBox.warning(self, "Lỗi", "Chưa mở PDF")
            return

        self.reset_temp_dir()
        count = 1
        
        self.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            total_pages = len(self.doc)
            for i in range(self.range_layout.count()):
                widget = self.range_layout.itemAt(i).widget()
                if not widget: continue

                from_input = widget.layout().itemAt(0).widget()
                to_input = widget.layout().itemAt(1).widget()
                
                try:
                    # Chuyển đổi sang số trang gốc để tách cho đúng
                    start_orig = int(from_input.text().strip()) - 1
                    end_orig = int(to_input.text().strip()) - 1
                    
                    if not (0 <= start_orig <= end_orig < len(self.original_page_map) + len(self.doc) - len(self.original_page_map)) :
                         raise ValueError("Số trang gốc không hợp lệ")

                    new_doc = fitz.open()
                    
                    # Lặp qua tài liệu hiện tại để tìm các trang gốc tương ứng
                    pages_to_insert = []
                    for page_idx, orig_idx in enumerate(self.original_page_map):
                        if start_orig <= orig_idx <= end_orig:
                            pages_to_insert.append(page_idx)
                    
                    if not pages_to_insert:
                        self.log(f"⚠️ Không tìm thấy trang nào trong khoảng gốc {start_orig+1}-{end_orig+1} để tách.")
                        continue

                    new_doc.insert_pdf(self.doc, from_page=pages_to_insert[0], to_page=pages_to_insert[-1], start_at=0)
                    out_path = os.path.join(self.temp_dir, f"split_{count}.pdf")
                    new_doc.save(out_path)
                    self.log(f"✅ Tách khoảng gốc {start_orig+1} → {end_orig+1} thành file {os.path.basename(out_path)}")
                    count += 1
                except ValueError as e:
                    QMessageBox.warning(self, "Lỗi", f"Khoảng trang không hợp lệ: '{from_input.text()}' - '{to_input.text()}'. {e}")
                    self.log(f"⚠️ Khoảng trang không hợp lệ: {from_input.text()} - {to_input.text()}")
                    break 
            
            if count > 1:
                QMessageBox.information(self, "Hoàn tất", f"Đã tách thành công {count-1} file.")
        finally:
            self.setEnabled(True)
            QApplication.restoreOverrideCursor()
            
    def split_single_pages(self):
        if not self.doc:
            QMessageBox.warning(self, "Lỗi", "Chưa mở PDF")
            return
            
        self.reset_temp_dir()
        
        self.setEnabled(False)
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            total_pages = len(self.doc)
            for i in range(total_pages):
                new_doc = fitz.open()
                new_doc.insert_pdf(self.doc, from_page=i, to_page=i)
                
                original_num = self.original_page_map[i]
                out_path = os.path.join(self.temp_dir, f"page_{original_num+1}.pdf")
                new_doc.save(out_path)

            self.log(f"✅ Đã tách {total_pages} trang thành các file riêng lẻ (đặt tên theo số trang gốc).")
            QMessageBox.information(self, "Hoàn tất", f"Đã tách {total_pages} trang thành công.")
        except Exception as e:
            self.log(f"❌ Lỗi khi tách từng trang: {e}")
            QMessageBox.critical(self, "Lỗi", f"Xảy ra lỗi: {e}")
        finally:
            self.setEnabled(True)
            QApplication.restoreOverrideCursor()