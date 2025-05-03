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
import json
from pathlib import Path
from typing import List, Dict, Any, Optional

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
BUNGIE_CLIENT_SECRET = os.getenv("BUNGIE_CLIENT_SECRET")  # Add client secret for confidential client
BUNGIE_API_KEY = os.getenv("BUNGIE_API_KEY")
REDIRECT_URI = os.getenv("REDIRECT_URI")

if not all([BUNGIE_CLIENT_ID, BUNGIE_CLIENT_SECRET, BUNGIE_API_KEY, REDIRECT_URI]):
    raise ValueError("BUNGIE_CLIENT_ID, BUNGIE_CLIENT_SECRET, BUNGIE_API_KEY, and REDIRECT_URI must be set in .env file")

logger.debug(f"Using Client ID: {BUNGIE_CLIENT_ID}")
logger.debug(f"Using Redirect URI: {REDIRECT_URI}")

# Define token file path
TOKEN_FILE = Path("token.json")

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
        self.token_expiry_time = None  # Added expiry time tracking
        self.auth_code_callback = None
        self.error_callback = None
        self.client_id = BUNGIE_CLIENT_ID
        self.client_secret = BUNGIE_CLIENT_SECRET
        self.api_key = BUNGIE_API_KEY
        self._load_token_data()  # Load existing token data on init
    
    def _load_token_data(self):
        """Load token data from the file if it exists."""
        try:
            if TOKEN_FILE.exists():
                with open(TOKEN_FILE, 'r') as f:
                    self.token_data = json.load(f)
                
                # Calculate expiry time if token data is loaded
                if 'expires_in' in self.token_data and 'received_at' in self.token_data:
                    received_at = datetime.fromisoformat(self.token_data['received_at'])
                    expires_in = timedelta(seconds=self.token_data['expires_in'])
                    self.token_expiry_time = received_at + expires_in
                    logger.info(f"Loaded token data from {TOKEN_FILE}. Token expires at {self.token_expiry_time}")
                else:
                    logger.warning(f"Loaded token data from {TOKEN_FILE}, but expiry information is incomplete.")
                    self.token_data = None # Invalidate incomplete data
            else:
                 logger.info(f"Token file {TOKEN_FILE} not found. Need authentication.")

        except (FileNotFoundError, json.JSONDecodeError, KeyError) as e:
            logger.error(f"Error loading token data from {TOKEN_FILE}: {e}. Deleting corrupted file.")
            # If file is corrupted or invalid, delete it to force re-auth
            if TOKEN_FILE.exists():
                TOKEN_FILE.unlink()
            self.token_data = None

    def _save_token_data(self):
        """Save the current token data to the file."""
        if self.token_data:
            try:
                 # Add the time the token was received before saving
                self.token_data['received_at'] = datetime.now().isoformat()
                with open(TOKEN_FILE, 'w') as f:
                    json.dump(self.token_data, f, indent=4)
                logger.info(f"Saved token data to {TOKEN_FILE}")
            except IOError as e:
                logger.error(f"Error saving token data to {TOKEN_FILE}: {e}")
    
    def start_auth(self, auth_code_callback=None, error_callback=None):
        """Start the OAuth flow and return the token data."""
        try:
            # Check if we already have a valid token
            if self.token_data and self.token_expiry_time and datetime.now() < self.token_expiry_time:
                logger.info("Using existing valid token.")
                # Attempt to refresh if close to expiry, implement refresh_if_needed logic if needed
                # self.refresh_if_needed() # Consider adding this call here later
                return self.token_data # Return existing valid token

            # If no valid token, proceed with auth flow
            logger.info("No valid token found or token expired. Starting authentication flow...")
            self.auth_code_callback = auth_code_callback
            self.error_callback = error_callback
            
            # Start server and get authorization URL
            self.server = OAuthServer()
            state = secrets.token_urlsafe(32)
            self.server.set_state(state)
            self.server.start()
            
            # Build authorization URL
            params = {
                'client_id': self.client_id,
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
                
            # Verify state parameter
            # This verification should ideally happen in the handler, but we need the expected state
            # For now, we re-check here after the handler potentially set the code
            # TODO: Refactor state verification to be solely within the handler if possible

            # Re-retrieve state from params in case handler modified it? No, use server's expected state.
            # received_state = params['state'][0] # Incorrect placement - params not available here
            
            # Check if the server recorded a state mismatch error during handling
            if self.server.oauth_error == "State parameter mismatch":
                 error = "State parameter mismatch during callback handling."
                 logger.error(error)
                 if self.error_callback:
                    self.error_callback(error)
                 # self.send_error_response(error) # Incorrect call - remove this
                 return None

            # Exchange code for token using Basic Auth
            logger.info("Exchanging authorization code for token...")
            # Use the code stored by the handler
            if not self.server.oauth_code:
                 error = "Authorization code not found after handling callback."
                 logger.error(error)
                 if self.error_callback:
                    self.error_callback(error)
                 return None

            auth = requests.auth.HTTPBasicAuth(self.client_id, self.client_secret)
            
            response = requests.post(
                BUNGIE_TOKEN_URL,
                auth=auth,
                data={
                    'grant_type': 'authorization_code',
                    'code': self.server.oauth_code,
                    'redirect_uri': REDIRECT_URI
                },
                headers={
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'X-API-Key': self.api_key
                }
            )
            
            if response.status_code != 200:
                error = f"Token exchange failed: {response.status_code}"
                logger.error(error)
                logger.error(f"Response: {response.text}")
                if self.error_callback:
                    self.error_callback(error)
                return None
                
            # Store token data
            self.token_data = response.json()
            
            # Calculate and store expiry time
            now = datetime.now()
            expires_in = timedelta(seconds=self.token_data['expires_in'])
            self.token_expiry_time = now + expires_in
            self.token_data['received_at'] = now.isoformat() # Store receive time

            logger.info(f"Successfully obtained access token. Expires at: {self.token_expiry_time}")
            
            # Save token data to file
            self._save_token_data()
            
            if self.auth_code_callback:
                self.auth_code_callback(self.token_data)
            
            return self.token_data
            
        except Exception as e:
            error = f"Authentication error: {str(e)}"
            logger.error(error, exc_info=True) # Log traceback
            if self.error_callback:
                self.error_callback(error)
            return None
            
        finally:
            # Stop the server if it was started
            self.stop_server()
    
    def refresh_token(self, refresh_token_to_use: Optional[str] = None):
        """Refresh the access token using the refresh token."""
        token_to_refresh = refresh_token_to_use
        if not token_to_refresh:
            # Fallback to internal token data if specific one isn't provided
            if not self.token_data or 'refresh_token' not in self.token_data:
                logger.error("Refresh token is missing. Cannot refresh.")
                raise Exception("Missing refresh token")
            token_to_refresh = self.token_data['refresh_token']
            logger.info("Refreshing token using internally stored refresh token.")
        else:
            logger.info("Refreshing token using provided refresh token.")

        payload = {
            'grant_type': 'refresh_token',
            'refresh_token': token_to_refresh,
            'client_id': self.client_id,
            'client_secret': self.client_secret
        }
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }

        try:
            response = requests.post(BUNGIE_TOKEN_URL, data=payload, headers=headers)
            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)
            new_token_data = response.json()

            # Validate response
            if 'access_token' not in new_token_data or 'refresh_token' not in new_token_data or 'expires_in' not in new_token_data:
                logger.error(f"Token refresh response missing required fields: {new_token_data}")
                raise Exception("Incomplete token data received from refresh")

            logger.info("Token refreshed successfully.")

            # If we used the internal token, update internal state and save to file
            if not refresh_token_to_use:
                self.token_data = new_token_data
                # Calculate new expiry time for internal tracking
                expires_in = timedelta(seconds=self.token_data['expires_in'])
                self.token_expiry_time = datetime.now() + expires_in # Use local time for internal check consistency?
                self._save_token_data() # Save the updated tokens to file
                logger.info(f"Internal token state updated. New expiry: {self.token_expiry_time}")
            
            # Always return the new token data
            return new_token_data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP Error refreshing token: {e}", exc_info=True)
            # Handle specific errors, e.g., invalid refresh token
            if e.response is not None:
                try:
                    error_details = e.response.json()
                    logger.error(f"Bungie API error details: {error_details}")
                    # If refresh token is invalid, we might need to clear stored tokens and force re-auth
                    if error_details.get("error") == "invalid_grant":
                        logger.warning("Refresh token is invalid. Clearing stored tokens.")
                        # Clear internal state if we were using it
                        if not refresh_token_to_use:
                             self.token_data = None
                             self.token_expiry_time = None
                             if TOKEN_FILE.exists():
                                TOKEN_FILE.unlink()
                        # Raise a specific exception to signal re-authentication is needed
                        raise InvalidRefreshTokenError("Refresh token rejected by Bungie.")
                except json.JSONDecodeError:
                    logger.error("Could not decode error response from Bungie.")
            raise Exception(f"Failed to refresh token: {e}") from e
        except Exception as e:
            logger.error(f"Unexpected error during token refresh: {e}", exc_info=True)
            raise Exception("An unexpected error occurred while refreshing the token") from e

    def refresh_if_needed(self, buffer_seconds=60):
        """Check if the token is expired or close to expiring and refresh it."""
        if not self.token_data or not self.token_expiry_time:
            logger.info("No token data available, cannot refresh.")
            return False # Cannot refresh without token data
        
        now = datetime.now()
        # Refresh if token is expired or within the buffer period
        if now >= self.token_expiry_time - timedelta(seconds=buffer_seconds):
            logger.info("Token expired or nearing expiry, attempting refresh.")
            return self.refresh_token()
        else:
            # logger.debug("Token is still valid, no refresh needed.")
            return True # Token is still valid

    def get_headers(self):
        """Get headers for API requests"""
        self.refresh_if_needed()
        return {
            'X-API-Key': BUNGIE_API_KEY,
            'Authorization': f'Bearer {self.token_data["access_token"]}'
        }

    def get_auth_url(self):
        """Get the Bungie OAuth authorization URL"""
        state = secrets.token_urlsafe(16)
        params = {
            'client_id': BUNGIE_CLIENT_ID,
            'response_type': 'code',
            'state': state,
            'redirect_uri': REDIRECT_URI
        }
        auth_url = f"{BUNGIE_AUTH_URL}?{urllib.parse.urlencode(params)}"
        return auth_url
        
    def handle_callback(self, code):
        """Handle the OAuth callback and exchange the code for tokens"""
        try:
            # ** DEBUGGING **
            logger.info("[DEBUG] Entering handle_callback")
            logger.info(f"[DEBUG] Received code: {code}")
            logger.info(f"[DEBUG] Using REDIRECT_URI: {REDIRECT_URI}")
            logger.info(f"[DEBUG] Using client_id: {self.client_id}")
            # logger.info(f"[DEBUG] Using client_secret: {self.client_secret[:4]}...{self.client_secret[-4:]}") # Be careful logging secrets
            logger.info(f"[DEBUG] Using api_key: {self.api_key}")
            
            # Exchange code for token using Basic Auth
            logger.info(f"Exchanging authorization code for token...")
            
            auth = requests.auth.HTTPBasicAuth(self.client_id, self.client_secret)
            
            data = {
                'grant_type': 'authorization_code',
                'code': code,
                'redirect_uri': REDIRECT_URI
            }
            
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'X-API-Key': self.api_key
            }
            
            # ** DEBUGGING **
            logger.info(f"[DEBUG] Sending POST request to: {BUNGIE_TOKEN_URL}")
            logger.info(f"[DEBUG] Request data: {data}")
            logger.info(f"[DEBUG] Request headers: {headers}")
            # logger.info(f"[DEBUG] Request auth: Basic {self.client_id}:***")
            
            response = requests.post(
                BUNGIE_TOKEN_URL,
                auth=auth,
                data=data,
                headers=headers
            )
            
            # ** DEBUGGING **
            logger.info(f"[DEBUG] Response status code: {response.status_code}")
            logger.info(f"[DEBUG] Response text: {response.text}")
            
            if response.status_code != 200:
                error = f"Token exchange failed: {response.status_code}"
                logger.error(error)
                logger.error(f"Full Response: {response.text}")
                try:
                    # Try to parse response as JSON for more details
                    error_data = response.json()
                    logger.error(f"Error details: {error_data}")
                    error_message = f"{error}: {error_data}"
                except:
                    error_message = f"{error}: {response.text}"
                raise Exception(error_message)
                
            # Store token data
            token_data = response.json()
            self.token_data = token_data
            
            # Calculate and store expiry time
            now = datetime.now()
            expires_in = timedelta(seconds=token_data['expires_in'])
            self.token_expiry_time = now + expires_in
            self.token_data['received_at'] = now.isoformat() # Store receive time

            logger.info(f"Successfully obtained access token. Expires at: {self.token_expiry_time}")
            
            # Save token data to file
            self._save_token_data()
            
            return token_data
            
        except Exception as e:
            error = f"Authentication callback error: {str(e)}"
            logger.error(error, exc_info=True) # Log traceback
            raise Exception(error)

    def get_bungie_id(self, access_token):
        """Get the Bungie Membership ID for the current user using the access token."""
        logger.info("[DEBUG] Entering get_bungie_id")
        if not access_token:
            logger.error("[DEBUG] get_bungie_id called with no access token")
            raise ValueError("Access token is required")

        # Prepare headers for the API call
        headers = {
            'X-API-Key': self.api_key,
            'Authorization': f'Bearer {access_token}'
        }
        logger.info(f"[DEBUG] Calling Bungie API: {BUNGIE_API_ROOT}/User/GetMembershipsForCurrentUser/")
        logger.info(f"[DEBUG] Headers for GetMemberships: {headers}") # Be cautious logging full headers

        try:
            response = requests.get(
                f"{BUNGIE_API_ROOT}/User/GetMembershipsForCurrentUser/",
                headers=headers
            )
            logger.info(f"[DEBUG] GetMemberships response status: {response.status_code}")
            logger.info(f"[DEBUG] GetMemberships response text: {response.text[:200]}...") # Log partial response

            response.raise_for_status()  # Raise HTTPError for bad responses (4xx or 5xx)

            user_data = response.json()

            if user_data['ErrorCode'] != 1: # 1 = Success
                error_msg = f"Bungie API Error {user_data['ErrorCode']}: {user_data['Message']}"
                logger.error(f"[DEBUG] {error_msg}")
                raise Exception(error_msg)

            # Extract the primary membership ID (usually the first one)
            if not user_data['Response']['destinyMemberships']:
                 logger.error("[DEBUG] No Destiny memberships found for user.")
                 raise Exception("No Destiny memberships found for user.")
                 
            # Use the BUNGIE membership ID from the top level
            bungie_membership_id = user_data['Response']['bungieNetUser']['membershipId']
            logger.info(f"[DEBUG] Found Bungie Membership ID: {bungie_membership_id}")
            
            return bungie_membership_id
            
        except requests.exceptions.RequestException as e:
            logger.error(f"[DEBUG] HTTP Error getting memberships: {e}", exc_info=True)
            raise Exception(f"Failed to get user memberships from Bungie API: {e}")
        except Exception as e:
            logger.error(f"[DEBUG] Error processing memberships response: {e}", exc_info=True)
            raise Exception(f"Error processing Bungie API response: {e}")

    def stop_server(self):
        """Stop the OAuth callback server if it's running."""
        if self.server:
            self.server.stop()
            self.server = None
            logger.debug("OAuth callback server stopped.") 

# Custom Exception for invalid refresh token
class InvalidRefreshTokenError(Exception):
    pass 