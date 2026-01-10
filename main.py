"""Entry point for Gemini Chat application."""

import sys

from PySide6.QtWidgets import QApplication, QMessageBox

from config import load_config
from main_window import MainWindow


def main():
    """Main entry point."""
    app = QApplication(sys.argv)
    app.setApplicationName("Gemini Chat")
    app.setStyle("Fusion")

    # Load configuration
    try:
        config = load_config()
    except ValueError as e:
        QMessageBox.critical(
            None,
            "Configuration Error",
            str(e) + "\n\nSet GEMINI_API_KEY environment variable and restart."
        )
        return 1

    # Create and show main window
    window = MainWindow(config)
    window.show()

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
