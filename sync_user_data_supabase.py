import os
import sys
from dotenv import load_dotenv
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions
from datetime import datetime, timezone
import logging

# Adjust path to import from web_app backend
# Assumes script is run from the project root directory
project_root = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, project_root)

from web_app.backend.bungie_oauth import OAuthManager, InvalidRefreshTokenError
from web_app.backend.models import CatalystData # We might need a different format
from web_app.backend.catalyst import CatalystAPI
from web_app.backend.weapon_api import WeaponAPI
from web_app.backend.manifest import ManifestManager

# --- Configuration & Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Load Environment Variables ---
dotenv_path = os.path.join(project_root, '.env')
logger.info(f"Attempting to load environment variables from: {dotenv_path}")
loaded = load_dotenv(dotenv_path=dotenv_path)
if not loaded:
    logger.critical(f".env file not found at {dotenv_path}. Exiting.")
    exit(1)
logger.info(".env file loaded successfully.")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
BUNGIE_API_KEY = os.getenv("BUNGIE_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY or not BUNGIE_API_KEY:
    logger.critical("Missing one or more required environment variables (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, BUNGIE_API_KEY).")
    exit(1)

# --- Initialize Services ---
def initialize_services():
    logger.info("Initializing services...")
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY, options=ClientOptions(schema="public"))
        logger.info("Supabase client initialized.")

        manifest_manager = ManifestManager(api_key=BUNGIE_API_KEY, manifest_dir='./manifest_data')
        logger.info("ManifestManager initialized.")

        oauth_manager = OAuthManager() # Loads token from file by default
        logger.info("OAuthManager initialized.")

        catalyst_api = CatalystAPI(api_key=BUNGIE_API_KEY, manifest_manager=manifest_manager)
        logger.info("CatalystAPI initialized.")

        weapon_api = WeaponAPI(api_key=BUNGIE_API_KEY, manifest_manager=manifest_manager)
        logger.info("WeaponAPI initialized.")
        
        return supabase_client, manifest_manager, oauth_manager, catalyst_api, weapon_api
    except Exception as e:
        logger.exception(f"Failed to initialize services: {e}")
        return None, None, None, None, None

def sync_catalysts(sb_client: Client, oauth_manager: OAuthManager, catalyst_api: CatalystAPI):
    logger.info("Starting catalyst sync...")
    try:
        # Ensure token is valid and get user ID
        oauth_manager.refresh_if_needed()
        access_token = oauth_manager.token_data['access_token']
        bungie_membership_id = oauth_manager.token_data['membership_id']
        if not bungie_membership_id:
            logger.error("Bungie Membership ID not found in token data. Cannot sync catalysts.")
            return

        logger.info(f"Fetching catalyst data from Bungie API for user {bungie_membership_id}...")
        # Call the new method to get data formatted for the database
        catalyst_status_map = catalyst_api.get_catalyst_status_for_db(access_token)
        
        if not catalyst_status_map:
             logger.warning("No catalyst status data returned from API method.")
             return

        upsert_list = []
        now_iso = datetime.now(timezone.utc).isoformat()
        # Iterate through the dictionary returned by the new method
        for record_hash, data in catalyst_status_map.items(): 
            upsert_list.append({
                "user_id": str(bungie_membership_id),
                "catalyst_record_hash": int(record_hash),
                "is_complete": data.get('is_complete', False),
                "objectives": data.get('objectives'), # This is already the dict { objHash: progress }
                "last_updated": now_iso
            })

        if not upsert_list:
            logger.info("No catalyst data prepared to upsert.")
            return

        logger.info(f"Upserting {len(upsert_list)} catalyst records into Supabase...")
        response = sb_client.table("user_catalyst_status").upsert(upsert_list).execute()
        
        # Check response - upsert might return data or just status
        if response.data:
            logger.info(f"Successfully upserted/processed {len(response.data)} catalyst records.")
        else:
            logger.info("Catalyst upsert executed (response data might be empty on success/no change).")

    except InvalidRefreshTokenError:
        logger.error("Invalid refresh token. Cannot sync catalysts.")
    except Exception as e:
        logger.exception(f"An error occurred during catalyst sync: {e}")

def sync_weapons(sb_client: Client, oauth_manager: OAuthManager, weapon_api: WeaponAPI):
    logger.info("Starting weapon sync...")
    try:
        # Ensure token is valid 
        oauth_manager.refresh_if_needed()
        access_token = oauth_manager.token_data['access_token']
        # Get Bungie membership ID for user_id column in DB
        bungie_user_id_for_db = oauth_manager.token_data['membership_id'] 
        if not bungie_user_id_for_db:
            logger.error("Bungie Membership ID not found in token data. Cannot determine user for DB upsert.")
            return

        # Fetch Destiny-specific membership info needed for API calls
        logger.info(f"Fetching Destiny membership info for user {bungie_user_id_for_db}...")
        membership_info = weapon_api.get_membership_info(access_token)
        if not membership_info:
             logger.error(f"Could not get Destiny membership info for user {bungie_user_id_for_db}. Cannot sync weapons.")
             return
        membership_type = membership_info['type']
        destiny_membership_id = membership_info['id'] # Use this ID for Bungie API calls
        logger.info(f"Found Destiny membership type {membership_type}, ID {destiny_membership_id}.")

        # Fetch weapons using the correct Destiny membership ID
        logger.info(f"Fetching weapon data from Bungie API using Destiny ID {destiny_membership_id}...")
        weapon_list = weapon_api.get_all_weapons(access_token, membership_type, destiny_membership_id)

        if not weapon_list:
            logger.warning("No weapon data returned from API.")
            return
            
        upsert_list = []
        now_iso = datetime.now(timezone.utc).isoformat()
        for weapon in weapon_list:
            if not weapon.instance_id:
                continue 
            upsert_list.append({
                "user_id": str(bungie_user_id_for_db), # Use Bungie ID for the user_id column
                "item_instance_id": weapon.instance_id, 
                "item_hash": int(weapon.item_hash),
                "location": weapon.location,
                "is_equipped": weapon.is_equipped,
                "perks": weapon.perks, 
                "last_updated": now_iso
            })

        if not upsert_list:
            logger.info("No weapon data to upsert.")
            return

        logger.info(f"Upserting {len(upsert_list)} weapon inventory records into Supabase for user {bungie_user_id_for_db}...")
        response = sb_client.table("user_weapon_inventory").upsert(upsert_list).execute()

        if response.data:
            logger.info(f"Successfully upserted/processed {len(response.data)} weapon records.")
        else:
            logger.info("Weapon upsert executed (response data might be empty on success/no change).")

    except InvalidRefreshTokenError:
        logger.error("Invalid refresh token. Cannot sync weapons.")
    except Exception as e:
        logger.exception(f"An error occurred during weapon sync: {e}")

def main():
    sb_client, manifest_manager, oauth_manager, catalyst_api, weapon_api = initialize_services()
    
    if not all([sb_client, manifest_manager, oauth_manager, catalyst_api, weapon_api]):
        logger.critical("Service initialization failed. Exiting sync script.")
        return

    # Check if token data exists before proceeding
    if not oauth_manager.token_data or not oauth_manager.token_data.get('access_token'):
        logger.error("No valid token data loaded by OAuthManager. Cannot proceed with sync.")
        logger.error("Please ensure token.json exists and is valid, or authenticate first.")
        return
        
    # --- Run Sync Operations ---
    # For now, runs sequentially. Could be run in parallel if needed.
    sync_catalysts(sb_client, oauth_manager, catalyst_api)
    sync_weapons(sb_client, oauth_manager, weapon_api)

    logger.info("Sync script finished.")

if __name__ == "__main__":
    main() 