import unittest
import os
import sys
import webbrowser
from unittest.mock import patch, MagicMock, mock_open, PropertyMock
from bungie_oauth import OAuthManager, OAuthServer, OAuthCallbackHandler
from dotenv import load_dotenv
import socket
import socketserver
import ssl
from datetime import datetime, timedelta

# Load environment variables
load_dotenv()

class TestOAuthManager(unittest.TestCase):
    def setUp(self):
        """Set up test environment"""
        self.oauth_manager = OAuthManager()
        
    def test_initialization(self):
        """Test OAuthManager initialization"""
        self.assertIsNotNone(self.oauth_manager)
        self.assertIsNone(self.oauth_manager.server)
        self.assertIsNone(self.oauth_manager.token_data)
        self.assertIsNotNone(self.oauth_manager.client_id)
        self.assertIsNotNone(self.oauth_manager.api_key)
        
    @patch('webbrowser.open')
    @patch('bungie_oauth.OAuthServer')
    @patch('requests.post')
    def test_start_auth(self, mock_post, mock_server, mock_webbrowser):
        """Test the authentication start process"""
        # Mock the server
        mock_server_instance = MagicMock()
        mock_server.return_value = mock_server_instance
        mock_server_instance.oauth_code = "test_auth_code"
        mock_server_instance.oauth_error = None
        
        # Mock the token response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "test_access_token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": "test_refresh_token"
        }
        mock_post.return_value = mock_response
        
        # Mock callbacks
        success_callback = MagicMock()
        error_callback = MagicMock()
        
        # Start authentication
        token_data = self.oauth_manager.start_auth(success_callback, error_callback)
        
        # Verify server was started
        mock_server_instance.start.assert_called_once()
        mock_server_instance.handle_request.assert_called_once()
        
        # Verify browser was opened with correct URL
        self.assertTrue(mock_webbrowser.called)
        url_call = mock_webbrowser.call_args[0][0]
        self.assertIn("response_type=code", url_call)
        self.assertIn("client_id=", url_call)
        self.assertIn("state=", url_call)
        
        # Verify token data and callback
        self.assertIsNotNone(token_data)
        self.assertEqual(token_data["access_token"], "test_access_token")
        self.assertEqual(token_data["refresh_token"], "test_refresh_token")
        self.assertIn("obtained_at", token_data)
        success_callback.assert_called_once_with(token_data)
        error_callback.assert_not_called()
        
    @patch('webbrowser.open')
    @patch('bungie_oauth.OAuthServer')
    def test_auth_error_handling(self, mock_server, mock_webbrowser):
        """Test error handling during authentication"""
        # Mock the server with error
        mock_server_instance = MagicMock()
        mock_server.return_value = mock_server_instance
        mock_server_instance.oauth_error = "Test error"
        mock_server_instance.oauth_code = None
        
        # Mock callbacks
        success_callback = MagicMock()
        error_callback = MagicMock()
        
        # Start authentication
        token_data = self.oauth_manager.start_auth(success_callback, error_callback)
        
        # Verify error handling
        self.assertIsNone(token_data)
        success_callback.assert_not_called()
        error_callback.assert_called_once_with("Test error")
        
    def test_refresh_if_needed_no_token(self):
        """Test refresh check with no token"""
        self.oauth_manager.token_data = None
        self.assertFalse(self.oauth_manager.refresh_if_needed())
        
    def test_refresh_if_needed_not_expired(self):
        """Test refresh check with valid token"""
        self.oauth_manager.token_data = {
            "access_token": "test_token",
            "expires_in": 3600,
            "obtained_at": datetime.now().timestamp()
        }
        self.assertTrue(self.oauth_manager.refresh_if_needed())
        
    @patch('bungie_oauth.OAuthManager.refresh_token')
    def test_refresh_if_needed_expired(self, mock_refresh_token):
        """Test refresh with expired token"""
        # Set expired token
        self.oauth_manager.token_data = {
            "access_token": "test_token",
            "expires_in": 3600,
            "obtained_at": (datetime.now() - timedelta(hours=2)).timestamp(),
            "refresh_token": "test_refresh_token"
        }
        
        # Mock successful refresh
        mock_refresh_token.return_value = True
        
        # Test refresh
        result = self.oauth_manager.refresh_if_needed()
        self.assertTrue(result)
        mock_refresh_token.assert_called_once()
        
    @patch('bungie_oauth.OAuthManager.refresh_token')
    @patch('bungie_oauth.OAuthManager.start_auth')
    def test_refresh_if_needed_failed_refresh(self, mock_start_auth, mock_refresh_token):
        """Test refresh fallback to full auth when refresh fails"""
        # Set expired token
        self.oauth_manager.token_data = {
            "access_token": "test_token",
            "expires_in": 3600,
            "obtained_at": (datetime.now() - timedelta(hours=2)).timestamp(),
            "refresh_token": "test_refresh_token"
        }
        
        # Mock failed refresh and successful auth
        mock_refresh_token.return_value = False
        mock_start_auth.return_value = {"access_token": "new_token"}
        
        # Test refresh
        result = self.oauth_manager.refresh_if_needed()
        self.assertTrue(result)
        mock_refresh_token.assert_called_once()
        mock_start_auth.assert_called_once()
        
    @patch('requests.post')
    def test_refresh_token_success(self, mock_post):
        """Test successful token refresh"""
        # Set up token data
        self.oauth_manager.token_data = {
            "access_token": "old_token",
            "refresh_token": "test_refresh_token",
            "obtained_at": datetime.now().timestamp()
        }
        
        # Mock successful refresh response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "access_token": "new_token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "refresh_token": "new_refresh_token"
        }
        mock_post.return_value = mock_response
        
        # Test refresh
        result = self.oauth_manager.refresh_token()
        self.assertTrue(result)
        self.assertEqual(self.oauth_manager.token_data["access_token"], "new_token")
        self.assertEqual(self.oauth_manager.token_data["refresh_token"], "new_refresh_token")
        self.assertIn("obtained_at", self.oauth_manager.token_data)
        
    @patch('requests.post')
    def test_refresh_token_no_refresh_token(self, mock_post):
        """Test refresh with no refresh token"""
        self.oauth_manager.token_data = {
            "access_token": "test_token",
            "obtained_at": datetime.now().timestamp()
        }
        
        result = self.oauth_manager.refresh_token()
        self.assertFalse(result)
        mock_post.assert_not_called()
        
    @patch('requests.post')
    def test_refresh_token_failure(self, mock_post):
        """Test failed token refresh"""
        # Set up token data
        self.oauth_manager.token_data = {
            "access_token": "old_token",
            "refresh_token": "test_refresh_token",
            "obtained_at": datetime.now().timestamp()
        }
        
        # Mock failed refresh response
        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_post.return_value = mock_response
        
        # Test refresh
        result = self.oauth_manager.refresh_token()
        self.assertFalse(result)
        self.assertEqual(self.oauth_manager.token_data["access_token"], "old_token")
        
    def test_get_headers(self):
        """Test header generation"""
        test_token = {
            "access_token": "test_token",
            "token_type": "Bearer",
            "expires_in": 3600,
            "obtained_at": datetime.now().timestamp()
        }
        self.oauth_manager.token_data = test_token
        
        headers = self.oauth_manager.get_headers()
        
        self.assertIn("X-API-Key", headers)
        self.assertIn("Authorization", headers)
        self.assertEqual(headers["Authorization"], "Bearer test_token")
        
    def test_get_headers_no_token(self):
        """Test header generation without token"""
        self.oauth_manager.token_data = None
        with self.assertRaises(Exception):
            self.oauth_manager.get_headers()

class TestOAuthServer(unittest.TestCase):
    def setUp(self):
        """Set up test environment"""
        self.server = OAuthServer()
        
    def test_server_initialization(self):
        """Test OAuthServer initialization"""
        self.assertIsNone(self.server.httpd)
        self.assertIsNone(self.server.expected_state)
        self.assertIsNone(self.server.oauth_code)
        self.assertIsNone(self.server.oauth_error)
        
    @patch('socketserver.TCPServer')
    @patch('ssl.SSLContext')
    def test_server_start(self, mock_ssl_context, mock_tcp_server):
        """Test server start with SSL"""
        # Mock SSL context and certificate files
        mock_context = MagicMock()
        mock_ssl_context.return_value = mock_context
        
        # Mock certificate files
        with patch('os.path.exists') as mock_exists:
            mock_exists.return_value = True
            
            # Start server
            self.server.start()
            
            # Verify SSL setup
            mock_ssl_context.assert_called_once_with(ssl.PROTOCOL_TLS_SERVER)
            mock_context.load_cert_chain.assert_called_once()
            
            # Verify server creation
            mock_tcp_server.assert_called_once()
            
    def test_state_management(self):
        """Test state parameter management"""
        test_state = "test_state"
        self.server.set_state(test_state)
        self.assertEqual(self.server.expected_state, test_state)

class TestOAuthCallbackHandler(unittest.TestCase):
    def setUp(self):
        """Set up test environment"""
        self.server = MagicMock()
        self.request = MagicMock(spec=socket.socket)
        self.client_address = ('127.0.0.1', 12345)
        
    def test_success_response(self):
        """Test successful callback handling"""
        # Mock request data
        request_data = (
            "GET /auth?code=test_code&state=test_state HTTP/1.1\r\n"
            "Host: localhost:4200\r\n\r\n"
        ).encode()
        self.request.recv.return_value = request_data
        
        # Set expected state and clear error
        self.server.expected_state = "test_state"
        self.server.oauth_error = None
        
        # Create handler
        handler = OAuthCallbackHandler(self.request, self.client_address, self.server)
        handler.oauth_server = self.server
        
        # Handle request
        handler.handle()
        
        # Verify response
        self.request.sendall.assert_called()
        self.assertEqual(self.server.oauth_code, "test_code")
        self.assertIsNone(self.server.oauth_error)
        
    def test_error_response(self):
        """Test error callback handling"""
        # Mock request data with error
        request_data = (
            "GET /auth?error=test_error&state=test_state HTTP/1.1\r\n"
            "Host: localhost:4200\r\n\r\n"
        ).encode()
        self.request.recv.return_value = request_data
        
        # Set expected state
        self.server.expected_state = "test_state"
        
        # Create handler
        handler = OAuthCallbackHandler(self.request, self.client_address, self.server)
        handler.oauth_server = self.server
        
        # Handle request
        handler.handle()
        
        # Verify error handling
        self.request.sendall.assert_called()
        self.assertEqual(self.server.oauth_error, "test_error")
        
    def test_state_mismatch(self):
        """Test state parameter mismatch"""
        # Mock request data with wrong state
        request_data = (
            "GET /auth?code=test_code&state=wrong_state HTTP/1.1\r\n"
            "Host: localhost:4200\r\n\r\n"
        ).encode()
        self.request.recv.return_value = request_data
        
        # Set expected state
        self.server.expected_state = "correct_state"
        
        # Create handler
        handler = OAuthCallbackHandler(self.request, self.client_address, self.server)
        handler.oauth_server = self.server
        
        # Handle request
        handler.handle()
        
        # Verify error handling
        self.request.sendall.assert_called()
        self.assertEqual(self.server.oauth_error, "State parameter mismatch")

if __name__ == '__main__':
    unittest.main() 