import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QPushButton, QLabel, QScrollArea, QTextEdit,
                           QHBoxLayout, QProgressBar, QFrame, QGroupBox, QRadioButton,
                           QButtonGroup, QMessageBox, QSplitter, QCheckBox, QToolButton,
                           QLineEdit, QComboBox, QSizePolicy)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QEvent, QTimer, QSize, QPropertyAnimation, QEasingCurve
from PyQt6.QtGui import QFont, QColor, QPalette, QIcon, QPainter, QLinearGradient
import logging
from bungie_oauth import OAuthManager
from catalyst import CatalystAPI
import os
from dotenv import load_dotenv
import threading
import json
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

# Configure root logger
logging.basicConfig(level=logging.INFO)
root_logger = logging.getLogger()

# Theme definitions
THEMES = {
    'dark': {
        'background': '#000000',  # Pure black
        'surface': '#0D0D0D',     # Very dark gray
        'primary': '#00FFFF',     # Cyan
        'secondary': '#FF00FF',   # Magenta
        'accent': '#EBFE05',      # Neon yellow
        'text': '#FFFFFF',        # Pure white
        'text_secondary': '#00FFFF', # Cyan for secondary text
        'error': '#FF3D3D',
        'success': '#00FF00',     # Neon green
        'warning': '#FF9900',     # Orange
        'neon_glow': '0 0 5px',   # Subtle glow
        'neon_glow_strong': '0 0 10px' # Stronger glow for hover
    },
    'light': {
        'background': '#FFFFFF',
        'surface': '#F5F5F5',
        'primary': '#00FFFF',     # Keeping neon colors for light theme
        'secondary': '#FF00FF',
        'accent': '#EBFE05',
        'text': '#000000',
        'text_secondary': '#0D0D0D',
        'error': '#FF3D3D',
        'success': '#00FF00',
        'warning': '#FF9900',
        'neon_glow': '0 0 5px',
        'neon_glow_strong': '0 0 10px'
    }
}

# Custom fonts
FONTS = {
    'title': QFont('Rajdhani, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen-Sans, Ubuntu, Cantarell, "Helvetica Neue", sans-serif', 24, QFont.Weight.Bold),
    'heading': QFont('Rajdhani, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen-Sans, Ubuntu, Cantarell, "Helvetica Neue", sans-serif', 18, QFont.Weight.Medium),
    'body': QFont('Rajdhani, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen-Sans, Ubuntu, Cantarell, "Helvetica Neue", sans-serif', 12),
    'mono': QFont('JetBrains Mono, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace', 10)
}

class AnimatedWidget(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.animation = QPropertyAnimation(self, b"windowOpacity")
        self.animation.setDuration(300)
        self.animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        
    def showEvent(self, event):
        self.setWindowOpacity(0)
        self.animation.setStartValue(0)
        self.animation.setEndValue(1)
        self.animation.start()
        super().showEvent(event)

class ThemeToggleButton(QToolButton):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setCheckable(True)
        self.setIcon(QIcon.fromTheme("weather-clear"))
        self.setStyleSheet("""
            QToolButton {
                border: none;
                padding: 5px;
                border-radius: 15px;
            }
            QToolButton:checked {
                background-color: #FFD700;
            }
        """)

class LogDisplay(QScrollArea):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWidgetResizable(True)
        self.text_widget = QLabel()
        self.text_widget.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.text_widget.setWordWrap(True)
        self.text_widget.setStyleSheet("background-color: #f0f0f0; padding: 10px;")
        self.text_widget.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.setWidget(self.text_widget)
        self.log_lines = []
        self.max_lines = 1000

    def append_text(self, text):
        self.log_lines.append(text)
        # Keep only the last max_lines
        if len(self.log_lines) > self.max_lines:
            self.log_lines = self.log_lines[-self.max_lines:]
        self.text_widget.setText("\n".join(self.log_lines))
        # Scroll to bottom
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        
    def event(self, e):
        if e.type() == QAppendTextEvent.EVENT_TYPE:
            self.append_text(e.text)
            return True
        return super().event(e)

class LogHandler(logging.Handler):
    def __init__(self, log_display):
        super().__init__()
        self.log_display = log_display
        self.setFormatter(logging.Formatter('%(levelname)s:%(name)s:%(message)s'))

    def emit(self, record):
        msg = self.format(record)
        # Thread-safe way to append to the log display
        QApplication.instance().postEvent(
            self.log_display,
            QAppendTextEvent(msg)
        )

class QAppendTextEvent(QEvent):
    EVENT_TYPE = QEvent.Type(QEvent.registerEventType())
    
    def __init__(self, text):
        super().__init__(self.EVENT_TYPE)
        self.text = text

class CatalystThread(QThread):
    catalyst_found = pyqtSignal(dict)
    finished = pyqtSignal()
    error = pyqtSignal(str)
    
    def __init__(self, api, discover_mode=False):
        super().__init__()
        self.api = api
        self._is_running = True
        self.discover_mode = discover_mode

    def run(self):
        try:
            logging.info("Starting catalyst fetch...")
            if self.discover_mode:
                logging.info("Running in discovery mode to find new catalysts")
                self.api.discovery_mode = True
            else:
                logging.info("Running in standard mode to show known catalysts")
                self.api.discovery_mode = False
                
            catalysts = self.api.get_catalysts()
            for catalyst in catalysts:
                if not self._is_running:
                    break
                self.catalyst_found.emit(catalyst)
            self.finished.emit()
        except Exception as e:
            logging.error(f"Error fetching catalysts: {e}")
            self.error.emit(str(e))

    def stop(self):
        self._is_running = False

class CatalystWidget(AnimatedWidget):
    def __init__(self, catalyst, theme_toggle, parent=None):
        super().__init__(parent)
        self.catalyst = catalyst
        self.theme_toggle = theme_toggle
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        
        # Create progress bar first
        self.progress_bar = QProgressBar()
        self.progress_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.progress_bar.setMinimumHeight(20)  # Reduced from 30 to be more proportional
        self.progress_bar.setMaximum(100)
        self.progress_bar.setValue(0)
        progress = self.catalyst.get('progress', 0)
        self.progress_bar.setFormat(f"{progress}% Complete")
        
        self.setup_animations()
        self.setup_ui()
        self.update_style()

    def setup_animations(self):
        # Progress bar animation
        self.progress_animation = QPropertyAnimation(self.progress_bar, b"value")
        self.progress_animation.setDuration(1000)
        self.progress_animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        
        # Hover animation
        self.hover_animation = QPropertyAnimation(self, b"geometry")
        self.hover_animation.setDuration(200)
        self.hover_animation.setEasingCurve(QEasingCurve.Type.OutCubic)

    def enterEvent(self, event):
        self.hover_animation.setStartValue(self.geometry())
        self.hover_animation.setEndValue(self.geometry().adjusted(-5, -5, 5, 5))
        self.hover_animation.start()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.hover_animation.setStartValue(self.geometry())
        self.hover_animation.setEndValue(self.geometry().adjusted(5, 5, -5, -5))
        self.hover_animation.start()
        super().leaveEvent(event)

    def update_style(self):
        theme = THEMES['dark' if not self.theme_toggle.isChecked() else 'light']
        self.setStyleSheet(f"""
            QFrame {{
                background-color: {theme['surface']};
                border: 2px solid {theme['accent']};
                border-radius: 10px;
                padding: 20px;
                margin: 8px;
            }}
            QLabel {{
                color: {theme['accent']};
                font-family: 'Rajdhani';
                font-weight: bold;
                font-size: 16px;
                text-transform: uppercase;
                letter-spacing: 2px;
            }}
            QProgressBar {{
                border: 2px solid {theme['accent']};
                border-radius: 5px;
                text-align: center;
                background-color: {theme['background']};
                min-height: 30px;
                max-height: 30px;
                font-size: 14px;
                font-weight: bold;
                color: {theme['text']};
            }}
            QProgressBar::chunk {{
                background-color: {theme['accent']};
                border-radius: 3px;
            }}
        """)

    def setup_ui(self):
        layout = QVBoxLayout()
        layout.setSpacing(10)  # Reduced from 15 to be more compact
        layout.setContentsMargins(15, 15, 15, 15)  # Reduced from 20 to be more compact
        
        # Title with proper sizing
        title = QLabel(self.catalyst.get('name', 'Unknown Catalyst').upper())
        title.setFont(FONTS['heading'])
        title.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        layout.addWidget(title)
        
        # Description with proper wrapping
        desc = QLabel(self.catalyst.get('description', 'No description available').upper())
        desc.setFont(FONTS['body'])
        desc.setWordWrap(True)
        desc.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout.addWidget(desc)
        
        # Progress bar
        layout.addWidget(self.progress_bar)
        
        self.setLayout(layout)
        
        # Animate progress
        progress = self.catalyst.get('progress', 0)
        self.progress_animation.setStartValue(0)
        self.progress_animation.setEndValue(progress)
        self.progress_animation.start()

class CollapsibleGroup(QWidget):
    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setup_ui(title)
        
    def setup_ui(self, title):
        layout = QVBoxLayout(self)
        layout.setSpacing(0)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Header button with dynamic sizing
        self.header = QPushButton(f"▼ {title}")
        self.header.setCheckable(True)
        self.header.setChecked(True)
        self.header.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.header.clicked.connect(self.toggle_content)
        
        # Content widget with dynamic sizing
        self.content = QWidget()
        self.content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setSpacing(10)
        self.content_layout.setContentsMargins(10, 5, 10, 5)  # Reduced vertical margins
        
        layout.addWidget(self.header)
        layout.addWidget(self.content)
        
    def toggle_content(self, checked):
        self.content.setVisible(checked)
        self.header.setText(f"{'▼' if checked else '▶'} {self.header.text()[2:]}")
        
    def add_widget(self, widget):
        self.content_layout.addWidget(widget)

class ControlPanel(QFrame):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent_app = parent
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.setup_ui()
        
        # Connect signals only if parent is provided
        if self.parent_app:
            self.search_bar.textChanged.connect(self.parent_app.search_catalysts)
            self.sort_combo.currentTextChanged.connect(self.parent_app.sort_catalysts)
            
            # Connect filter buttons
            self.filter_buttons[0].setChecked(True)
            for btn in self.filter_buttons:
                btn.clicked.connect(lambda checked, b=btn: self.handle_filter_click(b))

    def handle_filter_click(self, clicked_button):
        # Uncheck other buttons when one is clicked
        for btn in self.filter_buttons:
            if btn != clicked_button:
                btn.setChecked(False)
        
        # Apply filter
        if clicked_button.isChecked():
            self.parent_app.filter_catalysts(clicked_button.text())
        else:
            # If unchecked, check "ALL" button
            self.filter_buttons[0].setChecked(True)
            self.parent_app.filter_catalysts("ALL")

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(10)
        
        # Search bar with neon effect
        search_layout = QHBoxLayout()
        self.search_bar = QLineEdit()
        self.search_bar.setPlaceholderText("SEARCH CATALYSTS...")
        self.search_bar.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        search_layout.addWidget(self.search_bar)
        
        # Sort options with neon styling
        sort_layout = QHBoxLayout()
        sort_label = QLabel("SORT BY:")
        sort_label.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.sort_combo = QComboBox()
        self.sort_combo.addItems(["NAME", "PROGRESS", "WEAPON TYPE"])
        self.sort_combo.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        sort_layout.addWidget(sort_label)
        sort_layout.addWidget(self.sort_combo)
        sort_layout.addStretch()
        
        # Filter toggles with neon effect
        filter_layout = QHBoxLayout()
        filter_label = QLabel("FILTER:")
        filter_label.setStyleSheet(f"color: {THEMES['dark']['text_secondary']};")
        filter_layout.addWidget(filter_label)
        
        self.filter_buttons = []
        for filter_type in ["ALL", "COMPLETED", "IN PROGRESS", "NOT STARTED"]:
            btn = QPushButton(filter_type)
            btn.setCheckable(True)
            btn.setStyleSheet(f"""
                QPushButton {{
                    background-color: {THEMES['dark']['background']};
                    color: {THEMES['dark']['text']};
                    border: 2px solid {THEMES['dark']['secondary']};
                    border-radius: 8px;
                    padding: 5px 10px;
                    font-family: 'Rajdhani';
                    font-size: 12px;
                }}
                QPushButton:checked {{
                    background-color: {THEMES['dark']['secondary']};
                    color: {THEMES['dark']['background']};
                }}
            """)
            filter_layout.addWidget(btn)
            self.filter_buttons.append(btn)
        
        # Progress summary with neon frame
        summary_frame = QFrame()
        summary_frame.setStyleSheet(f"""
            QFrame {{
                background-color: {THEMES['dark']['surface']};
                border: 2px solid {THEMES['dark']['accent']};
                border-radius: 10px;
                padding: 10px;
            }}
        """)
        summary_layout = QHBoxLayout(summary_frame)
        
        # Add progress stats with neon text
        for stat in ["TOTAL", "COMPLETED", "IN PROGRESS"]:
            stat_widget = QWidget()
            stat_layout = QVBoxLayout(stat_widget)
            label = QLabel(stat)
            label.setStyleSheet(f"color: {THEMES['dark']['text_secondary']};")
            value = QLabel("0")
            value.setStyleSheet(f"""
                color: {THEMES['dark']['accent']};
                font-size: 24px;
                font-weight: bold;
            """)
            stat_layout.addWidget(label)
            stat_layout.addWidget(value)
            summary_layout.addWidget(stat_widget)
        
        # Add all layouts to main layout
        layout.addLayout(search_layout)
        layout.addLayout(sort_layout)
        layout.addLayout(filter_layout)
        layout.addWidget(summary_frame)

class DestinyApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Destiny 2 Catalyst Tracker")
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        
        # Initialize variables
        self.api = None
        self.oauth_manager = None
        self.catalyst_thread = None
        self.cached_catalysts = {}
        self.cache_file = "catalyst_cache.json"
        
        # Create theme toggle button first
        self.theme_toggle = ThemeToggleButton()
        self.theme_toggle.toggled.connect(self.toggle_theme)
        self.theme_toggle.setChecked(False)  # Start with dark theme
        
        # Setup UI components
        self.setup_ui()
        self.apply_theme(False)  # Apply initial dark theme
        self.setup_animations()
        
        # Load cache
        self.load_cache()
        
        # Setup timer for periodic updates
        self.update_timer = QTimer()
        self.update_timer.timeout.connect(self.fetch_catalysts)
        self.update_timer.start(300000)  # 5 minutes

    def apply_theme(self, is_light):
        theme = THEMES['light' if is_light else 'dark']
        self.setStyleSheet(f"""
            QMainWindow {{
                background-color: {theme['background']};
            }}
            QPushButton {{
                background-color: {theme['background']};
                color: {theme['primary']};
                border: 2px solid {theme['primary']};
                border-radius: 10px;
                padding: 12px 24px;
                font-family: 'Rajdhani';
                font-size: 16px;
                font-weight: bold;
                text-transform: uppercase;
                letter-spacing: 2px;
            }}
            QPushButton:hover {{
                color: {theme['text']};
                border-color: {theme['secondary']};
                box-shadow: {theme['neon_glow_strong']} {theme['secondary']};
            }}
            QPushButton:pressed {{
                background-color: {theme['secondary']};
                color: {theme['background']};
            }}
            QPushButton:disabled {{
                background-color: {theme['surface']};
                border-color: {theme['text_secondary']};
                color: {theme['text_secondary']};
            }}
            QLabel {{
                color: {theme['text']};
                font-family: 'Rajdhani';
                font-weight: bold;
            }}
            QScrollArea {{
                border: none;
                background: transparent;
            }}
            QScrollBar:vertical {{
                border: none;
                background: {theme['surface']};
                width: 10px;
                border-radius: 5px;
            }}
            QScrollBar::handle:vertical {{
                background: {theme['primary']};
                border-radius: 5px;
            }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
                border: none;
                background: none;
            }}
            QWidget#central {{
                background-color: {theme['background']};
            }}
        """)

    def toggle_theme(self, checked):
        """Toggle between light and dark themes"""
        self.apply_theme(checked)
        # Update catalyst widgets if they exist
        if hasattr(self, 'catalysts_widget') and self.catalysts_widget.layout():
            for i in range(self.catalysts_widget.layout().count()):
                widget = self.catalysts_widget.layout().itemAt(i).widget()
                if isinstance(widget, CatalystWidget):
                    widget.update_style()
        
        # Update log display theme
        theme = THEMES['light' if checked else 'dark']
        self.log_display.text_widget.setStyleSheet(f"""
            QLabel {{
                background-color: {theme['surface']};
                color: {theme['text']};
                padding: 15px;
                font-family: 'JetBrains Mono';
                font-size: 13px;
                border: 2px solid {theme['primary']};
                border-radius: 10px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
        """)

    def setup_animations(self):
        # Window fade in animation
        self.window_animation = QPropertyAnimation(self, b"windowOpacity")
        self.window_animation.setDuration(500)
        self.window_animation.setStartValue(0)
        self.window_animation.setEndValue(1)
        self.window_animation.start()

    def setup_ui(self):
        # Main widget and layout
        main_widget = QWidget()
        main_widget.setObjectName("central")
        self.setCentralWidget(main_widget)
        layout = QVBoxLayout(main_widget)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(15)
        
        # Top bar with neon buttons
        top_bar = QHBoxLayout()
        top_bar.setSpacing(15)
        
        # Auth button with neon effect
        self.auth_button = QPushButton("AUTHENTICATE WITH BUNGIE")
        self.auth_button.clicked.connect(self.authenticate)
        self.auth_button.setMinimumHeight(45)
        self.auth_button.setMinimumWidth(300)
        self.auth_button.setFont(FONTS['body'])
        self.auth_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {THEMES['dark']['background']};
                color: {THEMES['dark']['primary']};
                border: 2px solid {THEMES['dark']['primary']};
                border-radius: 10px;
            }}
        """)
        
        # Discovery mode button with neon effect
        self.discover_button = QPushButton("DISCOVERY MODE")
        self.discover_button.clicked.connect(self.toggle_discovery_mode)
        self.discover_button.setCheckable(True)
        self.discover_button.setMinimumHeight(45)
        self.discover_button.setMinimumWidth(200)
        self.discover_button.setFont(FONTS['body'])
        self.discover_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {THEMES['dark']['background']};
                color: {THEMES['dark']['secondary']};
                border: 2px solid {THEMES['dark']['secondary']};
                border-radius: 10px;
            }}
            QPushButton:checked {{
                background-color: {THEMES['dark']['secondary']};
                color: {THEMES['dark']['background']};
            }}
        """)
        
        top_bar.addWidget(self.auth_button)
        top_bar.addWidget(self.discover_button)
        top_bar.addStretch()
        
        # Enhanced theme toggle with neon border
        self.theme_toggle.setMinimumSize(45, 45)
        self.theme_toggle.setStyleSheet("""
            QToolButton {
                background-color: #0D0D0D;
                border: 2px solid #EBFE05;
                border-radius: 22px;
                padding: 5px;
            }
            QToolButton:checked {
                background-color: #EBFE05;
                border-color: #FF0099;
            }
        """)
        top_bar.addWidget(self.theme_toggle)
        
        layout.addLayout(top_bar)
        
        # Control panel
        self.control_panel = ControlPanel(self)
        layout.addWidget(self.control_panel)
        
        # Create splitter with neon handle
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.splitter.setStyleSheet("""
            QSplitter::handle {
                height: 2px;
                background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                    stop:0 #EBFE05, stop:1 #FF0099);
            }
        """)
        
        # Scroll area with custom scrollbar
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background: transparent;
            }
            QScrollBar:vertical {
                border: none;
                background: #1A1A1A;
                width: 10px;
                border-radius: 5px;
            }
            QScrollBar::handle:vertical {
                background: #EBFE05;
                border-radius: 5px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                border: none;
                background: none;
            }
        """)
        
        # Catalysts container
        self.catalysts_widget = QWidget()
        catalysts_layout = QVBoxLayout(self.catalysts_widget)
        catalysts_layout.setSpacing(10)
        catalysts_layout.setContentsMargins(10, 10, 10, 10)
        catalysts_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll_area.setWidget(self.catalysts_widget)
        
        # Log display with neon border
        self.log_display = LogDisplay()
        self.log_display.setMinimumHeight(150)
        self.log_display.text_widget.setStyleSheet(f"""
            QLabel {{
                background-color: {THEMES['dark']['background']};
                color: {THEMES['dark']['text_secondary']};
                padding: 15px;
                font-family: 'JetBrains Mono';
                font-size: 13px;
                border: 2px solid {THEMES['dark']['text_secondary']};
                border-radius: 10px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
        """)
        
        self.splitter.addWidget(scroll_area)
        self.splitter.addWidget(self.log_display)
        layout.addWidget(self.splitter)
        
        # Status bar with neon styling
        status_bar = QWidget()
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(10, 10, 10, 10)
        status_layout.setSpacing(15)
        
        self.status_label = QLabel("Please authenticate to continue")
        self.status_label.setStyleSheet(f"""
            QLabel {{
                color: {THEMES['dark']['accent']};
                font-size: 16px;
                font-weight: bold;
                padding: 10px;
                background-color: {THEMES['dark']['background']};
                border: 2px solid {THEMES['dark']['accent']};
                border-radius: 10px;
                text-transform: uppercase;
                letter-spacing: 2px;
            }}
        """)
        
        # Cache checkbox with neon styling
        self.use_cache_checkbox = QCheckBox("Use cached data")
        self.use_cache_checkbox.setChecked(True)
        self.use_cache_checkbox.setStyleSheet(f"""
            QCheckBox {{
                color: {THEMES['dark']['accent']};
                font-size: 14px;
                font-weight: bold;
                padding: 5px;
                text-transform: uppercase;
                letter-spacing: 1px;
            }}
            QCheckBox::indicator {{
                width: 20px;
                height: 20px;
                border-radius: 5px;
                border: 2px solid {THEMES['dark']['accent']};
            }}
            QCheckBox::indicator:checked {{
                background-color: {THEMES['dark']['accent']};
            }}
            QCheckBox::indicator:unchecked {{
                background-color: {THEMES['dark']['background']};
            }}
        """)
        
        # Refresh button with neon styling
        self.refresh_button = QPushButton("REFRESH CATALYSTS")
        self.refresh_button.setDisabled(True)
        self.refresh_button.setMinimumHeight(45)
        self.refresh_button.setMinimumWidth(200)
        self.refresh_button.setFont(FONTS['body'])
        self.refresh_button.setStyleSheet(f"""
            QPushButton {{
                background-color: {THEMES['dark']['background']};
                color: {THEMES['dark']['secondary']};
                border: 2px solid {THEMES['dark']['secondary']};
                border-radius: 10px;
            }}
            QPushButton:disabled {{
                background-color: {THEMES['dark']['surface']};
                border-color: {THEMES['dark']['text_secondary']};
                color: {THEMES['dark']['text_secondary']};
            }}
        """)
        
        status_layout.addWidget(self.status_label, 1)
        status_layout.insertWidget(1, self.use_cache_checkbox)
        status_layout.addWidget(self.refresh_button)
        
        layout.addWidget(status_bar)
        
        # Configure logging
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            
        log_handler = LogHandler(self.log_display)
        root_logger.addHandler(log_handler)
        
        self.splitter.setSizes([400, 200])
        
        # Load cached catalysts if available
        self.load_cache()

    def load_cache(self):
        """Load cached catalyst data from file if it exists"""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r') as f:
                    cache_data = json.load(f)
                    
                # Check if cache is still valid (less than 1 day old)
                cache_time = datetime.fromisoformat(cache_data.get('timestamp', '2000-01-01'))
                if datetime.now() - cache_time < timedelta(days=1):
                    self.cached_catalysts = cache_data.get('catalysts', {})
                    logging.info(f"Loaded {len(self.cached_catalysts)} catalysts from cache")
                else:
                    logging.info("Cache is older than 1 day, will fetch fresh data")
        except Exception as e:
            logging.error(f"Error loading cache: {e}")
            self.cached_catalysts = {}

    def save_cache(self, catalysts):
        """Save catalyst data to cache file"""
        try:
            # Convert list of catalysts to dictionary with hash as key
            catalyst_dict = {str(c.get('recordHash')): c for c in catalysts if 'recordHash' in c}
            
            cache_data = {
                'timestamp': datetime.now().isoformat(),
                'catalysts': catalyst_dict
            }
            
            with open(self.cache_file, 'w') as f:
                json.dump(cache_data, f)
                
            logging.info(f"Saved {len(catalyst_dict)} catalysts to cache")
        except Exception as e:
            logging.error(f"Error saving cache: {e}")

    def authenticate(self):
        """Authenticate with Bungie.net"""
        self.status_label.setText("Authenticating with Bungie.net...")
        logging.info("Starting authentication process...")
        
        # Initialize OAuthManager
        from bungie_oauth import OAuthManager
        
        api_key = os.environ.get("BUNGIE_API_KEY", "")
        if not api_key:
            error_msg = "BUNGIE_API_KEY environment variable not set"
            logging.error(error_msg)
            self.status_label.setText(error_msg)
            return
            
        logging.info("API key found, initializing OAuth manager...")
        self.oauth_manager = OAuthManager()
        
        # Start authentication process
        try:
            logging.info("Starting OAuth flow...")
            token_data = self.oauth_manager.start_auth(
                auth_code_callback=lambda code: logging.info(f"Received auth code: {code}"),
                error_callback=lambda error: logging.error(f"Auth error: {error}")
            )
            
            if not token_data:
                error_msg = "Authentication failed. Please try again."
                logging.error("No token data received from OAuth manager")
                self.status_label.setText(error_msg)
                return
                
            logging.info("Authentication successful, received token data")
            self.status_label.setText("Authentication successful! Fetching catalysts...")
            
            # Enable mode selection and refresh button
            logging.info("Enabling UI controls...")
            self.discover_button.setEnabled(True)
            self.refresh_button.setEnabled(True)
            self.auth_button.setEnabled(False)
            
            # Initialize catalyst API with token
            logging.info("Initializing Catalyst API...")
            self.api = CatalystAPI(api_key, token_data["access_token"])
            
            # Start fetching catalysts
            logging.info("Starting catalyst fetch...")
            self.fetch_catalysts()
            
        except Exception as e:
            error_msg = f"Authentication error: {str(e)}"
            logging.error(error_msg, exc_info=True)  # This will log the full stack trace
            self.status_label.setText(error_msg)
        finally:
            # Clean up OAuth server
            if self.oauth_manager and self.oauth_manager.server:
                logging.info("Stopping OAuth server...")
                self.oauth_manager.stop_server()

    def fetch_catalysts(self):
        """Fetch and display catalysts"""
        if not self.api:
            self.status_label.setText("Please authenticate first")
            return
            
        # Clear existing catalysts
        while self.catalysts_widget.layout().count():
            item = self.catalysts_widget.layout().takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        root_logger.info("Starting catalyst fetch in desktop app...")
        self.status_label.setText("Fetching catalysts...")
        
        # Check if we should use cached data
        discover_mode = self.discover_button.isChecked()
        use_cache = self.use_cache_checkbox.isChecked() and not discover_mode
        
        if use_cache and self.cached_catalysts:
            # If we have cached data and user wants to use it, display from cache
            logging.info("Using cached catalyst data")
            catalysts = list(self.cached_catalysts.values())
            # Sort catalysts by completion status and name
            catalysts.sort(key=lambda c: (c.get('complete', False), c.get('name', '')))
            for catalyst in catalysts:
                self.handle_catalyst_found(catalyst)
            self.handle_catalysts_finished()
            return
        
        # Create and start catalyst thread
        root_logger.info("Creating catalyst thread...")
        if self.catalyst_thread and self.catalyst_thread.isRunning():
            self.catalyst_thread.stop()
            self.catalyst_thread.wait()
            
        self.catalyst_thread = CatalystThread(self.api, discover_mode)
        self.catalyst_thread.catalyst_found.connect(self.handle_catalyst_found)
        self.catalyst_thread.finished.connect(self.handle_catalysts_finished)
        self.catalyst_thread.error.connect(self.handle_catalysts_error)
        
        root_logger.info("Starting catalyst thread...")
        self.catalyst_thread.start()

    def handle_catalyst_found(self, catalyst_data):
        """Handle found catalyst"""
        is_discovered = catalyst_data.get('discovered', False)
        status_text = " [DISCOVERED]" if is_discovered else ""
        root_logger.info(f"Found catalyst: {catalyst_data['name']}{status_text}")
        
        widget = CatalystWidget(catalyst_data, self.theme_toggle)
        
        # Get or create weapon type group
        weapon_type = catalyst_data.get('weaponType', 'Unknown')
        group = self.get_or_create_weapon_group(weapon_type)
        group.add_widget(widget)
        
        # Add to collected catalysts for caching
        if 'recordHash' in catalyst_data and (not is_discovered or self.discover_button.isChecked()):
            self.cached_catalysts[str(catalyst_data['recordHash'])] = catalyst_data
            
        # Update progress summary
        self.update_progress_summary()

    def get_or_create_weapon_group(self, weapon_type):
        """Get existing weapon type group or create new one"""
        # Look for existing group
        layout = self.catalysts_widget.layout()
        for i in range(layout.count()):
            widget = layout.itemAt(i).widget()
            if isinstance(widget, CollapsibleGroup) and widget.header.text()[2:] == weapon_type:
                return widget
        
        # Create new group if not found
        group = CollapsibleGroup(weapon_type)
        layout.addWidget(group)
        return group

    def handle_catalysts_finished(self):
        """Handle finished catalyst fetch"""
        mode_text = "discovery" if self.discover_button.isChecked() else "standard"
        root_logger.info(f"Catalyst fetch complete in {mode_text} mode")
        
        # Save catalysts to cache (even in discovery mode to remember found items)
        self.save_cache(list(self.cached_catalysts.values()))
        
        # Show count in status bar
        count = self.catalysts_widget.layout().count()
        self.status_label.setText(f"Found {count} catalysts in {mode_text} mode")

    def handle_catalysts_error(self, error):
        """Handle catalyst fetch error"""
        root_logger.error(f"Error fetching catalysts in desktop app: {error}")
        self.status_label.setText(f"Error fetching catalysts: {error}")

    def toggle_discovery_mode(self):
        """Toggle between discovery mode and standard mode"""
        self.use_cache_checkbox.setEnabled(False)
        self.use_cache_checkbox.setChecked(False)
        logging.info("Switched to discovery mode - cache disabled")
        
        # If we already have an API, refresh catalysts when mode changes
        if self.api and self.isVisible():
            self.fetch_catalysts()

    def update_progress_summary(self):
        """Update the progress summary stats"""
        total = len(self.cached_catalysts)
        completed = sum(1 for c in self.cached_catalysts.values() if c.get('progress', 0) == 100)
        in_progress = sum(1 for c in self.cached_catalysts.values() if 0 < c.get('progress', 0) < 100)
        
        # Update the labels in the control panel
        summary_frame = self.control_panel.findChild(QFrame)
        if summary_frame:
            stats = summary_frame.findChildren(QLabel)
            value_labels = [s for s in stats if s.text().isdigit() or s.text() == '0']
            if len(value_labels) >= 3:
                value_labels[0].setText(str(total))
                value_labels[1].setText(str(completed))
                value_labels[2].setText(str(in_progress))

    def filter_catalysts(self, filter_type):
        """Filter catalysts based on progress"""
        layout = self.catalysts_widget.layout()
        for i in range(layout.count()):
            group = layout.itemAt(i).widget()
            if isinstance(group, CollapsibleGroup):
                content_layout = group.content_layout
                visible_count = 0
                
                for j in range(content_layout.count()):
                    widget = content_layout.itemAt(j).widget()
                    if isinstance(widget, CatalystWidget):
                        progress = widget.catalyst.get('progress', 0)
                        visible = True
                        
                        if filter_type == "COMPLETED":
                            visible = progress == 100
                        elif filter_type == "IN PROGRESS":
                            visible = 0 < progress < 100
                        elif filter_type == "NOT STARTED":
                            visible = progress == 0
                        
                        widget.setVisible(visible)
                        if visible:
                            visible_count += 1
                
                # Hide group if no visible catalysts
                group.setVisible(visible_count > 0 or filter_type == "ALL")
    
    def search_catalysts(self, search_text):
        """Search catalysts by name"""
        search_text = search_text.lower()
        layout = self.catalysts_widget.layout()
        
        for i in range(layout.count()):
            group = layout.itemAt(i).widget()
            if isinstance(group, CollapsibleGroup):
                content_layout = group.content_layout
                visible_count = 0
                
                for j in range(content_layout.count()):
                    widget = content_layout.itemAt(j).widget()
                    if isinstance(widget, CatalystWidget):
                        name = widget.catalyst.get('name', '').lower()
                        visible = search_text in name
                        widget.setVisible(visible)
                        if visible:
                            visible_count += 1
                
                # Hide group if no visible catalysts
                group.setVisible(visible_count > 0)
    
    def sort_catalysts(self, sort_by):
        """Sort catalysts by the selected criteria"""
        layout = self.catalysts_widget.layout()
        groups = []
        
        # Collect all groups
        while layout.count():
            group = layout.takeAt(0).widget()
            if group:
                groups.append(group)
        
        # Sort groups by name
        groups.sort(key=lambda g: g.header.text()[2:])
        
        # Sort catalysts within each group
        for group in groups:
            content_layout = group.content_layout
            widgets = []
            
            while content_layout.count():
                widget = content_layout.takeAt(0).widget()
                if widget:
                    widgets.append(widget)
            
            if sort_by == "NAME":
                widgets.sort(key=lambda w: w.catalyst.get('name', ''))
            elif sort_by == "PROGRESS":
                widgets.sort(key=lambda w: w.catalyst.get('progress', 0), reverse=True)
            
            for widget in widgets:
                content_layout.addWidget(widget)
        
        # Add sorted groups back to layout
        for group in groups:
            layout.addWidget(group)

def main():
    app = QApplication(sys.argv)
    window = DestinyApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 