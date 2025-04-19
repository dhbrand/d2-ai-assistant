import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QPushButton, QLabel, QScrollArea, QTextEdit,
                           QHBoxLayout, QProgressBar, QFrame)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
import logging
from bungie_oauth import OAuthManager
from catalyst import CatalystAPI
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

class LogDisplay(QTextEdit):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setStyleSheet("""
            QTextEdit {
                background-color: #1a1b2b;
                color: white;
                border: none;
                font-family: monospace;
            }
        """)

class LogHandler(logging.Handler):
    def __init__(self, text_widget):
        super().__init__()
        self.text_widget = text_widget
        self.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))

    def emit(self, record):
        msg = self.format(record)
        self.text_widget.append(msg)

class AuthThread(QThread):
    success = pyqtSignal(dict)
    error = pyqtSignal(str)
    
    def __init__(self, oauth_manager):
        super().__init__()
        self.oauth_manager = oauth_manager
        
    def run(self):
        def auth_callback(token_data):
            self.success.emit(token_data)
            
        def error_callback(error):
            self.error.emit(str(error))
            
        self.oauth_manager.start_auth(auth_callback, error_callback)

class CatalystThread(QThread):
    success = pyqtSignal(list)
    error = pyqtSignal(str)
    
    def __init__(self, catalyst_api):
        super().__init__()
        self.catalyst_api = catalyst_api
        
    def run(self):
        try:
            catalysts = self.catalyst_api.get_catalysts()
            self.success.emit(catalysts)
        except Exception as e:
            self.error.emit(str(e))

class CatalystWidget(QFrame):
    def __init__(self, catalyst_data, parent=None):
        super().__init__(parent)
        self.setStyleSheet("""
            QFrame {
                background-color: #2a2b3b;
                border-radius: 5px;
                padding: 10px;
                margin: 5px;
            }
            QLabel {
                color: white;
            }
            QProgressBar {
                border: 1px solid #444455;
                border-radius: 3px;
                text-align: center;
                background-color: #1a1b2b;
            }
            QProgressBar::chunk {
                background-color: #7777ff;
            }
        """)
        
        layout = QVBoxLayout(self)
        
        # Catalyst name
        name_label = QLabel(catalyst_data['name'])
        name_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #8888ff;")
        layout.addWidget(name_label)
        
        # Description
        if catalyst_data.get('description'):
            desc_label = QLabel(catalyst_data['description'])
            desc_label.setWordWrap(True)
            layout.addWidget(desc_label)
        
        # Objectives
        for obj in catalyst_data['objectives']:
            obj_layout = QHBoxLayout()
            
            # Progress bar
            progress = QProgressBar()
            progress.setMaximum(obj['completion'])
            progress.setValue(obj['progress'])
            progress.setFormat(f"{obj['progress']}/{obj['completion']}")
            obj_layout.addWidget(progress)
            
            # Description
            desc = QLabel(obj['description'])
            desc.setWordWrap(True)
            obj_layout.addWidget(desc)
            
            layout.addLayout(obj_layout)

class DestinyApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Destiny 2 Catalyst Tracker")
        self.setMinimumSize(800, 600)
        
        # Initialize OAuth manager
        self.oauth_manager = OAuthManager()
        self.catalyst_api = None
        
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Create title label
        title_label = QLabel("Destiny 2 Catalyst Tracker")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 24px; color: #8888ff; margin: 20px;")
        layout.addWidget(title_label)
        
        # Create log display
        self.log_display = LogDisplay()
        layout.addWidget(self.log_display)
        
        # Add log handler
        log_handler = LogHandler(self.log_display)
        logger.addHandler(log_handler)
        
        # Create login button
        self.login_button = QPushButton("Login with Bungie")
        self.login_button.setStyleSheet("""
            QPushButton {
                background-color: #7777ff;
                color: white;
                border: none;
                padding: 15px 30px;
                border-radius: 5px;
                font-size: 18px;
                min-width: 250px;
            }
            QPushButton:hover {
                background-color: #8888ff;
            }
            QPushButton:pressed {
                background-color: #6666ff;
            }
            QPushButton:disabled {
                background-color: #555555;
            }
        """)
        self.login_button.clicked.connect(self.start_auth)
        layout.addWidget(self.login_button, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # Create status label
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: white; font-size: 14px; margin: 10px;")
        layout.addWidget(self.status_label)
        
        # Create scroll area for catalysts
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("""
            QScrollArea {
                border: none;
                background-color: #1a1b2b;
            }
        """)
        layout.addWidget(self.scroll_area)
        
        # Create widget to hold catalysts
        self.catalysts_widget = QWidget()
        self.catalysts_widget.setLayout(QVBoxLayout())
        self.scroll_area.setWidget(self.catalysts_widget)
        
        # Set window style
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1a1b2b;
            }
            QLabel {
                color: white;
            }
        """)
        
    def start_auth(self):
        """Start the authentication process"""
        try:
            self.login_button.setEnabled(False)
            self.status_label.setText("Authenticating...")
            
            # Create and start auth thread
            self.auth_thread = AuthThread(self.oauth_manager)
            self.auth_thread.success.connect(self.handle_auth_success)
            self.auth_thread.error.connect(self.handle_auth_error)
            self.auth_thread.start()
            
        except Exception as e:
            logger.error(f"Error starting authentication: {e}")
            self.login_button.setEnabled(True)
            self.status_label.setText(f"Error: {str(e)}")
            
    def handle_auth_success(self, token_data):
        """Handle successful authentication"""
        logger.info("Authentication successful!")
        self.login_button.setEnabled(True)
        self.status_label.setText("Authentication successful! Fetching catalysts...")
        
        # Initialize catalyst API with token
        api_key = os.getenv("BUNGIE_API_KEY")
        self.catalyst_api = CatalystAPI(api_key, token_data["access_token"])
        
        # Start fetching catalysts
        self.fetch_catalysts()
        
    def handle_auth_error(self, error):
        """Handle authentication error"""
        logger.error(f"Authentication error: {error}")
        self.login_button.setEnabled(True)
        self.status_label.setText(f"Error: {error}")
        
    def fetch_catalysts(self):
        """Fetch and display catalysts"""
        if not self.catalyst_api:
            logger.error("Catalyst API not initialized")
            return
            
        self.status_label.setText("Fetching catalysts...")
        
        # Create and start catalyst thread
        self.catalyst_thread = CatalystThread(self.catalyst_api)
        self.catalyst_thread.success.connect(self.handle_catalysts_success)
        self.catalyst_thread.error.connect(self.handle_catalysts_error)
        self.catalyst_thread.start()
        
    def handle_catalysts_success(self, catalysts):
        """Handle successful catalyst fetch"""
        logger.info(f"Found {len(catalysts)} incomplete catalysts")
        self.status_label.setText(f"Found {len(catalysts)} incomplete catalysts")
        
        # Clear existing catalysts
        layout = self.catalysts_widget.layout()
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        
        # Add new catalysts
        for catalyst in catalysts:
            widget = CatalystWidget(catalyst)
            layout.addWidget(widget)
        
        # Add stretch at the end
        layout.addStretch()
        
    def handle_catalysts_error(self, error):
        """Handle catalyst fetch error"""
        logger.error(f"Error fetching catalysts: {error}")
        self.status_label.setText(f"Error fetching catalysts: {error}")

def main():
    app = QApplication(sys.argv)
    window = DestinyApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 