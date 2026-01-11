"""Theme Manager for light/dark theme switching.

This module provides a centralized theme management system with:
- Light and dark color schemes
- Theme toggle functionality
- Palette application
- Stylesheet generation for widgets
"""

from PySide6.QtGui import QPalette, QColor
from PySide6.QtCore import Signal, QObject
from PySide6.QtWidgets import QApplication


# Color schemes
LIGHT_COLORS = {
    # Base colors
    'window': '#f5f5f5',
    'window_alt': '#ffffff',
    'panel': '#ffffff',
    'panel_alt': '#fafafa',
    'input': '#ffffff',
    'input_border': '#e0e0e0',
    'input_focus': '#2196f3',

    # Text colors
    'text': '#1a1a1a',
    'text_secondary': '#666666',
    'text_muted': '#999999',
    'text_link': '#1976d2',

    # Border colors
    'border': '#e0e0e0',
    'border_light': '#eeeeee',
    'border_dark': '#bdbdbd',

    # Accent colors
    'accent': '#1976d2',
    'accent_hover': '#1565c0',
    'accent_light': '#e3f2fd',

    # Message bubbles
    'user_bubble': '#e3f2fd',
    'user_bubble_text': '#0d47a1',
    'model_bubble': '#f5f5f5',
    'model_bubble_text': '#1a1a1a',

    # Status colors
    'success': '#4caf50',
    'warning': '#ff9800',
    'error': '#f44336',

    # UI elements
    'button': '#e0e0e0',
    'button_hover': '#d0d0d0',
    'button_text': '#1a1a1a',
    'button_primary': '#1976d2',
    'button_primary_hover': '#1565c0',
    'button_primary_text': '#ffffff',

    # Scrollbar
    'scrollbar_bg': '#f0f0f0',
    'scrollbar_handle': '#c0c0c0',
    'scrollbar_hover': '#a0a0a0',

    # Code/syntax highlighting
    'code_bg': '#f5f5f5',
    'code_key': '#0d47a1',
    'code_string': '#2e7d32',
    'code_number': '#ff5722',
    'code_bool': '#9c27b0',

    # Timeline
    'timeline_bg': '#ffffff',
    'timeline_event': '#e3f2fd',

    # Highlight
    'highlight': '#e3f2fd',
    'highlight_text': '#1a1a1a',
}

DARK_COLORS = {
    # Base colors
    'window': '#1e1e1e',
    'window_alt': '#252526',
    'panel': '#252526',
    'panel_alt': '#2d2d2d',
    'input': '#3c3c3c',
    'input_border': '#555555',
    'input_focus': '#007acc',

    # Text colors
    'text': '#d4d4d4',
    'text_secondary': '#888888',
    'text_muted': '#666666',
    'text_link': '#4fc3f7',

    # Border colors
    'border': '#3c3c3c',
    'border_light': '#4a4a4a',
    'border_dark': '#2d2d2d',

    # Accent colors
    'accent': '#007acc',
    'accent_hover': '#1e90ff',
    'accent_light': '#094771',

    # Message bubbles
    'user_bubble': '#0d47a1',
    'user_bubble_text': '#ffffff',
    'model_bubble': '#37474f',
    'model_bubble_text': '#d4d4d4',

    # Status colors
    'success': '#4caf50',
    'warning': '#ff9800',
    'error': '#f44336',

    # UI elements
    'button': '#3c3c3c',
    'button_hover': '#4a4a4a',
    'button_text': '#d4d4d4',
    'button_primary': '#0d47a1',
    'button_primary_hover': '#1565c0',
    'button_primary_text': '#ffffff',

    # Scrollbar
    'scrollbar_bg': '#2d2d2d',
    'scrollbar_handle': '#555555',
    'scrollbar_hover': '#666666',

    # Code/syntax highlighting
    'code_bg': '#1e1e1e',
    'code_key': '#4fc3f7',
    'code_string': '#98c379',
    'code_number': '#d19a66',
    'code_bool': '#c678dd',

    # Timeline
    'timeline_bg': '#252526',
    'timeline_event': '#37474f',

    # Highlight
    'highlight': '#094771',
    'highlight_text': '#ffffff',
}


class ThemeManager(QObject):
    """Manages application themes with light/dark toggle."""

    theme_changed = Signal(str)  # 'light' or 'dark'

    def __init__(self):
        super().__init__()
        self._current_theme = 'dark'
        self._colors = DARK_COLORS

    @property
    def current_theme(self) -> str:
        """Get current theme name."""
        return self._current_theme

    @property
    def is_dark(self) -> bool:
        """Check if current theme is dark."""
        return self._current_theme == 'dark'

    def color(self, key: str) -> str:
        """Get a color value by key.

        Args:
            key: Color key from the color scheme.

        Returns:
            Hex color string.
        """
        return self._colors.get(key, '#000000')

    def qcolor(self, key: str) -> QColor:
        """Get a QColor by key.

        Args:
            key: Color key from the color scheme.

        Returns:
            QColor object.
        """
        return QColor(self.color(key))

    def toggle(self) -> str:
        """Toggle between light and dark themes.

        Returns:
            New theme name ('light' or 'dark').
        """
        if self._current_theme == 'dark':
            self.set_theme('light')
        else:
            self.set_theme('dark')
        return self._current_theme

    def set_theme(self, theme: str) -> None:
        """Set the current theme.

        Args:
            theme: 'light' or 'dark'.
        """
        if theme not in ('light', 'dark'):
            return

        self._current_theme = theme
        self._colors = LIGHT_COLORS if theme == 'light' else DARK_COLORS
        self.theme_changed.emit(theme)

    def apply_palette(self, app: QApplication) -> None:
        """Apply current theme palette to the application.

        Args:
            app: QApplication instance.
        """
        palette = QPalette()

        # Window
        palette.setColor(QPalette.ColorRole.Window, self.qcolor('window'))
        palette.setColor(QPalette.ColorRole.WindowText, self.qcolor('text'))

        # Base (input backgrounds)
        palette.setColor(QPalette.ColorRole.Base, self.qcolor('input'))
        palette.setColor(QPalette.ColorRole.AlternateBase, self.qcolor('panel_alt'))

        # Text
        palette.setColor(QPalette.ColorRole.Text, self.qcolor('text'))
        palette.setColor(QPalette.ColorRole.BrightText, self.qcolor('text'))

        # Button
        palette.setColor(QPalette.ColorRole.Button, self.qcolor('button'))
        palette.setColor(QPalette.ColorRole.ButtonText, self.qcolor('button_text'))

        # Highlights
        palette.setColor(QPalette.ColorRole.Highlight, self.qcolor('accent'))
        palette.setColor(QPalette.ColorRole.HighlightedText, self.qcolor('highlight_text'))

        # Links
        palette.setColor(QPalette.ColorRole.Link, self.qcolor('text_link'))

        # Tooltips
        palette.setColor(QPalette.ColorRole.ToolTipBase, self.qcolor('panel'))
        palette.setColor(QPalette.ColorRole.ToolTipText, self.qcolor('text'))

        # Disabled colors
        palette.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.WindowText,
            self.qcolor('text_muted')
        )
        palette.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.Text,
            self.qcolor('text_muted')
        )
        palette.setColor(
            QPalette.ColorGroup.Disabled,
            QPalette.ColorRole.ButtonText,
            self.qcolor('text_muted')
        )

        app.setPalette(palette)

    def get_stylesheet(self, widget_type: str) -> str:
        """Get stylesheet for a specific widget type.

        Args:
            widget_type: Type of widget (e.g., 'chat', 'panel', 'button').

        Returns:
            CSS stylesheet string.
        """
        c = self._colors

        stylesheets = {
            'main_widget': f"""
                QWidget {{
                    background-color: {c['window']};
                    color: {c['text']};
                }}
            """,

            'panel': f"""
                QFrame {{
                    background-color: {c['panel']};
                    border: 1px solid {c['border']};
                    border-radius: 6px;
                }}
            """,

            'group_box': f"""
                QGroupBox {{
                    background-color: {c['panel']};
                    border: 1px solid {c['border']};
                    border-radius: 6px;
                    margin-top: 12px;
                    padding-top: 10px;
                    color: {c['text']};
                    font-weight: bold;
                }}
                QGroupBox::title {{
                    subcontrol-origin: margin;
                    left: 10px;
                    padding: 0 5px;
                    color: {c['accent']};
                }}
            """,

            'input': f"""
                QLineEdit {{
                    background-color: {c['input']};
                    border: 1px solid {c['input_border']};
                    border-radius: 20px;
                    padding: 8px 16px;
                    font-size: 14px;
                    color: {c['text']};
                }}
                QLineEdit:focus {{
                    border-color: {c['input_focus']};
                }}
                QLineEdit::placeholder {{
                    color: {c['text_muted']};
                }}
            """,

            'button': f"""
                QPushButton {{
                    background-color: {c['button']};
                    color: {c['button_text']};
                    border: none;
                    padding: 8px 16px;
                    border-radius: 4px;
                    font-size: 13px;
                }}
                QPushButton:hover {{
                    background-color: {c['button_hover']};
                }}
            """,

            'button_primary': f"""
                QPushButton {{
                    background-color: {c['button_primary']};
                    color: {c['button_primary_text']};
                    border: none;
                    padding: 8px 16px;
                    border-radius: 4px;
                    font-size: 13px;
                    font-weight: bold;
                }}
                QPushButton:hover {{
                    background-color: {c['button_primary_hover']};
                }}
            """,

            'combo_box': f"""
                QComboBox {{
                    background-color: {c['input']};
                    border: 1px solid {c['input_border']};
                    border-radius: 4px;
                    padding: 4px 8px;
                    color: {c['text']};
                    min-width: 120px;
                }}
                QComboBox:hover {{
                    border-color: {c['accent']};
                }}
                QComboBox::drop-down {{
                    border: none;
                    padding-right: 8px;
                }}
                QComboBox QAbstractItemView {{
                    background-color: {c['panel']};
                    border: 1px solid {c['border']};
                    color: {c['text']};
                    selection-background-color: {c['accent_light']};
                }}
            """,

            'list_widget': f"""
                QListWidget {{
                    background-color: {c['panel']};
                    border: 1px solid {c['border']};
                    border-radius: 4px;
                    color: {c['text']};
                }}
                QListWidget::item {{
                    padding: 4px;
                }}
                QListWidget::item:selected {{
                    background-color: {c['accent_light']};
                    color: {c['text']};
                }}
                QListWidget::item:hover {{
                    background-color: {c['highlight']};
                }}
            """,

            'tab_widget': f"""
                QTabWidget::pane {{
                    border: none;
                    background-color: {c['panel']};
                }}
                QTabBar::tab {{
                    background-color: transparent;
                    color: {c['text_secondary']};
                    padding: 8px 16px;
                    border-bottom: 2px solid transparent;
                }}
                QTabBar::tab:selected {{
                    color: {c['accent']};
                    border-bottom: 2px solid {c['accent']};
                }}
                QTabBar::tab:hover {{
                    color: {c['text']};
                }}
            """,

            'scroll_area': f"""
                QScrollArea {{
                    border: none;
                    background-color: {c['window']};
                }}
                QScrollBar:vertical {{
                    background-color: {c['scrollbar_bg']};
                    width: 8px;
                    margin: 0;
                }}
                QScrollBar::handle:vertical {{
                    background-color: {c['scrollbar_handle']};
                    min-height: 30px;
                    border-radius: 4px;
                }}
                QScrollBar::handle:vertical:hover {{
                    background-color: {c['scrollbar_hover']};
                }}
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                    height: 0;
                }}
            """,

            'user_bubble': f"""
                QFrame {{
                    background-color: {c['user_bubble']};
                    border-radius: 12px;
                    padding: 8px;
                }}
                QLabel {{
                    color: {c['user_bubble_text']};
                }}
            """,

            'model_bubble': f"""
                QFrame {{
                    background-color: {c['model_bubble']};
                    border-radius: 12px;
                    padding: 8px;
                }}
                QLabel {{
                    color: {c['model_bubble_text']};
                }}
            """,

            'slider': f"""
                QSlider::groove:horizontal {{
                    border: 1px solid {c['border']};
                    height: 6px;
                    background: {c['panel']};
                    border-radius: 3px;
                }}
                QSlider::handle:horizontal {{
                    background: {c['accent']};
                    border: none;
                    width: 14px;
                    margin: -4px 0;
                    border-radius: 7px;
                }}
                QSlider::handle:horizontal:hover {{
                    background: {c['accent_hover']};
                }}
            """,

            'spin_box': f"""
                QSpinBox, QDoubleSpinBox {{
                    background-color: {c['input']};
                    border: 1px solid {c['input_border']};
                    border-radius: 4px;
                    padding: 4px 8px;
                    color: {c['text']};
                    min-width: 70px;
                }}
                QSpinBox:focus, QDoubleSpinBox:focus {{
                    border-color: {c['input_focus']};
                }}
            """,
        }

        return stylesheets.get(widget_type, '')


# Global singleton instance
theme_manager = ThemeManager()
