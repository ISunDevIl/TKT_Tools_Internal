import sys
from pathlib import Path
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QPushButton, QHBoxLayout, QSpacerItem, QSizePolicy
from PyQt5.QtCore import Qt, QSize
from PyQt5.QtGui import QIcon


def rsrc_path(*parts):
    """
    Ưu tiên đường dẫn trong bundle (sys._MEIPASS).
    Khi chạy debug, tự quy về thư mục package (cùng file hiện tại).
    Hỗ trợ path dạng bắt đầu bằng 'TKT_Tools' (bỏ tiền tố khi chạy dev).
    """
    # 1) Khi chạy .exe (onefile)
    if hasattr(sys, "_MEIPASS"):
        p = Path(sys._MEIPASS).joinpath(*parts)
        if p.exists():
            return str(p)

    # 2) Khi chạy từ mã nguồn (debug)
    pkg_root = Path(__file__).resolve().parent  # thư mục package TKT_Tools
    if parts and parts[0].lower() == "tkt_tools":
        p = pkg_root.joinpath(*parts[1:])       # bỏ tiền tố TKT_Tools
    else:
        p = pkg_root.joinpath(*parts)
    if p.exists():
        return str(p)

    # 3) Phòng hờ: thử theo CWD
    return str(Path.cwd().joinpath(*parts))

# tiện lợi: đường dẫn vào thư mục assets theo mapping spec ('assets' -> 'TKT_Tools/assets')
def asset_path(*more):
    return rsrc_path("TKT_Tools", "assets", *more)
class SettingsWidget(QWidget):
    def __init__(self, open_subscriptions_callback):
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(24)                   

        # Hàng chứa nút quản lý gói đăng ký (trái trên)
        top_bar = QHBoxLayout()

        btn_manage = QPushButton("Quản lý gói đăng ký")
        btn_manage.setIcon(QIcon(asset_path("icon", "boite.png")))
        btn_manage.setIconSize(QSize(36, 36))                             
        btn_manage.setFixedSize(360, 96)                               
        btn_manage.setStyleSheet("""
            QPushButton {
                padding:10px 18px;              
                font-size:20px;                    
                font-family: Arial, sans-serif;
                border:1px solid #ccc;
                border-radius:10px;
                background:#f5f5f5;
                color:#333;
                text-align:left;                 
            }
            QPushButton:hover { background:#e8e8e8; border:2px solid #000000; }
        """)
        btn_manage.clicked.connect(open_subscriptions_callback)

        top_bar.addWidget(btn_manage, alignment=Qt.AlignLeft)
        top_bar.addItem(QSpacerItem(40, 20, QSizePolicy.Expanding, QSizePolicy.Minimum))
        layout.addLayout(top_bar)

        # Label nội dung chính
        label = QLabel("⚙️ Trang Cài đặt\n\nTại đây bạn có thể cấu hình ứng dụng.")
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet("""
            font-size:22px;       
            font-weight:600;      
            color:#444;
            padding:24px;         
            font-family: Arial, sans-serif;
        """)
        layout.addWidget(label)
