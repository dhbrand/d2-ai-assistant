import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QPushButton, QLabel, QScrollArea, QTextEdit,
                           QHBoxLayout, QProgressBar, QFrame, QGroupBox, QRadioButton,
                           QButtonGroup, QMessageBox, QSplitter, QCheckBox)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QEvent
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

class CatalystWidget(QWidget):
    def __init__(self, catalyst_data, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        
        # Create a group box for the catalyst
        group_box = QGroupBox(catalyst_data['name'])
        if catalyst_data.get('discovered', False):
            group_box.setStyleSheet("QGroupBox { font-weight: bold; color: #007700; }")
        else:
            group_box.setStyleSheet("QGroupBox { font-weight: bold; }")
        group_layout = QVBoxLayout()
        
        # Add weapon name
        name_label = QLabel(catalyst_data['name'])
        font = name_label.font()
        font.setBold(True)
        name_label.setFont(font)
        group_layout.addWidget(name_label)
        
        # Add description if available
        if catalyst_data.get('description'):
            desc_label = QLabel(catalyst_data['description'])
            desc_label.setWordWrap(True)
            group_layout.addWidget(desc_label)
        
        # Add objectives
        for obj in catalyst_data['objectives']:
            obj_layout = QHBoxLayout()
            
            # Create progress bar
            progress_bar = QProgressBar()
            progress_bar.setRange(0, obj['completion'])
            progress_bar.setValue(obj['progress'])
            progress_bar.setFormat(f"{obj['progress']}/{obj['completion']} - {obj['description']}")
            
            obj_layout.addWidget(progress_bar)
            group_layout.addLayout(obj_layout)
        
        group_box.setLayout(group_layout)
        layout.addWidget(group_box)

class DestinyApp(QMainWindow):
    def __init__(self):
        super().__init__()
        
        self.setWindowTitle("Destiny 2 Catalyst Tracker")
        self.setMinimumSize(800, 600)
        
        self.catalyst_api = None
        self.oauth_manager = None
        self.catalyst_thread = None
        self.cached_catalysts = {}
        self.cache_file = "catalyst_cache.json"
        
        # Create central widget and main layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # Mode selection group at the top
        mode_group_box = QGroupBox("Catalyst Mode")
        mode_layout = QHBoxLayout(mode_group_box)
        
        self.mode_group = QButtonGroup(self)
        self.known_catalysts_radio = QRadioButton("Known Catalysts")
        self.discover_catalysts_radio = QRadioButton("Discover New Catalysts")
        self.known_catalysts_radio.setChecked(True)
        self.known_catalysts_radio.setToolTip("Only show catalysts from the predefined list")
        self.discover_catalysts_radio.setToolTip("Search for potential new exotic catalysts")
        
        self.mode_group.addButton(self.known_catalysts_radio)
        self.mode_group.addButton(self.discover_catalysts_radio)
        
        # Cache control
        self.use_cache_checkbox = QCheckBox("Use Cached Data")
        self.use_cache_checkbox.setChecked(True)
        self.use_cache_checkbox.setToolTip("Use cached catalyst data for faster loading (up to 1 day old)")
        
        mode_layout.addWidget(self.known_catalysts_radio)
        mode_layout.addWidget(self.discover_catalysts_radio)
        mode_layout.addWidget(self.use_cache_checkbox)
        mode_layout.addStretch()
        
        # Disable mode selection until authenticated
        self.known_catalysts_radio.setEnabled(False)
        self.discover_catalysts_radio.setEnabled(False)
        
        # Add to main layout
        main_layout.addWidget(mode_group_box)
        
        # Create splitter for catalysts and logs
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        main_layout.addWidget(self.splitter, 1)
        
        # Create scroll area for catalysts
        scroll_area = QScrollArea()
        scroll_area.setWidgetResizable(True)
        self.catalysts_widget = QWidget()
        self.catalysts_widget.setLayout(QVBoxLayout())
        self.catalysts_widget.layout().setAlignment(Qt.AlignmentFlag.AlignTop)
        scroll_area.setWidget(self.catalysts_widget)
        
        # Create log display
        self.log_display = LogDisplay()
        
        # Add to splitter
        self.splitter.addWidget(scroll_area)
        self.splitter.addWidget(self.log_display)
        
        # Create status bar at bottom
        status_bar = QWidget()
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(5, 5, 5, 5)
        
        self.status_label = QLabel("Please authenticate to continue")
        self.auth_button = QPushButton("Authenticate with Bungie")
        self.refresh_button = QPushButton("Refresh Catalysts")
        self.refresh_button.setDisabled(True)
        
        status_layout.addWidget(self.status_label, 1)
        status_layout.addWidget(self.refresh_button)
        status_layout.addWidget(self.auth_button)
        
        main_layout.addWidget(status_bar)
        
        # Connect signals
        self.auth_button.clicked.connect(self.authenticate)
        self.refresh_button.clicked.connect(self.fetch_catalysts)
        self.known_catalysts_radio.toggled.connect(self.on_mode_changed)
        self.discover_catalysts_radio.toggled.connect(self.on_mode_changed)
        
        # Configure logging to display in the app
        root_logger = logging.getLogger()
        root_logger.setLevel(logging.INFO)
        
        # Clear existing handlers and add our custom handler
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
            
        log_handler = LogHandler(self.log_display)
        root_logger.addHandler(log_handler)
        
        # Set the splitter's initial sizes (70% for catalysts, 30% for logs)
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

    def on_mode_changed(self):
        """Handle mode change between known catalysts and discovery mode"""
        if self.discover_catalysts_radio.isChecked():
            self.use_cache_checkbox.setChecked(False)
            self.use_cache_checkbox.setEnabled(False)
            logging.info("Switched to discovery mode - cache disabled")
        else:
            self.use_cache_checkbox.setEnabled(True)
            logging.info("Switched to known catalysts mode - cache enabled")
        
        # If we already have an API, refresh catalysts when mode changes
        if self.catalyst_api and self.isVisible():
            self.fetch_catalysts()

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
            self.known_catalysts_radio.setEnabled(True)
            self.discover_catalysts_radio.setEnabled(True)
            self.refresh_button.setEnabled(True)
            self.auth_button.setEnabled(False)
            
            # Initialize catalyst API with token
            logging.info("Initializing Catalyst API...")
            self.catalyst_api = CatalystAPI(api_key, token_data["access_token"])
            
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
        if not self.catalyst_api:
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
        discover_mode = self.discover_catalysts_radio.isChecked()
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
            
        self.catalyst_thread = CatalystThread(self.catalyst_api, discover_mode)
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
        
        widget = CatalystWidget(catalyst_data)
        layout = self.catalysts_widget.layout()
        layout.addWidget(widget)
        
        # Add to collected catalysts for caching (only if not in discovery mode or not a discovered item)
        if 'recordHash' in catalyst_data and (not is_discovered or self.discover_catalysts_radio.isChecked()):
            self.cached_catalysts[str(catalyst_data['recordHash'])] = catalyst_data

    def handle_catalysts_finished(self):
        """Handle finished catalyst fetch"""
        mode_text = "discovery" if self.discover_catalysts_radio.isChecked() else "standard"
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

def main():
    app = QApplication(sys.argv)
    window = DestinyApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 