import os
import sys

# 将工程根目录添加到 sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt
from ui.main_window import MainWindow

def main():
    # 启用高 DPI 缩放支持
    app = QApplication(sys.argv)
    app.setApplicationName("FileCleaner Pro")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
