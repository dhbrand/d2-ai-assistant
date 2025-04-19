import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QPushButton, QLabel, QScrollArea, QTextEdit)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
import logging
from bungie_oauth import OAuthManager

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

class DestinyApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Destiny 2 OAuth Test")
        self.setMinimumSize(800, 600)
        
        # Initialize OAuth manager
        self.oauth_manager = OAuthManager()
        
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Create title label
        title_label = QLabel("Destiny 2 OAuth Test")
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
        self.status_label.setText("Authentication successful!")
        
    def handle_auth_error(self, error):
        """Handle authentication error"""
        logger.error(f"Authentication error: {error}")
        self.login_button.setEnabled(True)
        self.status_label.setText(f"Error: {error}")

def main():
    app = QApplication(sys.argv)
    window = DestinyApp()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 