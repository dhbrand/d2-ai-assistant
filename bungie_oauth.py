import os
import logging
import secrets
import urllib.parse
import webbrowser
import requests
import socketserver
import ssl
from dotenv import load_dotenv
from datetime import datetime, timedelta
import threading
import time
import sys
import socket

# Configure logging
logger = logging.getLogger(__name__)

# Disable noisy loggers
logging.getLogger('urllib3.connectionpool').setLevel(logging.WARNING)

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

class OAuthCallbackHandler(socketserver.BaseRequestHandler):
    def __init__(self, request, client_address, server):
        self.oauth_server = getattr(server, 'oauth_server', None)
        super().__init__(request, client_address, server)
    
    def handle(self):
        try:
            # Parse the request
            data = self.request.recv(1024).decode()
            if not data:
                return
                
            # Extract the path from the request
            path = data.split('\n')[0].split(' ')[1]
            logger.debug(f"Received request: {path}")
            
            # Parse the callback URL
            parsed = urllib.parse.urlparse(path)
            params = urllib.parse.parse_qs(parsed.query)
            logger.debug(f"Query parameters: {params}")
            
            # Get the server instance
            server = self.oauth_server
            if not server:
                error = "Server instance not found"
                logger.error(error)
                self.send_error_response(error)
                return
            
            if 'error' in params:
                error = params['error'][0]
                server.oauth_error = error
                logger.error(f"OAuth error: {error}")
                self.send_error_response(error)
                return
                
            if 'code' not in params or 'state' not in params:
                error = "Missing code or state parameter"
                server.oauth_error = error
                logger.error(error)
                self.send_error_response(error)
                return
                
            # Verify state parameter
            received_state = params['state'][0]
            if received_state != server.expected_state:
                error = "State parameter mismatch"
                server.oauth_error = error
                logger.error(error)
                self.send_error_response(error)
                return
                
            # Store the authorization code
            server.oauth_code = params['code'][0]
            logger.debug("Received authorization code")
            
            # Send success response
            self.send_success_response()
            
        except Exception as e:
            error = f"Error handling callback: {str(e)}"
            logger.error(error)
            if hasattr(self, 'oauth_server'):
                self.oauth_server.oauth_error = error
            self.send_error_response(error)
            
    def send_success_response(self):
        response = (
            "HTTP/1.1 200 OK\r\n"
            "Content-Type: text/html\r\n"
            "\r\n"
            "<html><body>"
            "<h1>Authentication Successful!</h1>"
            "<p>You can close this window now.</p>"
            "<script>setTimeout(function() { window.close(); }, 2000);</script>"
            "</body></html>"
        )
        self.request.sendall(response.encode())
        
    def send_error_response(self, error):
        response = (
            "HTTP/1.1 400 Bad Request\r\n"
            "Content-Type: text/html\r\n"
            "\r\n"
            f"<html><body>"
            f"<h1>Authentication Error</h1>"
            f"<p>Error: {error}</p>"
            f"<p>Please close this window and try again.</p>"
            f"</body></html>"
        )
        self.request.sendall(response.encode())

class OAuthServer:
    def __init__(self):
        self.httpd = None
        self.expected_state = None
        self.oauth_code = None
        self.oauth_error = None
        
    def set_state(self, state):
        self.expected_state = state
        
    def start(self):
        """Start the HTTPS server"""
        # Create HTTPS server
        self.httpd = socketserver.TCPServer(('localhost', 4200), OAuthCallbackHandler)
        self.httpd.oauth_server = self
        
        # Setup SSL context
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.verify_mode = ssl.CERT_NONE  # Accept self-signed certificates
        context.check_hostname = False  # Don't verify hostname
        
        # Load certificates
        certfile = 'localhost.pem'
        keyfile = 'localhost-key.pem'
        
        if not (os.path.exists(certfile) and os.path.exists(keyfile)):
            raise FileNotFoundError("SSL certificates not found. Please run mkcert to generate them.")
            
        context.load_cert_chain(certfile=certfile, keyfile=keyfile)
        
        # Wrap socket with SSL
        self.httpd.socket = context.wrap_socket(self.httpd.socket, server_side=True)
        
        logger.debug("HTTPS Server started on localhost:4200")
        
    def stop(self):
        """Stop the HTTPS server"""
        if self.httpd:
            self.httpd.server_close()
            self.httpd = None
            
    def handle_request(self):
        """Handle a single request"""
        if self.httpd:
            self.httpd.handle_request()

class OAuthManager:
    """Manages OAuth authentication flow and token handling"""
    
    def __init__(self):
        self.server = None
        self.token_data = None
        self.auth_code_callback = None
        self.error_callback = None
        self.client_id = BUNGIE_CLIENT_ID
        self.client_secret = BUNGIE_API_KEY
        self.api_key = BUNGIE_API_KEY
    
    def start_auth(self, auth_code_callback=None, error_callback=None):
        """Start the OAuth flow and return the token data."""
        try:
            self.auth_code_callback = auth_code_callback
            self.error_callback = error_callback
            
            # Start server and get authorization URL
            self.server = OAuthServer()
            state = secrets.token_urlsafe(32)
            self.server.set_state(state)
            self.server.start()
            
            # Build authorization URL
            params = {
                'client_id': BUNGIE_CLIENT_ID,
                'response_type': 'code',
                'state': state,
                'redirect_uri': REDIRECT_URI
            }
            auth_url = f"{BUNGIE_AUTH_URL}?{urllib.parse.urlencode(params)}"
            
            # Open browser for authentication
            logger.info("Opening browser for authentication...")
            webbrowser.open(auth_url)
            
            # Wait for authentication to complete
            self.server.handle_request()
            
            if self.server.oauth_error:
                if self.error_callback:
                    self.error_callback(self.server.oauth_error)
                return None
            
            if not self.server.oauth_code:
                error = "No authorization code received"
                logger.error(error)
                if self.error_callback:
                    self.error_callback(error)
                return None
                
            # Exchange code for token
            logger.info("Exchanging authorization code for token...")
            response = requests.post(
                BUNGIE_TOKEN_URL,
                data={
                    'grant_type': 'authorization_code',
                    'code': self.server.oauth_code,
                    'client_id': BUNGIE_CLIENT_ID,
                    'redirect_uri': REDIRECT_URI
                },
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-API-Key': BUNGIE_API_KEY
                }
            )
            
            if response.status_code != 200:
                error = f"Token exchange failed: {response.status_code}"
                logger.error(error)
                if self.error_callback:
                    self.error_callback(error)
                return None
                
            self.token_data = response.json()
            logger.info("Successfully obtained access token")
            
            if self.auth_code_callback:
                self.auth_code_callback(self.token_data)
            
            return self.token_data
            
        except Exception as e:
            error = f"Error during authentication: {str(e)}"
            logger.error(error)
            if self.error_callback:
                self.error_callback(error)
            return None
    
    def refresh_if_needed(self):
        """Check if token needs refresh and handle re-authentication if needed."""
        if not self.token_data:
            logger.warning("No token data available")
            return False
            
        # Check if token is expired or will expire soon
        now = datetime.now().timestamp()
        expires_at = self.token_data.get('obtained_at', 0) + self.token_data.get('expires_in', 0)
        
        # If token will expire in less than 5 minutes
        if now >= (expires_at - 300):
            logger.info("Token expired or will expire soon, re-authenticating...")
            token_data = self.start_auth()
            return token_data is not None
            
        return True
    
    def get_headers(self):
        """Get headers for API requests."""
        if not self.token_data:
            raise Exception("No token data available")
            
        if not self.refresh_if_needed():
            raise Exception("Token expired and re-authentication failed")
            
        return {
            'Authorization': f"{self.token_data['token_type']} {self.token_data['access_token']}",
            'X-API-Key': self.api_key
        }
    
    def stop_server(self):
        """Stop the OAuth server if it's running"""
        if self.server:
            self.server.stop()
            self.server = None 