import sys
from PyQt6.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                           QPushButton, QLabel, QScrollArea, QProgressBar)
from PyQt6.QtCore import Qt, QThread, pyqtSignal
import requests
from dotenv import load_dotenv
import os
import webbrowser
from datetime import datetime, timedelta
import logging
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
import socket
import ssl
import secrets

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Bungie API Configuration
BUNGIE_API_ROOT = "https://www.bungie.net/Platform"
BUNGIE_AUTH_URL = "https://www.bungie.net/en/OAuth/Authorize"
BUNGIE_TOKEN_URL = "https://www.bungie.net/platform/app/oauth/token/"
BUNGIE_CLIENT_ID = os.getenv("BUNGIE_CLIENT_ID")
BUNGIE_API_KEY = os.getenv("BUNGIE_API_KEY")
REDIRECT_URI = os.getenv("REDIRECT_URI")

if not BUNGIE_CLIENT_ID or not BUNGIE_API_KEY or not REDIRECT_URI:
    raise ValueError("BUNGIE_CLIENT_ID, BUNGIE_API_KEY, and REDIRECT_URI must be set in .env file")

logger.debug(f"Using Client ID: {BUNGIE_CLIENT_ID}")
logger.debug(f"Using Redirect URI: {REDIRECT_URI}")

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        """Override to use our logger"""
        logger.debug(f"Server: {format%args}")
    
    def do_GET(self):
        """Handle the OAuth callback"""
        try:
            logger.debug(f"Received callback: {self.path}")
            
            # Get the callback path from the redirect URI
            callback_path = urllib.parse.urlparse(REDIRECT_URI).path
            
            if self.path.startswith(callback_path):
                parsed = urllib.parse.urlparse(self.path)
                query = urllib.parse.parse_qs(parsed.query)
                
                # Send response before processing
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                
                success_message = """
                <html>
                <body style="background-color: #1a1b2b; color: white; font-family: Arial, sans-serif; display: flex; justify-content: center; align-items: center; height: 100vh; margin: 0;">
                    <div style="text-align: center; padding: 20px; background-color: #2a2b3d; border-radius: 10px;">
                        <h2>Authentication Complete</h2>
                        <p>You can close this window and return to the app.</p>
                    </div>
                </body>
                </html>
                """
                self.wfile.write(success_message.encode())
                
                # Check for state parameter
                if "state" not in query:
                    self.server.oauth_error = "Missing state parameter in callback"
                    logger.error("Missing state parameter in callback")
                    return
                
                # Verify state parameter matches
                if query["state"][0] != self.server.expected_state:
                    self.server.oauth_error = "Invalid state parameter in callback"
                    logger.error("Invalid state parameter in callback")
                    return
                
                if "code" in query:
                    self.server.oauth_code = query["code"][0]
                    logger.debug("Received authorization code")
                elif "error" in query:
                    error = query["error"][0]
                    error_description = query.get("error_description", ["Unknown error"])[0]
                    self.server.oauth_error = f"{error}: {error_description}"
                    logger.error(f"Received OAuth error: {self.server.oauth_error}")
            else:
                self.send_response(404)
                self.end_headers()
            
        except Exception as e:
            logger.error(f"Error in callback handler: {e}")
            self.server.oauth_error = str(e)

class OAuthServer(QThread):
    auth_code_received = pyqtSignal(str)
    error_occurred = pyqtSignal(str)
    
    def __init__(self):
        super().__init__()
        self.server = None
        self.expected_state = None
    
    def set_state(self, state):
        """Set the expected state parameter"""
        self.expected_state = state
    
    def run(self):
        """Run the OAuth callback server"""
        try:
            # Parse the redirect URI to get the port
            parsed_uri = urllib.parse.urlparse(REDIRECT_URI)
            port = int(parsed_uri.port)
            host = parsed_uri.hostname
            
            self.server = HTTPServer((host, port), OAuthCallbackHandler)
            
            # Setup SSL with pre-generated certificates
            cert_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'dev-certs')
            certfile = os.path.join(cert_dir, 'server.crt')
            keyfile = os.path.join(cert_dir, 'server.key')
            
            if not (os.path.exists(certfile) and os.path.exists(keyfile)):
                raise Exception("SSL certificates not found in dev-certs directory")
            
            context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
            context.load_cert_chain(certfile=certfile, keyfile=keyfile)
            self.server.socket = context.wrap_socket(self.server.socket, server_side=True)
            
            self.server.timeout = 1
            self.server.oauth_code = None
            self.server.oauth_error = None
            self.server.expected_state = self.expected_state
            
            logger.debug(f"HTTPS Server started on {host}:{port}")
            
            # Wait for callback
            timeout = 300  # 5 minutes
            start_time = datetime.now()
            
            while datetime.now() - start_time < timedelta(seconds=timeout):
                self.server.handle_request()
                
                if self.server.oauth_code:
                    self.auth_code_received.emit(self.server.oauth_code)
                    break
                elif self.server.oauth_error:
                    self.error_occurred.emit(self.server.oauth_error)
                    break
            else:
                self.error_occurred.emit("Authentication timed out after 5 minutes")
            
        except Exception as e:
            self.error_occurred.emit(f"Server error: {str(e)}")
        finally:
            if self.server:
                self.server.server_close()

class CatalystCard(QWidget):
    def __init__(self, catalyst_data, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout()
        
        # Name
        name_label = QLabel(catalyst_data["name"])
        name_label.setStyleSheet("font-weight: bold; font-size: 14px;")
        layout.addWidget(name_label)
        
        # Progress bar
        progress_bar = QProgressBar()
        progress_bar.setValue(int(catalyst_data["progress"]))
        layout.addWidget(progress_bar)
        
        # Progress text
        progress_text = QLabel(f"{catalyst_data['progress']}% Complete")
        layout.addWidget(progress_text)
        
        # Objective
        objective_label = QLabel(catalyst_data["objective"])
        objective_label.setWordWrap(True)
        layout.addWidget(objective_label)
        
        self.setLayout(layout)
        self.setStyleSheet("""
            QWidget {
                background-color: #2a2b3d;
                color: white;
                border-radius: 8px;
                padding: 10px;
            }
            QProgressBar {
                border: 1px solid #5c69d1;
                border-radius: 5px;
                text-align: center;
            }
            QProgressBar::chunk {
                background-color: #5c69d1;
            }
        """)

class CatalystTracker(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Destiny 2 Catalyst Tracker")
        self.setMinimumSize(800, 600)
        self.access_token = None
        self.refresh_token = None
        self.token_expiry = None
        self.oauth_server = None
        
        # Create central widget and layout
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        
        # Create title label
        title_label = QLabel("Destiny 2 Catalyst Tracker")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 24px; color: #8888ff; margin: 20px;")
        layout.addWidget(title_label)
        
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
        self.login_button.clicked.connect(self.login)
        layout.addWidget(self.login_button, alignment=Qt.AlignmentFlag.AlignCenter)
        
        # Create status label
        self.status_label = QLabel()
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.status_label.setStyleSheet("color: white; font-size: 14px; margin: 10px;")
        layout.addWidget(self.status_label)
        
        # Create scroll area for catalysts
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        self.scroll_content = QWidget()
        self.scroll_layout = QVBoxLayout(self.scroll_content)
        scroll.setWidget(self.scroll_content)
        layout.addWidget(scroll)
        
        # Set window style
        self.setStyleSheet("""
            QMainWindow {
                background-color: #1a1b2b;
            }
            QScrollArea {
                border: none;
                background-color: transparent;
            }
            QWidget#scroll_content {
                background-color: transparent;
            }
        """)
        self.scroll_content.setObjectName("scroll_content")
    
    def login(self):
        """Start OAuth flow"""
        try:
            if self.oauth_server is not None:
                self.oauth_server.quit()
            
            self.oauth_server = OAuthServer()
            self.oauth_server.auth_code_received.connect(self.handle_auth_code)
            self.oauth_server.error_occurred.connect(self.handle_oauth_error)
            
            # Generate a secure random state parameter
            state = secrets.token_urlsafe(32)
            self.current_state = state  # Store for verification
            
            # Set the state before starting the server
            self.oauth_server.set_state(state)
            self.oauth_server.start()
            
            params = {
                "client_id": BUNGIE_CLIENT_ID,
                "response_type": "code",
                "state": state,
                "redirect_uri": REDIRECT_URI
            }
            
            auth_url = f"{BUNGIE_AUTH_URL}?{urllib.parse.urlencode(params)}"
            logger.debug(f"Opening auth URL: {auth_url}")
            
            # Use default browser - more reliable than forcing Chrome
            webbrowser.open(auth_url)
            self.login_button.setEnabled(False)
            self.status_label.setText("Waiting for Bungie authentication...")
            
        except Exception as e:
            logger.error(f"Error starting login: {e}")
            self.status_label.setText(f"Error: {str(e)}")
            self.login_button.setEnabled(True)

    def handle_auth_code(self, code):
        """Handle the received authorization code"""
        try:
            logger.debug("Exchanging auth code for token")
            
            # Exchange code for token
            token_data = {
                "grant_type": "authorization_code",
                "code": code,
                "client_id": BUNGIE_CLIENT_ID,
                "redirect_uri": REDIRECT_URI
            }
            
            headers = {
                "X-API-Key": BUNGIE_API_KEY,
                "Content-Type": "application/x-www-form-urlencoded"
            }
            
            response = requests.post(BUNGIE_TOKEN_URL, data=token_data, headers=headers)
            logger.debug(f"Token response status: {response.status_code}")
            
            if response.status_code == 200:
                token_info = response.json()
                if "error" in token_info:
                    raise Exception(f"OAuth error: {token_info['error']}")
                self.update_token_info(token_info)
                self.refresh_catalysts()
            else:
                error_data = response.json()
                error_msg = error_data.get("error_description", "Unknown error")
                raise Exception(f"Failed to get access token: {error_msg}")
                
        except Exception as e:
            logger.error(f"Error handling auth code: {e}")
            self.status_label.setText(f"Error: {str(e)}")
            self.login_button.setEnabled(True)

    def update_token_info(self, token_info):
        """Update token information and schedule refresh"""
        try:
            self.access_token = token_info["access_token"]
            self.refresh_token = token_info.get("refresh_token")  # May not be present for public clients
            self.membership_id = token_info.get("membership_id")
            
            # Set token expiry (Bungie tokens expire in 3600 seconds)
            expires_in = token_info.get("expires_in", 3600)
            self.token_expiry = datetime.now() + timedelta(seconds=expires_in)
            
            # Schedule token refresh 5 minutes before expiry
            refresh_delay = expires_in - 300  # 5 minutes before expiry
            if refresh_delay > 0 and self.refresh_token:  # Only schedule refresh if we have a refresh token
                QThread.singleShot(refresh_delay * 1000, self.refresh_token_if_needed)
                
            logger.debug("Token information updated successfully")
            
        except Exception as e:
            logger.error(f"Error updating token info: {e}")
            raise

    def refresh_token_if_needed(self):
        """Check and refresh token if needed"""
        if not self.refresh_token:
            logger.debug("No refresh token available")
            return
            
        if datetime.now() >= self.token_expiry:
            try:
                token_data = {
                    "grant_type": "refresh_token",
                    "refresh_token": self.refresh_token,
                    "client_id": BUNGIE_CLIENT_ID
                }
                
                headers = {
                    "X-API-Key": BUNGIE_API_KEY,
                    "Content-Type": "application/x-www-form-urlencoded"
                }
                
                response = requests.post(BUNGIE_TOKEN_URL, data=token_data, headers=headers)
                if response.status_code == 200:
                    token_info = response.json()
                    if "error" in token_info:
                        raise Exception(f"OAuth error: {token_info['error']}")
                    self.update_token_info(token_info)
                    logger.debug("Token refreshed successfully")
                else:
                    error_data = response.json()
                    error_msg = error_data.get("error_description", "Unknown error")
                    raise Exception(f"Failed to refresh token: {error_msg}")
                    
            except Exception as e:
                logger.error(f"Error refreshing token: {e}")
                self.access_token = None
                self.refresh_token = None
                self.status_label.setText("Error refreshing session. Please login again.")
                self.login_button.setEnabled(True)

    def refresh_catalysts(self):
        """Refresh the catalyst list"""
        try:
            # Check if token needs refresh before making API calls
            self.refresh_token_if_needed()
            if not self.access_token:
                return

            # Clear existing catalysts
            for i in reversed(range(self.scroll_layout.count())): 
                self.scroll_layout.itemAt(i).widget().setParent(None)
            
            # Get membership data
            headers = {"X-API-Key": BUNGIE_API_KEY}
            if self.access_token:
                headers["Authorization"] = f"Bearer {self.access_token}"
            
            response = requests.get(
                f"{BUNGIE_API_ROOT}/User/GetMembershipsForCurrentUser/",
                headers=headers
            )
            membership_data = response.json()["Response"]
            
            # Get catalysts
            catalysts = self.get_catalysts(membership_data)
            
            # Display catalysts
            for catalyst in catalysts:
                card = CatalystCard(catalyst)
                self.scroll_layout.addWidget(card)
            
        except Exception as e:
            logger.error(f"Error refreshing catalysts: {e}")
            self.status_label.setText(f"Error: {str(e)}")
    
    def get_catalysts(self, membership_data):
        """Get catalyst data from Bungie API"""
        destiny_membership = membership_data["destinyMemberships"][0]
        membership_type = destiny_membership["membershipType"]
        membership_id = destiny_membership["membershipId"]
        
        headers = {"X-API-Key": BUNGIE_API_KEY}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        
        profile_response = requests.get(
            f"{BUNGIE_API_ROOT}/Destiny2/{membership_type}/Profile/{membership_id}/",
            headers=headers,
            params={"components": "200,102"}
        )
        profile_data = profile_response.json()["Response"]
        
        catalysts = []
        
        if "profileInventory" in profile_data:
            inventory_items = profile_data["profileInventory"]["data"]["items"]
            for item in inventory_items:
                item_response = requests.get(
                    f"{BUNGIE_API_ROOT}/Destiny2/{membership_type}/Profile/{membership_id}/Item/{item['itemInstanceId']}",
                    headers=headers,
                    params={"components": "300,307"}
                )
                item_data = item_response.json()["Response"]
                
                if "objectives" in item_data and item_data["objectives"]["data"]:
                    objectives = item_data["objectives"]["data"]["objectives"]
                    if any(obj.get("complete", False) is not None for obj in objectives):
                        catalyst_info = {
                            "name": item_data.get("displayProperties", {}).get("name", "Unknown Catalyst"),
                            "progress": self.calculate_progress(objectives),
                            "objective": self.get_objective_description(objectives)
                        }
                        catalysts.append(catalyst_info)
        
        return catalysts
    
    def calculate_progress(self, objectives):
        if not objectives:
            return 0
        
        total_progress = 0
        for obj in objectives:
            if obj.get("completionValue", 0) > 0:
                progress = (obj.get("progress", 0) / obj.get("completionValue", 1)) * 100
                total_progress += progress
        
        return min(round(total_progress / len(objectives), 1), 100)
    
    def get_objective_description(self, objectives):
        if not objectives:
            return "No objectives found"
        
        return objectives[0].get("progressDescription", "Complete catalyst objectives")

    def handle_oauth_error(self, error_message):
        """Handle OAuth errors"""
        logger.error(f"OAuth error: {error_message}")
        self.status_label.setText(f"Error: {error_message}")
        self.login_button.setEnabled(True)

def main():
    app = QApplication(sys.argv)
    window = CatalystTracker()
    window.show()
    sys.exit(app.exec())

if __name__ == "__main__":
    main() 