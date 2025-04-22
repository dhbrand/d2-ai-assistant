import os
import time
import logging
from dotenv import load_dotenv
from bungie_oauth import OAuthManager
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

def test_api_call(headers):
    """Test the API call with the current token"""
    url = "https://www.bungie.net/Platform/User/GetMembershipsForCurrentUser/"
    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        data = response.json()
        if 'Response' in data and 'destinyMemberships' in data['Response']:
            return data['Response']
    return None

def main():
    # Initialize OAuth manager
    oauth = OAuthManager()
    
    # Start authentication
    logger.info("Starting authentication...")
    token_data = oauth.start_auth()
    
    if not token_data:
        logger.error("Authentication failed")
        return
        
    logger.info("Authentication successful!")
    logger.info(f"Access token expires in: {token_data['expires_in']} seconds")
    
    if 'refresh_token' in token_data:
        logger.info("Refresh token received")
    else:
        logger.error("No refresh token received")
        return
    
    # Wait for token to expire (or nearly expire)
    logger.info("Waiting for token to expire...")
    time.sleep(5)  # Wait 5 seconds for demonstration
    
    # Try to refresh the token
    logger.info("Attempting to refresh token...")
    if oauth.refresh_token():
        logger.info("Token refresh successful!")
        logger.info(f"New access token expires in: {oauth.token_data['expires_in']} seconds")
    else:
        logger.error("Token refresh failed")
    
    # Try to make an API request to verify the new token
    try:
        headers = oauth.get_headers()
        logger.info("Successfully got headers with refreshed token")
    except Exception as e:
        logger.error(f"Failed to get headers: {str(e)}")

if __name__ == "__main__":
    main() 