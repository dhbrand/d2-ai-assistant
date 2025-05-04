#!/usr/bin/env python
import os
import json
import logging
from dotenv import load_dotenv
from datetime import datetime, timezone, timedelta
import sys

# Adjust path to import from web_app/backend
# Assuming the script is run from the project root (destiny2_catalysts/)
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '.')))

try:
    from web_app.backend.manifest import ManifestManager
    from web_app.backend.weapon_api import WeaponAPI
    from web_app.backend.models import Weapon # For type hinting
except ImportError as e:
    print(f"Error importing modules. Make sure PYTHONPATH is set or run from project root. Details: {e}")
    sys.exit(1)

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()
BUNGIE_API_KEY = os.getenv("BUNGIE_API_KEY")
if not BUNGIE_API_KEY:
    logger.error("BUNGIE_API_KEY environment variable not set.")
    sys.exit(1)

# --- Helper function to get a potentially valid token from token.json ---
def get_access_token_from_file(file_path="token.json"):
    """Reads token data from file and returns access token if not expired."""
    try:
        with open(file_path, 'r') as f:
            token_data = json.load(f)
        
        access_token = token_data.get('access_token')
        expires_in = token_data.get('expires_in')
        fetched_at_timestamp = token_data.get('fetched_at') # Unix timestamp (float/int)
        received_at_str = token_data.get('received_at') # ISO string
        
        if not access_token:
             logger.warning(f"{file_path} found but missing access_token.")
             return None

        expiry_valid = False
        expiry_time_str = "Unknown"
        now_utc = datetime.now(timezone.utc)
        buffer = timedelta(minutes=1) # 1 minute buffer
        expires_at_calc = None

        # --- Try using fetched_at (Unix timestamp) first --- 
        if expires_in and fetched_at_timestamp:
            try:
                fetched_at = datetime.fromtimestamp(fetched_at_timestamp, tz=timezone.utc)
                expires_at_calc = fetched_at + timedelta(seconds=expires_in)
                logger.info(f"Checking expiry based on 'fetched_at' ({fetched_at}). Calculated expiry: {expires_at_calc}")
            except (TypeError, ValueError) as ts_err:
                logger.warning(f"Could not process 'fetched_at' timestamp {fetched_at_timestamp}: {ts_err}")

        # --- If fetched_at didn't work or wasn't present, try received_at (ISO string) --- 
        elif expires_in and received_at_str:
            try:
                received_at = datetime.fromisoformat(received_at_str)
                if received_at.tzinfo is None:
                    received_at = received_at.replace(tzinfo=timezone.utc)
                expires_at_calc = received_at + timedelta(seconds=expires_in)
                logger.info(f"Checking expiry based on 'received_at' ({received_at}). Calculated expiry: {expires_at_calc}")
            except ValueError as dt_err:
                logger.warning(f"Could not parse 'received_at' timestamp '{received_at_str}': {dt_err}")
        
        # --- Perform the expiry check if calculation was possible --- 
        if expires_at_calc:
            if expires_at_calc > (now_utc + buffer):
                expiry_valid = True
                expiry_time_str = str(expires_at_calc)
            else:
                 logger.warning(f"Token from {file_path} expired. Expiry: {expires_at_calc}, Now: {now_utc}")
        else:
            logger.warning(f"Cannot determine token expiry from {file_path} (missing expires_in and usable timestamp). Assuming expired.")

        if expiry_valid:
             logger.info(f"Using access token from {file_path}, expires approx {expiry_time_str}")
             return access_token
        else:
             logger.warning(f"Token deemed expired or expiry check failed.")
             return None

    except FileNotFoundError:
        logger.warning(f"{file_path} not found.")
        return None
    except (json.JSONDecodeError, KeyError, TypeError, ValueError) as e:
        logger.error(f"Error reading or parsing {file_path}: {e}")
        return None

# --- Main test logic ---
if __name__ == "__main__":
    logger.info("Starting WeaponAPI test script...")

    # 1. Get Access Token
    # Tries to get token from token.json. Ensure this file exists and is valid.
    # You might need to run the main app's login flow once to generate it.
    access_token = get_access_token_from_file()
    if not access_token:
        logger.error("Could not get a valid access token from token.json.")
        logger.error("Please run the main application login flow first, or modify this script to provide a token.")
        sys.exit(1)

    manifest_manager = None # Define outside try block for finally
    try:
        # 2. Initialize Managers
        logger.info("Initializing ManifestManager...")
        manifest_manager = ManifestManager(api_key=BUNGIE_API_KEY, manifest_dir='./manifest_data')
        manifest_manager._connect_db() # Ensure connection - might need adjustment if private
        logger.info("ManifestManager initialized and connected.")

        logger.info("Initializing WeaponAPI...")
        weapon_api = WeaponAPI(api_key=BUNGIE_API_KEY, manifest_manager=manifest_manager)
        logger.info("WeaponAPI initialized.")

        # 3. Get Membership Info
        logger.info("Fetching membership info...")
        membership_info = weapon_api.get_membership_info(access_token)
        if not membership_info:
            logger.error("Failed to retrieve membership info.")
            sys.exit(1)
        
        membership_type = membership_info['type']
        destiny_membership_id = membership_info['id']
        logger.info(f"Using Membership Type: {membership_type}, ID: {destiny_membership_id}")

        # 4. Get Weapons
        logger.info("Calling get_all_weapons...")
        weapons = weapon_api.get_all_weapons(
            access_token=access_token,
            membership_type=membership_type,
            destiny_membership_id=destiny_membership_id
        )
        
        logger.info(f"--- get_all_weapons finished ---")
        logger.info(f"Found {len(weapons)} weapons.")

        if weapons:
            logger.info("First 5 weapons found:")
            for i, weapon in enumerate(weapons[:5]):
                 # Log relevant info, avoiding overly verbose fields like description
                 logger.info(f"  {i+1}. Name: {weapon.name}, Type: {weapon.item_type}, Tier: {weapon.tier_type}, Hash: {weapon.item_hash}, InstanceId: {weapon.instance_id}, Location: {weapon.location}")
        else:
            logger.warning("No weapons were processed. Check previous logs for potential errors in API calls or manifest lookups within WeaponAPI.")

    except Exception as e:
        logger.error(f"An unexpected error occurred during the test: {e}", exc_info=True)
    finally:
        # 5. Clean up
        if manifest_manager:
            logger.info("Closing manifest database connection.")
            manifest_manager.close()
        logger.info("WeaponAPI test script finished.") 