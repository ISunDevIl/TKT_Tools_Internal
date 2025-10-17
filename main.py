import sys
from PyQt5.QtWidgets import QApplication
from tools.TKT_DashBoard import MainWindow

def main():
    """Hàm chính để khởi tạo và chạy ứng dụng."""
    app = QApplication(sys.argv)
    app.setStyleSheet("""
        * {
            font-family: Arial, sans-serif;
        }
    """)
    window = MainWindow()
    window.show() 
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
