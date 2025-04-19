import logging
import requests
import time
from bungie_oauth import OAuthManager, BUNGIE_API_ROOT

# Configure logging - set to DEBUG for more detailed logs
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

def test_api_call(headers):
    """Make a test API call to verify authentication"""
    url = f"{BUNGIE_API_ROOT}/User/GetMembershipsForCurrentUser/"
    logger.debug(f"Making API call to: {url}")
    logger.debug(f"Using headers: {headers}")
    
    response = requests.get(url, headers=headers)
    logger.debug(f"API response status: {response.status_code}")
    
    if response.status_code == 200:
        data = response.json()
        logger.info("API call successful!")
        return data["Response"]
    else:
        error_msg = f"API call failed: {response.status_code} - {response.text}"
        logger.error(error_msg)
        raise Exception(error_msg)

def handle_auth_code(code):
    """Callback for successful authorization code"""
    logger.info("✓ Authorization code received")
    logger.debug(f"Code: {code}")

def handle_auth_error(error):
    """Callback for authentication errors"""
    logger.error(f"✗ Authentication error: {error}")

def main():
    logger.info("Starting OAuth test...")
    
    # Initialize OAuth manager
    oauth_manager = OAuthManager()
    
    try:
        # Start authentication
        logger.info("Starting authentication process...")
        token_data = oauth_manager.start_auth(
            auth_code_callback=lambda code: logger.info(f"Received auth code: {code}"),
            error_callback=lambda error: logger.error(f"Auth error: {error}")
        )
        
        if not token_data:
            logger.error("Failed to get token data")
            return
            
        logger.info("Successfully authenticated!")
        logger.info(f"Access token: {token_data['access_token'][:10]}...")
        logger.info(f"Token type: {token_data['token_type']}")
        logger.info(f"Expires in: {token_data['expires_in']} seconds")
        
        # Test token refresh
        logger.info("Testing token refresh...")
        if oauth_manager.refresh_if_needed():
            logger.info("Token refresh successful")
        else:
            logger.warning("Token refresh not needed or not possible")
            
        # Test getting headers
        try:
            headers = oauth_manager.get_headers()
            logger.info("Successfully got headers with valid token")
        except Exception as e:
            logger.error(f"Failed to get headers: {str(e)}")
            
        # Test the authentication with an API call
        logger.info("Testing API call...")
        membership_data = test_api_call(headers)
        logger.info(f"✓ Found {len(membership_data['destinyMemberships'])} Destiny 2 memberships")
        
    except Exception as e:
        logger.error(f"Error during OAuth test: {str(e)}")
    finally:
        # Clean up
        if oauth_manager.server:
            logger.info("Stopping OAuth server...")
            oauth_manager.stop_server()
            logger.info("✓ OAuth server stopped")

if __name__ == "__main__":
    main() 