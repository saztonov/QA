"""Entry point for Gemini Chat application."""

import sys

from PySide6.QtWidgets import QApplication, QMessageBox
from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Qt

from config import load_config
from main_window import MainWindow
from app_logger import app_logger
from theme_manager import theme_manager


def setup_dark_palette(app: QApplication) -> None:
    """Setup dark color palette for the application."""
    palette = QPalette()

    # Base colors
    palette.setColor(QPalette.ColorRole.Window, QColor(30, 30, 30))
    palette.setColor(QPalette.ColorRole.WindowText, QColor(212, 212, 212))
    palette.setColor(QPalette.ColorRole.Base, QColor(37, 37, 38))
    palette.setColor(QPalette.ColorRole.AlternateBase, QColor(45, 45, 45))
    palette.setColor(QPalette.ColorRole.ToolTipBase, QColor(45, 45, 45))
    palette.setColor(QPalette.ColorRole.ToolTipText, QColor(212, 212, 212))
    palette.setColor(QPalette.ColorRole.Text, QColor(212, 212, 212))
    palette.setColor(QPalette.ColorRole.Button, QColor(60, 60, 60))
    palette.setColor(QPalette.ColorRole.ButtonText, QColor(212, 212, 212))
    palette.setColor(QPalette.ColorRole.BrightText, QColor(255, 255, 255))
    palette.setColor(QPalette.ColorRole.Link, QColor(0, 122, 204))
    palette.setColor(QPalette.ColorRole.Highlight, QColor(9, 71, 113))
    palette.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))

    # Disabled colors
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, QColor(127, 127, 127))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(127, 127, 127))
    palette.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(127, 127, 127))

    app.setPalette(palette)


def main():
    """Main entry point."""
    app_logger.startup(version="1.0")

    app = QApplication(sys.argv)
    app.setApplicationName("Gemini Chat")
    app.setStyle("Fusion")

    # Apply theme (starts with dark)
    theme_manager.apply_palette(app)
    app_logger.debug(f"Theme applied: {theme_manager.current_theme}")

    # Load configuration
    try:
        config = load_config()
        app_logger.info(f"Config loaded, API key present: {bool(config.api_key)}")
    except ValueError as e:
        app_logger.error(f"Config error: {e}")
        QMessageBox.critical(
            None,
            "Configuration Error",
            str(e) + "\n\nSet GEMINI_API_KEY environment variable and restart."
        )
        return 1

    # Create and show main window
    window = MainWindow(config)
    window.show()
    app_logger.info("Main window displayed")

    result = app.exec()
    app_logger.shutdown()
    return result


if __name__ == "__main__":
    sys.exit(main())
