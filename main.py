# main.py
import os
import sys
from dotenv import load_dotenv
from PySide6 import QtCore, QtGui, QtWidgets

from cuby.window import CubyWindow
from cuby.splash import CubySplash
from cuby.constants import LOGO_PATH, DATA_DIR

def _register_font_if_exists(path: str) -> bool:
    if not os.path.exists(path):
        return False
    fid = QtGui.QFontDatabase.addApplicationFont(path)
    return fid != -1

def _install_bundled_fonts() -> str:
    base_dir = os.path.dirname(os.path.abspath(__file__))
    fonts_dir = os.path.join(base_dir, "assets", "fonts")
    for fname in ("Vazirmatn-Regular.ttf",
                  "Vazirmatn-Medium.ttf",
                  "Vazirmatn-SemiBold.ttf",
                  "Vazirmatn-Bold.ttf"):
        _register_font_if_exists(os.path.join(fonts_dir, fname))
    families = QtGui.QFontDatabase().families()
    for fam in ("Vazirmatn", "Vazir", "IRANSansWeb", "IRANSans"):
        if fam in families:
            return fam
    return QtWidgets.QApplication.font().family()

def _set_windows_appusermodel_id(app_id: str = "DarkCube.Cuby"):
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        except Exception:
            pass

def main():
    load_dotenv()
    _set_windows_appusermodel_id()

    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("Cuby")
    app.setOrganizationName("DarkCube")

    base_dir = os.path.dirname(os.path.abspath(__file__))
    darkcube_logo_path = os.path.join(base_dir, "assets", "darkcube_logo.png")

    # ---- Splash
    splash = CubySplash(
        logo_path=LOGO_PATH,
        maker_logo_path=darkcube_logo_path,
        maker_line="Built by DarkCube",
        dark=True,
    )
    splash.center_on_screen()
    splash.show()
    QtWidgets.QApplication.processEvents()

    # Fonts
    splash.set_progress(8, "Loading fonts…")
    family = _install_bundled_fonts()
    app.setFont(QtGui.QFont(family, 10))

    # Data dir
    splash.set_progress(18, "Preparing data directories…")
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
    except Exception:
        pass

    # Theme warmup (اختیاری)
    splash.set_progress(28, "Preparing theme…")
    QtWidgets.QApplication.processEvents()

    # Resources
    splash.set_progress(42, "Loading resources…")
    if os.path.exists(LOGO_PATH):
        app.setWindowIcon(QtGui.QIcon(LOGO_PATH))

    # Main window
    splash.set_progress(65, "Starting Cuby window…")
    win = CubyWindow()

    splash.set_progress(88, "Almost there…")
    QtWidgets.QApplication.processEvents()

    splash.set_progress(100, "Ready")
    win.show()
    splash.close()

    sys.exit(app.exec())

if __name__ == "__main__":
    main()
