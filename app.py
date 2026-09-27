import os
import sys

from PySide6.QtWidgets import QApplication

from ui.main_window import MainWindow, run


if __name__ == "__main__":
    if os.environ.get("RGV_SMOKE_TEST") == "1":
        app = QApplication(sys.argv)
        window = MainWindow()
        window.show()
        app.processEvents()
        window.close()
    else:
        run()
