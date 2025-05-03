#!/usr/bin/env python3
import json
import logging
import sys
import os
from bungie_oauth import OAuthManager
from catalyst import CatalystAPI

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger()
handler = logging.StreamHandler(sys.stdout)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def main():
    """
    Test the catalyst retrieval functionality using an existing auth token.
    
    This script will:
    1. Load the token from token.json
    2. Initialize the OAuthManager
    3. Initialize the CatalystAPI
    4. Attempt to fetch catalysts
    5. Display results
    """
    # Check if token file exists
    if not os.path.exists('token.json'):
        logger.error("token.json file not found. Please ensure authentication is completed first.")
        logger.info("Run auth flow to generate a token.json file.")
        return
    
    # Load environment variables
    try:
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv('BUNGIE_API_KEY')
        client_id = os.getenv('BUNGIE_CLIENT_ID')
        client_secret = os.getenv('BUNGIE_CLIENT_SECRET')
        
        if not all([api_key, client_id, client_secret]):
            logger.error("Required environment variables not set. Check your .env file.")
            return
            
    except ImportError:
        logger.error("dotenv package not installed. Run: pip install python-dotenv")
        return
    
    try:
        # Initialize OAuthManager
        logger.info("Initializing OAuth Manager...")
        oauth_manager = OAuthManager()
        
        # Load existing token
        logger.info("Loading token from token.json...")
        with open('token.json', 'r') as f:
            token_data = json.load(f)
        oauth_manager.token_data = token_data
        
        # Check if token is valid
        if not oauth_manager.refresh_if_needed():
            logger.error("Failed to refresh token. Please re-authenticate.")
            return
        
        # Initialize CatalystAPI
        logger.info("Initializing Catalyst API...")
        catalyst_api = CatalystAPI(oauth_manager)
        
        # Fetch catalysts
        logger.info("Fetching catalysts...")
        start_time = time.time()
        catalysts = catalyst_api.get_catalysts()
        elapsed = time.time() - start_time
        
        # Display results
        logger.info(f"Found {len(catalysts)} catalysts in {elapsed:.2f} seconds")
        print("\nCatalyst Results:")
        print("----------------")
        
        for idx, catalyst in enumerate(catalysts, 1):
            complete_status = "✅ Complete" if catalyst.get('complete') else "❌ Incomplete"
            progress = 0
            total = 0
            
            if objectives := catalyst.get('objectives', []):
                progress = sum(obj.get('progress', 0) for obj in objectives)
                total = sum(obj.get('completion', 0) for obj in objectives)
            
            progress_str = f"{progress}/{total}" if total > 0 else "N/A"
            
            print(f"{idx}. {catalyst.get('name')} - {complete_status} - Progress: {progress_str}")
        
        print("\nDetailed information for first 3 catalysts:")
        for catalyst in catalysts[:3]:
            print(f"\n{catalyst.get('name')}:")
            print(f"  Description: {catalyst.get('description')}")
            print(f"  Complete: {catalyst.get('complete')}")
            print(f"  Record Hash: {catalyst.get('recordHash')}")
            print("  Objectives:")
            for obj in catalyst.get('objectives', []):
                print(f"    - {obj.get('description')}: {obj.get('progress')}/{obj.get('completion')} {'(Complete)' if obj.get('complete') else ''}")

    except Exception as e:
        logger.error(f"Error: {e}", exc_info=True)

if __name__ == "__main__":
    # Add import for time only at runtime to avoid circular import in function definition
    import time
    main() 