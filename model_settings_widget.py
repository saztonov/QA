"""Model settings widget for configuring generation parameters."""

from dataclasses import dataclass, field
from typing import Optional

from PySide6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QSlider,
    QSpinBox,
    QDoubleSpinBox,
    QComboBox,
    QGroupBox,
    QPushButton,
    QFrame,
    QScrollArea,
)
from PySide6.QtCore import Qt, Signal


@dataclass
class GenerationConfig:
    """Configuration for model generation parameters."""

    # Core generation parameters
    temperature: float = 1.0  # Fixed at 1.0
    top_p: float = 0.95
    top_k: int = 40
    max_output_tokens: int = 8192

    # Media resolution for images/video
    # LOW = 64 tokens, MEDIUM = 256 tokens, HIGH = zoomed 256 tokens
    media_resolution: str = "MEDIA_RESOLUTION_MEDIUM"

    # Thinking mode
    include_thoughts: bool = True
    thinking_budget: int = 8192  # Token budget for thinking

    # Optional parameters
    candidate_count: int = 1
    presence_penalty: float = 0.0
    frequency_penalty: float = 0.0

    def to_dict(self) -> dict:
        """Convert to dictionary for API call."""
        config = {
            "temperature": self.temperature,
            "top_p": self.top_p,
            "top_k": self.top_k,
            "max_output_tokens": self.max_output_tokens,
            "candidate_count": self.candidate_count,
        }

        # Only add penalties if non-zero
        if self.presence_penalty != 0.0:
            config["presence_penalty"] = self.presence_penalty
        if self.frequency_penalty != 0.0:
            config["frequency_penalty"] = self.frequency_penalty

        return config


class ModelSettingsWidget(QWidget):
    """Widget for configuring model generation parameters."""

    settings_changed = Signal(object)  # Emits GenerationConfig

    def __init__(self):
        super().__init__()
        self.config = GenerationConfig()
        self._setup_ui()

    def _setup_ui(self):
        """Setup the UI."""
        # Dark theme styles
        self.setStyleSheet("""
            QGroupBox {
                background-color: #2d2d2d;
                border: 1px solid #3c3c3c;
                border-radius: 6px;
                margin-top: 12px;
                padding-top: 10px;
                color: #e0e0e0;
                font-weight: bold;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 5px;
                color: #4fc3f7;
            }
            QLabel {
                color: #d4d4d4;
                font-size: 12px;
            }
            QSlider::groove:horizontal {
                border: 1px solid #3c3c3c;
                height: 6px;
                background: #252526;
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #007acc;
                border: none;
                width: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #1e90ff;
            }
            QSpinBox, QDoubleSpinBox {
                background-color: #3c3c3c;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px 8px;
                color: #d4d4d4;
                min-width: 70px;
            }
            QSpinBox:focus, QDoubleSpinBox:focus {
                border-color: #007acc;
            }
            QComboBox {
                background-color: #3c3c3c;
                border: 1px solid #555;
                border-radius: 4px;
                padding: 4px 8px;
                color: #d4d4d4;
                min-width: 120px;
            }
            QComboBox:hover {
                border-color: #007acc;
            }
            QComboBox::drop-down {
                border: none;
                padding-right: 8px;
            }
            QComboBox QAbstractItemView {
                background-color: #252526;
                border: 1px solid #3c3c3c;
                color: #d4d4d4;
                selection-background-color: #094771;
            }
            QPushButton {
                background-color: #3c3c3c;
                color: #d4d4d4;
                border: 1px solid #555;
                padding: 6px 12px;
                border-radius: 4px;
                font-size: 11px;
            }
            QPushButton:hover {
                background-color: #4a4a4a;
                border-color: #007acc;
            }
        """)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        # Generation parameters group
        gen_group = QGroupBox("Generation Parameters")
        gen_layout = QVBoxLayout(gen_group)
        gen_layout.setSpacing(12)

        # Temperature (fixed at 1.0)
        temp_layout = QHBoxLayout()
        temp_label = QLabel("Temperature:")
        temp_label.setToolTip("Fixed at 1.0 for optimal results")
        temp_label.setMinimumWidth(100)

        temp_value = QLabel("1.0 (fixed)")
        temp_value.setStyleSheet("color: #4fc3f7; font-weight: bold;")

        temp_layout.addWidget(temp_label)
        temp_layout.addStretch()
        temp_layout.addWidget(temp_value)
        gen_layout.addLayout(temp_layout)

        # Top P (0.0 - 1.0)
        topp_layout = QHBoxLayout()
        topp_label = QLabel("Top P:")
        topp_label.setToolTip("Nucleus sampling - cumulative probability threshold (0.0-1.0)")
        topp_label.setMinimumWidth(100)

        self.topp_slider = QSlider(Qt.Orientation.Horizontal)
        self.topp_slider.setRange(0, 100)
        self.topp_slider.setValue(int(self.config.top_p * 100))
        self.topp_slider.valueChanged.connect(self._on_topp_slider_changed)

        self.topp_spinbox = QDoubleSpinBox()
        self.topp_spinbox.setRange(0.0, 1.0)
        self.topp_spinbox.setSingleStep(0.05)
        self.topp_spinbox.setDecimals(2)
        self.topp_spinbox.setValue(self.config.top_p)
        self.topp_spinbox.valueChanged.connect(self._on_topp_spinbox_changed)

        topp_layout.addWidget(topp_label)
        topp_layout.addWidget(self.topp_slider, 1)
        topp_layout.addWidget(self.topp_spinbox)
        gen_layout.addLayout(topp_layout)

        # Top K (1 - 100)
        topk_layout = QHBoxLayout()
        topk_label = QLabel("Top K:")
        topk_label.setToolTip("Maximum tokens to consider during sampling (1-100)")
        topk_label.setMinimumWidth(100)

        self.topk_slider = QSlider(Qt.Orientation.Horizontal)
        self.topk_slider.setRange(1, 100)
        self.topk_slider.setValue(self.config.top_k)
        self.topk_slider.valueChanged.connect(self._on_topk_slider_changed)

        self.topk_spinbox = QSpinBox()
        self.topk_spinbox.setRange(1, 100)
        self.topk_spinbox.setValue(self.config.top_k)
        self.topk_spinbox.valueChanged.connect(self._on_topk_spinbox_changed)

        topk_layout.addWidget(topk_label)
        topk_layout.addWidget(self.topk_slider, 1)
        topk_layout.addWidget(self.topk_spinbox)
        gen_layout.addLayout(topk_layout)

        # Max Output Tokens
        max_tokens_layout = QHBoxLayout()
        max_tokens_label = QLabel("Max Tokens:")
        max_tokens_label.setToolTip("Maximum number of tokens in response (1-65536)")
        max_tokens_label.setMinimumWidth(100)

        self.max_tokens_spinbox = QSpinBox()
        self.max_tokens_spinbox.setRange(1, 65536)
        self.max_tokens_spinbox.setValue(self.config.max_output_tokens)
        self.max_tokens_spinbox.setSingleStep(256)
        self.max_tokens_spinbox.valueChanged.connect(self._on_max_tokens_changed)

        max_tokens_layout.addWidget(max_tokens_label)
        max_tokens_layout.addStretch()
        max_tokens_layout.addWidget(self.max_tokens_spinbox)
        gen_layout.addLayout(max_tokens_layout)

        layout.addWidget(gen_group)

        # Media settings group
        media_group = QGroupBox("Media Settings")
        media_layout = QVBoxLayout(media_group)
        media_layout.setSpacing(12)

        # Media Resolution
        resolution_layout = QHBoxLayout()
        resolution_label = QLabel("Image Resolution:")
        resolution_label.setToolTip(
            "Image processing detail level:\n"
            "LOW - 64 tokens per image (fastest)\n"
            "MEDIUM - 256 tokens per image (balanced)\n"
            "HIGH - 256 tokens with zoom (best quality)"
        )
        resolution_label.setMinimumWidth(100)

        self.resolution_combo = QComboBox()
        self.resolution_combo.addItem("Low (64 tokens)", "MEDIA_RESOLUTION_LOW")
        self.resolution_combo.addItem("Medium (256 tokens)", "MEDIA_RESOLUTION_MEDIUM")
        self.resolution_combo.addItem("High (zoomed)", "MEDIA_RESOLUTION_HIGH")
        self.resolution_combo.setCurrentIndex(1)  # Default to medium
        self.resolution_combo.currentIndexChanged.connect(self._on_resolution_changed)

        resolution_layout.addWidget(resolution_label)
        resolution_layout.addStretch()
        resolution_layout.addWidget(self.resolution_combo)
        media_layout.addLayout(resolution_layout)

        layout.addWidget(media_group)

        # Thinking settings group
        thinking_group = QGroupBox("Thinking Mode")
        thinking_layout = QVBoxLayout(thinking_group)
        thinking_layout.setSpacing(12)

        # Include thoughts checkbox
        from PySide6.QtWidgets import QCheckBox
        self.include_thoughts_checkbox = QCheckBox("Show model thoughts")
        self.include_thoughts_checkbox.setChecked(self.config.include_thoughts)
        self.include_thoughts_checkbox.setToolTip(
            "Display the model's reasoning process in chat"
        )
        self.include_thoughts_checkbox.stateChanged.connect(self._on_thoughts_changed)
        thinking_layout.addWidget(self.include_thoughts_checkbox)

        # Thinking budget
        budget_layout = QHBoxLayout()
        budget_label = QLabel("Thinking Budget:")
        budget_label.setToolTip("Token budget for model thinking (1-24576)")
        budget_label.setMinimumWidth(100)

        self.thinking_budget_spinbox = QSpinBox()
        self.thinking_budget_spinbox.setRange(1, 24576)
        self.thinking_budget_spinbox.setValue(self.config.thinking_budget)
        self.thinking_budget_spinbox.setSingleStep(1024)
        self.thinking_budget_spinbox.valueChanged.connect(self._on_thinking_budget_changed)

        budget_layout.addWidget(budget_label)
        budget_layout.addStretch()
        budget_layout.addWidget(self.thinking_budget_spinbox)
        thinking_layout.addLayout(budget_layout)

        layout.addWidget(thinking_group)

        # Advanced settings group (collapsed by default)
        advanced_group = QGroupBox("Advanced")
        advanced_layout = QVBoxLayout(advanced_group)
        advanced_layout.setSpacing(12)

        # Presence Penalty
        presence_layout = QHBoxLayout()
        presence_label = QLabel("Presence Penalty:")
        presence_label.setToolTip("Penalizes repeated topics (-2.0 to 2.0)")
        presence_label.setMinimumWidth(100)

        self.presence_spinbox = QDoubleSpinBox()
        self.presence_spinbox.setRange(-2.0, 2.0)
        self.presence_spinbox.setSingleStep(0.1)
        self.presence_spinbox.setDecimals(2)
        self.presence_spinbox.setValue(self.config.presence_penalty)
        self.presence_spinbox.valueChanged.connect(self._on_presence_changed)

        presence_layout.addWidget(presence_label)
        presence_layout.addStretch()
        presence_layout.addWidget(self.presence_spinbox)
        advanced_layout.addLayout(presence_layout)

        # Frequency Penalty
        frequency_layout = QHBoxLayout()
        frequency_label = QLabel("Frequency Penalty:")
        frequency_label.setToolTip("Penalizes token repetition (-2.0 to 2.0)")
        frequency_label.setMinimumWidth(100)

        self.frequency_spinbox = QDoubleSpinBox()
        self.frequency_spinbox.setRange(-2.0, 2.0)
        self.frequency_spinbox.setSingleStep(0.1)
        self.frequency_spinbox.setDecimals(2)
        self.frequency_spinbox.setValue(self.config.frequency_penalty)
        self.frequency_spinbox.valueChanged.connect(self._on_frequency_changed)

        frequency_layout.addWidget(frequency_label)
        frequency_layout.addStretch()
        frequency_layout.addWidget(self.frequency_spinbox)
        advanced_layout.addLayout(frequency_layout)

        layout.addWidget(advanced_group)

        # Reset button
        reset_btn = QPushButton("Reset to Defaults")
        reset_btn.clicked.connect(self._reset_to_defaults)
        layout.addWidget(reset_btn)

        layout.addStretch()

    def _on_thoughts_changed(self, state: int):
        """Handle include thoughts checkbox change."""
        self.config.include_thoughts = state == 2  # Qt.Checked = 2
        self._emit_settings()

    def _on_thinking_budget_changed(self, value: int):
        """Handle thinking budget change."""
        self.config.thinking_budget = value
        self._emit_settings()

    def _on_topp_slider_changed(self, value: int):
        """Handle top_p slider change."""
        topp = value / 100.0
        self.topp_spinbox.blockSignals(True)
        self.topp_spinbox.setValue(topp)
        self.topp_spinbox.blockSignals(False)
        self.config.top_p = topp
        self._emit_settings()

    def _on_topp_spinbox_changed(self, value: float):
        """Handle top_p spinbox change."""
        self.topp_slider.blockSignals(True)
        self.topp_slider.setValue(int(value * 100))
        self.topp_slider.blockSignals(False)
        self.config.top_p = value
        self._emit_settings()

    def _on_topk_slider_changed(self, value: int):
        """Handle top_k slider change."""
        self.topk_spinbox.blockSignals(True)
        self.topk_spinbox.setValue(value)
        self.topk_spinbox.blockSignals(False)
        self.config.top_k = value
        self._emit_settings()

    def _on_topk_spinbox_changed(self, value: int):
        """Handle top_k spinbox change."""
        self.topk_slider.blockSignals(True)
        self.topk_slider.setValue(value)
        self.topk_slider.blockSignals(False)
        self.config.top_k = value
        self._emit_settings()

    def _on_max_tokens_changed(self, value: int):
        """Handle max tokens change."""
        self.config.max_output_tokens = value
        self._emit_settings()

    def _on_resolution_changed(self, index: int):
        """Handle resolution change."""
        self.config.media_resolution = self.resolution_combo.currentData()
        self._emit_settings()

    def _on_presence_changed(self, value: float):
        """Handle presence penalty change."""
        self.config.presence_penalty = value
        self._emit_settings()

    def _on_frequency_changed(self, value: float):
        """Handle frequency penalty change."""
        self.config.frequency_penalty = value
        self._emit_settings()

    def _emit_settings(self):
        """Emit settings changed signal."""
        self.settings_changed.emit(self.config)

    def _reset_to_defaults(self):
        """Reset all settings to defaults."""
        self.config = GenerationConfig()

        # Update UI
        self.topp_slider.setValue(int(self.config.top_p * 100))
        self.topp_spinbox.setValue(self.config.top_p)
        self.topk_slider.setValue(self.config.top_k)
        self.topk_spinbox.setValue(self.config.top_k)
        self.max_tokens_spinbox.setValue(self.config.max_output_tokens)
        self.resolution_combo.setCurrentIndex(1)
        self.include_thoughts_checkbox.setChecked(self.config.include_thoughts)
        self.thinking_budget_spinbox.setValue(self.config.thinking_budget)
        self.presence_spinbox.setValue(self.config.presence_penalty)
        self.frequency_spinbox.setValue(self.config.frequency_penalty)

        self._emit_settings()

    def get_config(self) -> GenerationConfig:
        """Get current generation config."""
        return self.config

    def set_config(self, config: GenerationConfig):
        """Set generation config."""
        self.config = config

        # Update UI without emitting signals
        self.topp_slider.blockSignals(True)
        self.topp_spinbox.blockSignals(True)
        self.topp_slider.setValue(int(config.top_p * 100))
        self.topp_spinbox.setValue(config.top_p)
        self.topp_slider.blockSignals(False)
        self.topp_spinbox.blockSignals(False)

        self.topk_slider.blockSignals(True)
        self.topk_spinbox.blockSignals(True)
        self.topk_slider.setValue(config.top_k)
        self.topk_spinbox.setValue(config.top_k)
        self.topk_slider.blockSignals(False)
        self.topk_spinbox.blockSignals(False)

        self.max_tokens_spinbox.blockSignals(True)
        self.max_tokens_spinbox.setValue(config.max_output_tokens)
        self.max_tokens_spinbox.blockSignals(False)

        # Set resolution combo
        for i in range(self.resolution_combo.count()):
            if self.resolution_combo.itemData(i) == config.media_resolution:
                self.resolution_combo.blockSignals(True)
                self.resolution_combo.setCurrentIndex(i)
                self.resolution_combo.blockSignals(False)
                break

        # Thinking settings
        self.include_thoughts_checkbox.blockSignals(True)
        self.include_thoughts_checkbox.setChecked(config.include_thoughts)
        self.include_thoughts_checkbox.blockSignals(False)

        self.thinking_budget_spinbox.blockSignals(True)
        self.thinking_budget_spinbox.setValue(config.thinking_budget)
        self.thinking_budget_spinbox.blockSignals(False)

        self.presence_spinbox.blockSignals(True)
        self.presence_spinbox.setValue(config.presence_penalty)
        self.presence_spinbox.blockSignals(False)

        self.frequency_spinbox.blockSignals(True)
        self.frequency_spinbox.setValue(config.frequency_penalty)
        self.frequency_spinbox.blockSignals(False)
