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
from catalyst_db import CatalystDB

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
    'title': QFont('Rajdhani, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif', 24, QFont.Weight.Bold),
    'heading': QFont('Rajdhani, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif', 18, QFont.Weight.Medium),
    'body': QFont('Rajdhani, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif', 12),
    'mono': QFont('"JetBrains Mono", Consolas, Monaco, "Courier New", monospace', 10)
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
        
        # Calculate progress from objectives
        progress = self.calculate_progress()
        self.progress_bar.setFormat(f"{progress}% Complete")
        
        self.setup_animations()
        self.setup_ui()
        self.update_style()

    def calculate_progress(self):
        """Calculate overall progress from objectives"""
        objectives = self.catalyst.get('objectives', [])
        if not objectives:
            return 0
        
        total_progress = 0
        for obj in objectives:
            if obj.get('completion', 0) > 0:
                progress = (obj.get('progress', 0) / obj.get('completion', 1)) * 100
                total_progress += progress
        
        return min(round(total_progress / len(objectives), 1), 100)

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
        
        # Add objectives list
        objectives = self.catalyst.get('objectives', [])
        if objectives:
            obj_container = QWidget()
            obj_layout = QVBoxLayout(obj_container)
            obj_layout.setSpacing(5)
            obj_layout.setContentsMargins(0, 0, 0, 0)
            
            for obj in objectives:
                obj_text = QLabel(obj.get('description', '').upper())
                obj_text.setFont(FONTS['body'])
                obj_text.setWordWrap(True)
                obj_text.setStyleSheet("font-size: 11px;")
                obj_layout.addWidget(obj_text)
                
                # Add individual progress bar for objective
                if obj.get('completion', 0) > 0:
                    obj_progress = QProgressBar()
                    obj_progress.setMaximum(100)
                    progress = (obj.get('progress', 0) / obj.get('completion', 1)) * 100
                    obj_progress.setValue(int(progress))
                    obj_progress.setFormat(f"{obj.get('progress', 0)}/{obj.get('completion', 1)} ({progress:.1f}%)")
                    obj_progress.setMinimumHeight(15)
                    obj_layout.addWidget(obj_progress)
            
            layout.addWidget(obj_container)
        
        # Overall progress bar
        layout.addWidget(self.progress_bar)
        
        self.setLayout(layout)
        
        # Animate progress
        progress = self.calculate_progress()
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
        self.current_theme = 'dark'
        self.setWindowTitle("Destiny 2 Catalyst Tracker")
        self.setMinimumSize(800, 600)
        
        # Initialize theme toggle first
        self.theme_toggle = ThemeToggleButton()
        self.theme_toggle.toggled.connect(self.toggle_theme)
        
        self.oauth = OAuthManager()
        self.api = CatalystAPI(self.oauth)
        self.catalyst_thread = None
        self.discovered_catalysts = {}
        self.weapon_groups = {}
        self.control_panel = None

        # Initialize database
        self.db = CatalystDB()
        
        # Center and maximize window
        self.setGeometry(100, 100, 1200, 800)  # Set initial size
        self.centerWindow()
        self.showMaximized()  # This will use the macOS maximize behavior
        
        # Apply initial theme and setup UI
        self.apply_theme(is_light=False)
        self.setup_animations()
        self.setup_ui()
        
        # Load cached data if available (after UI setup)
        self.load_cache()

        # Attempt to validate token (doesn't trigger fetch anymore)
        self._check_initial_auth_status()

    def centerWindow(self):
        """Center the window on the screen"""
        screen = QApplication.primaryScreen().geometry()
        size = self.geometry()
        x = (screen.width() - size.width()) // 2
        y = (screen.height() - size.height()) // 2
        self.move(x, y)
        
    def load_cache(self):
        """Load data from database and populate the UI if valid."""
        try:
            # Get all catalysts from database
            catalysts = self.db.get_all_catalysts()
            if catalysts:
                self.discovered_catalysts = {str(cat['recordHash']): cat for cat in catalysts}
                logging.info(f"Loaded {len(catalysts)} catalysts from database")
                
                # Update UI with loaded data
                self.clear_catalyst_display()
                for catalyst in catalysts:
                    self.handle_catalyst_found(catalyst)
                self.update_progress_summary()
        except Exception as e:
            logging.error(f"Error loading from database: {e}")

    def populate_ui_from_discovered_data(self):
        """Clears and refills the UI based on self.discovered_catalysts."""
        self.clear_catalyst_display()
        logging.info(f"Populating UI with {len(self.discovered_catalysts)} catalysts...")
        # Sort catalysts before displaying (e.g., by name)
        # Note: Sorting dict values requires getting items and sorting based on a key
        sorted_catalysts = sorted(self.discovered_catalysts.values(), key=lambda c: c.get('name', ''))
        
        for catalyst_data in sorted_catalysts:
            # Replicate the core logic of handle_catalyst_found for UI population
            widget = CatalystWidget(catalyst_data, self.theme_toggle)
            weapon_type = catalyst_data.get('weaponType', 'Unknown')
            group = self.get_or_create_weapon_group(weapon_type)
            group.add_widget(widget)
            
        self.update_progress_summary()
        logging.info("Finished populating UI from data.")

    def _check_initial_auth_status(self):
        """Check for existing valid token on startup."""
        try:
            self.oauth.get_headers()
            logging.info("Successfully validated existing token on startup.")
            self._update_auth_state(authenticated=True)
        except Exception as e:
            logging.warning(f"Initial token validation failed: {e}. User needs to authenticate.")
            self._update_auth_state(authenticated=False)

    def _update_auth_state(self, authenticated: bool):
        """Update UI elements based on authentication status."""
        if authenticated:
            logging.info("Authentication successful. Enabling authenticated features.")
            if self.auth_button:
                self.auth_button.setEnabled(False)
                self.auth_button.setText("Authenticated")
            if self.fetch_button:
                self.fetch_button.setEnabled(True)
            if self.discover_button:
                self.discover_button.setEnabled(True)
            if self.control_panel:
                 self.control_panel.setEnabled(True)
            # REMOVED: self.fetch_catalysts() - Don't fetch automatically here anymore
        else:
            logging.info("Authentication needed. Enabling authentication button.")
            if self.auth_button:
                self.auth_button.setEnabled(True)
                self.auth_button.setText("Authenticate with Bungie")
            if self.fetch_button:
                self.fetch_button.setEnabled(False)
            if self.discover_button:
                self.discover_button.setEnabled(False)
            if self.control_panel:
                 self.control_panel.setEnabled(False)
            # Optionally clear display if auth fails *after* cache was shown?
            # self.clear_catalyst_display() 
            # self.update_progress_summary()

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
        main_layout = QVBoxLayout(main_widget)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(15)
        
        # Top bar with neon buttons
        top_bar_widget = QFrame()
        top_bar_layout = QHBoxLayout(top_bar_widget)
        top_bar_layout.setContentsMargins(10, 5, 10, 5) # Reduced vertical margins

        # Title Label (Optional, if needed)
        # title_label = QLabel("Destiny 2 Catalyst Tracker")
        # title_label.setFont(FONTS['heading']) 
        # top_bar_layout.addWidget(title_label)

        # Spacer
        top_bar_layout.addStretch(1)

        # Authentication Button
        self.auth_button = QPushButton("Authenticate with Bungie")
        self.auth_button.setFont(FONTS['body'])
        self.auth_button.setIcon(QIcon.fromTheme("security-high")) # Example icon
        self.auth_button.setToolTip("Authenticate with Bungie.net to fetch your catalyst data")
        self.auth_button.clicked.connect(self.authenticate)
        self.auth_button.setEnabled(True) # Start enabled, will be updated by _update_auth_state
        top_bar_layout.addWidget(self.auth_button)

        # Fetch Button
        self.fetch_button = QPushButton("Fetch Catalysts")
        self.fetch_button.setFont(FONTS['body'])
        self.fetch_button.setIcon(QIcon.fromTheme("view-refresh")) # Example icon
        self.fetch_button.setToolTip("Fetch the latest catalyst progress")
        self.fetch_button.clicked.connect(self.fetch_catalysts)
        self.fetch_button.setEnabled(False) # Start disabled until authenticated
        top_bar_layout.addWidget(self.fetch_button)
        
        # Discovery Mode Button
        self.discover_button = QPushButton("Discover New")
        self.discover_button.setFont(FONTS['body'])
        self.discover_button.setIcon(QIcon.fromTheme("system-search")) # Example icon
        self.discover_button.setCheckable(True)
        self.discover_button.setToolTip("Run in discovery mode to find potentially new/missing catalysts (slower)")
        self.discover_button.clicked.connect(self.toggle_discovery_mode)
        self.discover_button.setEnabled(False) # Start disabled until authenticated
        top_bar_layout.addWidget(self.discover_button)

        # Theme Toggle Button
        self.theme_toggle = ThemeToggleButton()
        self.theme_toggle.toggled.connect(self.toggle_theme)
        top_bar_layout.addWidget(self.theme_toggle)

        main_layout.addWidget(top_bar_widget) # Add top bar to main layout

        # --- Control Panel ---
        self.control_panel = ControlPanel(self)
        self.control_panel.search_bar.textChanged.connect(self.search_catalysts)
        self.control_panel.sort_combo.currentTextChanged.connect(self.sort_catalysts)
        # Connect filter buttons (Iterate directly over the list)
        for btn in self.control_panel.filter_buttons:
            btn.clicked.connect(lambda checked, b=btn: self.control_panel.handle_filter_click(b))
        self.control_panel.filter_buttons[0].setChecked(True) # Corrected access
        self.control_panel.setEnabled(False) # Start disabled until authenticated
        main_layout.addWidget(self.control_panel)

        # --- Catalyst Scroll Area ---
        # Splitter for scroll area and log display
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        # Apply theme styles later in apply_theme if needed

        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        scroll_area.setObjectName("catalystScrollArea")
        # Apply theme styles later

        # Use self.catalyst_scroll_content as the container for groups
        self.catalyst_scroll_content = QWidget()
        self.catalyst_layout = QVBoxLayout(self.catalyst_scroll_content)
        self.catalyst_layout.setSpacing(5) # Reduced spacing between groups
        self.catalyst_layout.setContentsMargins(5, 5, 5, 5) # Reduced margins
        self.catalyst_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll_area.setWidget(self.catalyst_scroll_content)

        # --- Log Display ---
        self.log_display = LogDisplay()
        self.log_display.setMinimumHeight(100) # Reduced minimum height
        self.log_display.setObjectName("logDisplay")
        # Apply theme styles later

        self.splitter.addWidget(scroll_area)
        self.splitter.addWidget(self.log_display)
        self.splitter.setStretchFactor(0, 3) # Give more space to catalysts initially
        self.splitter.setStretchFactor(1, 1)
        # Use main_layout here as well
        main_layout.addWidget(self.splitter) 

        # Configure logging handler to use the log display
        log_handler = LogHandler(self.log_display)
        formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s', datefmt='%H:%M:%S')
        log_handler.setFormatter(formatter)
        # Add handler only if not already added
        if not any(isinstance(h, LogHandler) for h in root_logger.handlers):
             root_logger.addHandler(log_handler)

    def save_cache(self):
        """Save current catalyst data to database."""
        try:
            # Store each catalyst in the database
            for catalyst in self.discovered_catalysts.values():
                self.db.store_catalyst(catalyst)
            logging.info(f"Saved {len(self.discovered_catalysts)} catalysts to database")
        except Exception as e:
            logging.error(f"Error saving to database: {e}")

    def authenticate(self):
        """Initiate the Bungie OAuth flow when the button is clicked."""
        logging.info("Authentication button clicked, starting OAuth flow...")
        try:
            # Start the authentication flow (blocking)
            token_data = self.oauth.start_auth() 
            
            if token_data:
                logging.info("Manual authentication successful via button.")
                self._update_auth_state(authenticated=True)
            else:
                # Auth failed or was cancelled by user closing browser etc.
                logging.warning("Manual authentication failed or was cancelled.")
                self._update_auth_state(authenticated=False) 
                QMessageBox.warning(self, "Authentication Failed", 
                                     "Could not authenticate with Bungie. Please check logs and ensure you complete the browser step.")
        except Exception as e:
            logging.error(f"Error during manual authentication: {e}", exc_info=True)
            self._update_auth_state(authenticated=False)
            QMessageBox.critical(self, "Authentication Error", 
                                  f"An unexpected error occurred during authentication: {e}")

    def fetch_catalysts(self):
        """Fetch catalyst data using a background thread (triggered by button)."""
        if self.catalyst_thread and self.catalyst_thread.isRunning():
            logging.warning("Catalyst fetch already in progress.")
            return
            
        # Clear previous results visually *before* fetching when manually triggered
        self.clear_catalyst_display() 
        self.update_progress_summary() # Reset summary to zero while fetching
        # Clear the internal data dict as well, so handle_catalyst_found repopulates it cleanly
        self.discovered_catalysts.clear() 

        logging.info("Manual catalyst fetch triggered by button.")
        try:
            self.oauth.get_headers() 
        except Exception as e:
             logging.error(f"Cannot fetch catalysts: Authentication issue - {e}")
             QMessageBox.critical(self, "Authentication Error", f"Cannot fetch catalysts. Please re-authenticate.\nError: {e}")
             self._update_auth_state(authenticated=False)
             return

        # Use discovery mode based on button state
        discovery_mode = self.discover_button.isChecked()

        self.catalyst_thread = CatalystThread(self.api, discover_mode=discovery_mode)
        self.catalyst_thread.catalyst_found.connect(self.handle_catalyst_found)
        self.catalyst_thread.finished.connect(self.handle_catalysts_finished)
        self.catalyst_thread.error.connect(self.handle_catalysts_error)
        
        self.fetch_button.setText("Fetching...")
        self.fetch_button.setEnabled(False)
        self.discover_button.setEnabled(False)
        self.control_panel.setEnabled(False)
        self.catalyst_thread.start()

    def clear_catalyst_display(self):
        """Removes all catalyst widgets and group widgets from the layout."""
        # Clear existing groups first
        for group_widget in list(self.weapon_groups.values()):
            group_widget.setParent(None)
            group_widget.deleteLater()
        self.weapon_groups.clear()
        self.discovered_catalysts.clear()
        
        # Clear database
        try:
            self.db.clear_old_data(max_age_days=0)  # Clear all data
        except Exception as e:
            logging.error(f"Error clearing database: {e}")

    def handle_catalyst_found(self, catalyst_data):
        """Handle found catalyst"""
        is_discovered = catalyst_data.get('discovered', False)
        status_text = " [DISCOVERED]" if is_discovered else ""
        catalyst_name = catalyst_data.get('name', 'Unknown')
        logging.info(f"Found catalyst: {catalyst_name}{status_text}")
        
        # Ensure hash exists before proceeding
        record_hash = catalyst_data.get('recordHash')
        if not record_hash:
            logging.warning(f"Skipping catalyst without recordHash: {catalyst_name}")
            return

        record_hash_str = str(record_hash)

        # Update internal dictionary
        self.discovered_catalysts[record_hash_str] = catalyst_data

        # Store in database
        try:
            self.db.store_catalyst(catalyst_data)
        except Exception as e:
            logging.error(f"Error storing catalyst {catalyst_name} in database: {e}")

        # Create or update widget
        widget = CatalystWidget(catalyst_data, self.theme_toggle)
        
        # Get or create weapon type group
        weapon_type = catalyst_data.get('weaponType', 'Unknown')
        group = self.get_or_create_weapon_group(weapon_type)
        group.add_widget(widget)
            
        # Update progress summary
        self.update_progress_summary()

    def get_or_create_weapon_group(self, weapon_type):
        """Get existing weapon type group or create new one"""
        # Look for existing group
        layout = self.catalyst_layout
        for i in range(layout.count()):
            widget = layout.itemAt(i).widget()
            if isinstance(widget, CollapsibleGroup) and widget.header.text()[2:] == weapon_type:
                return widget
        
        # Create new group if not found
        group = CollapsibleGroup(weapon_type)
        layout.addWidget(group)
        return group

    def handle_catalysts_finished(self):
        logging.info("Catalyst fetch finished.")
        self.fetch_button.setText("Fetch Catalysts")
        # Re-enable buttons based on auth state (should still be true)
        is_authenticated = False
        try:
            self.oauth.get_headers()
            is_authenticated = True
        except:
            is_authenticated = False
        
        if is_authenticated:
             self.fetch_button.setEnabled(True)
             self.discover_button.setEnabled(True)
             self.control_panel.setEnabled(True) # Re-enable controls
        else:
             self._update_auth_state(authenticated=False) # Update if auth somehow failed

        # Save cache after successful fetch (now saves discovered_catalysts)
        self.save_cache()
        
        # Update summary after loading/fetching is complete
        self.update_progress_summary()

    def handle_catalysts_error(self, error):
        logging.error(f"Error received from catalyst thread: {error}")
        self.fetch_button.setText("Fetch Catalysts")
        QMessageBox.critical(self, "Fetch Error", f"Could not fetch catalyst data:\n{error}")
        # Check auth state again after error
        is_authenticated = False
        try:
            self.oauth.get_headers()
            is_authenticated = True
        except Exception as auth_e:
            logging.warning(f"Authentication check failed after fetch error: {auth_e}")
            is_authenticated = False

        if is_authenticated:
             self.fetch_button.setEnabled(True)
             self.discover_button.setEnabled(True)
             self.control_panel.setEnabled(True) # Re-enable controls
        else:
             # If authentication failed, update UI state
             self._update_auth_state(authenticated=False)

    def toggle_discovery_mode(self):
        """Toggle between discovery mode and standard mode"""
        self.use_cache_checkbox.setEnabled(False)
        self.use_cache_checkbox.setChecked(False)
        logging.info("Switched to discovery mode - cache disabled")
        
        # If we already have an API, refresh catalysts when mode changes
        if self.api and self.isVisible():
            self.fetch_catalysts()

    def update_progress_summary(self):
        """Update the progress summary stats using discovered_catalysts."""
        # Use self.discovered_catalysts now
        catalysts_data = self.discovered_catalysts.values()
        total = len(catalysts_data)
        completed = sum(1 for c in catalysts_data if c.get('complete', False)) # Use 'complete' flag
        # Calculate in_progress based on objectives within each catalyst
        in_progress = 0
        for c in catalysts_data:
            if not c.get('complete', False):
                 has_progress = False
                 objectives = c.get('objectives', [])
                 if objectives:
                      # Check if *any* objective has progress but is not complete
                      for obj in objectives:
                           if 0 < obj.get('progress', 0) < obj.get('completion', 1):
                                has_progress = True
                                break
                 if has_progress:
                      in_progress += 1
            
        # Update the labels in the control panel
        summary_frame = self.control_panel.findChild(QFrame)
        if summary_frame:
            # Find labels more reliably (maybe by object name?)
            # Assuming order for now:
            value_labels = summary_frame.findChildren(QLabel)[1::2] # Get every second label (the values)
            if len(value_labels) >= 3:
                value_labels[0].setText(str(total))
                value_labels[1].setText(str(completed))
                value_labels[2].setText(str(in_progress))
            else:
                logging.warning("Could not find all progress summary labels to update.")

    def filter_catalysts(self, filter_type):
        """Filter catalysts based on progress"""
        layout = self.catalyst_layout
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
        layout = self.catalyst_layout
        
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
        layout = self.catalyst_layout
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

    def keyPressEvent(self, event):
        """Handle key press events"""
        if event.key() == Qt.Key.Key_F11:
            if self.isMaximized():
                self.showNormal()
            else:
                self.showMaximized()
        super().keyPressEvent(event)

def main():
    app = QApplication(sys.argv)
    window = DestinyApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 