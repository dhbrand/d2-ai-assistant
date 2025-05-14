import sys
import os
from dotenv import load_dotenv
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions
from datetime import datetime, timezone
import logging
import subprocess
import asyncio

# Set project root (one level up from /scripts)
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Always resolve .env relative to the project root
env_path = os.path.join(project_root, ".env")
loaded = load_dotenv(dotenv_path=env_path)

# Always update DIM socket hashes before syncing user data
update_script_path = os.path.join(os.path.dirname(__file__), "update_dim_hashes.py")
subprocess.run(["python", update_script_path], check=True)

from web_app.backend.bungie_oauth import OAuthManager, InvalidRefreshTokenError
from web_app.backend.models import CatalystData # We might need a different format
from web_app.backend.catalyst import CatalystAPI
from web_app.backend.weapon_api import WeaponAPI
from web_app.backend.manifest import SupabaseManifestService

# --- Configuration & Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Load Environment Variables ---
logger.info(f"Attempting to load environment variables from: {env_path}")
if not loaded:
    logger.critical(f".env file not found at {env_path}. Exiting.")
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

        manifest_service = SupabaseManifestService(sb_client=supabase_client)
        logger.info("SupabaseManifestService initialized.")

        oauth_manager = OAuthManager() # Loads token from file by default
        logger.info("OAuthManager initialized.")

        catalyst_api = CatalystAPI(oauth_manager=oauth_manager, manifest_service=manifest_service)
        logger.info("CatalystAPI initialized.")

        weapon_api = WeaponAPI(oauth_manager=oauth_manager, manifest_service=manifest_service)
        logger.info("WeaponAPI initialized.")
        
        return supabase_client, manifest_service, oauth_manager, catalyst_api, weapon_api
    except Exception as e:
        logger.exception(f"Failed to initialize services: {e}")
        return None, None, None, None, None

async def sync_catalysts(sb_client: Client, oauth_manager: OAuthManager, catalyst_api: CatalystAPI):
    logger.info("Starting catalyst sync...")
    try:
        oauth_manager.refresh_if_needed()
        bungie_membership_id = oauth_manager.token_data['membership_id']
        if not bungie_membership_id:
            logger.error("Bungie Membership ID not found in token data. Cannot sync catalysts.")
            return
        logger.info(f"Fetching catalyst data from Bungie API for user {bungie_membership_id}...")
        catalyst_status_map = await catalyst_api.get_catalyst_status_for_db()
        if not catalyst_status_map:
            logger.warning("No catalyst status data returned from API method.")
            return
        upsert_list = []
        now_iso = datetime.now(timezone.utc).isoformat()
        for record_hash, data in catalyst_status_map.items():
            upsert_list.append({
                "user_id": str(bungie_membership_id),
                "catalyst_record_hash": int(record_hash),
                "is_complete": data.get('is_complete', False),
                "objectives": data.get('objectives'),
                "last_updated": now_iso
            })
        if not upsert_list:
            logger.info("No catalyst data prepared to upsert.")
            return
        logger.info(f"Upserting {len(upsert_list)} catalyst records into Supabase...")
        response = sb_client.table("user_catalyst_status").upsert(upsert_list).execute()
        if response.data:
            logger.info(f"Successfully upserted/processed {len(response.data)} catalyst records.")
        else:
            logger.info("Catalyst upsert executed (response data might be empty on success/no change).")
    except InvalidRefreshTokenError:
        logger.error("Invalid refresh token. Cannot sync catalysts.")
    except Exception as e:
        logger.exception(f"An error occurred during catalyst sync: {e}")

async def sync_weapons(sb_client: Client, oauth_manager: OAuthManager, weapon_api: WeaponAPI):
    logger.info("Starting weapon sync with detailed perks...")
    try:
        oauth_manager.refresh_if_needed()
        bungie_user_id_for_db = oauth_manager.token_data['membership_id']
        if not bungie_user_id_for_db:
            logger.error("Bungie Membership ID not found in token data. Cannot determine user for DB upsert.")
            return

        logger.info(f"Fetching Destiny membership info for user {bungie_user_id_for_db} via WeaponAPI...")
        membership_info = await weapon_api.get_membership_info() # Now calling the async version
        
        if not membership_info or not membership_info.get('id') or not membership_info.get('type'):
            logger.error(f"Could not get valid Destiny membership info for user {bungie_user_id_for_db} from WeaponAPI. Cannot sync weapons.")
            return
        
        membership_type = str(membership_info['type']) # Ensure type is string, though WeaponAPI should already return it as such
        destiny_membership_id = membership_info['id']
        
        logger.info(f"Successfully fetched Destiny membership: Type={membership_type}, ID={destiny_membership_id} for Bungie User {bungie_user_id_for_db}.")

        logger.info(f"Fetching detailed weapon data from Bungie API using Destiny ID {destiny_membership_id}...")
        # Call the new method that returns a list of dictionaries
        detailed_weapon_list = await weapon_api.get_all_weapons_with_detailed_perks(membership_type, destiny_membership_id)

        if not detailed_weapon_list:
            logger.warning(f"No detailed weapon data returned from API for user {destiny_membership_id}.")
            return

        upsert_list = []
        now_iso = datetime.now(timezone.utc).isoformat()

        for weapon_data in detailed_weapon_list: # weapon_data is already a dictionary
            if not weapon_data.get("item_instance_id"):
                logger.warning(f"Skipping weapon due to missing item_instance_id: {weapon_data.get('weapon_name')}")
                continue
            
            # Directly map fields from weapon_data to Supabase schema
            # Ensure all fields defined in user_weapon_inventory_schema.json are covered
            record_to_upsert = {
                "user_id": str(bungie_user_id_for_db),
                "item_instance_id": weapon_data.get("item_instance_id"),
                "item_hash": weapon_data.get("item_hash"), # Ensure this is an int if schema expects BIGINT
                "weapon_name": weapon_data.get("weapon_name"),
                "weapon_type": weapon_data.get("weapon_type"),
                "intrinsic_perk": weapon_data.get("intrinsic_perk"), # New field
                "location": weapon_data.get("location"),
                "is_equipped": weapon_data.get("is_equipped"),
                "col1_plugs": weapon_data.get("col1_plugs"), # Already a list of strings
                "col2_plugs": weapon_data.get("col2_plugs"),
                "col3_trait1": weapon_data.get("col3_trait1"),
                "col4_trait2": weapon_data.get("col4_trait2"),
                "origin_trait": weapon_data.get("origin_trait"),
                "masterwork": weapon_data.get("masterwork"),
                "weapon_mods": weapon_data.get("weapon_mods"),
                "shaders": weapon_data.get("shaders"),
                "last_updated": now_iso
            }
            upsert_list.append(record_to_upsert)

        if not upsert_list:
            logger.info(f"No weapon data prepared to upsert for user {bungie_user_id_for_db}.")
            return

        logger.info(f"Upserting {len(upsert_list)} detailed weapon inventory records into Supabase for user {bungie_user_id_for_db}...")
        response = sb_client.table("user_weapon_inventory").upsert(upsert_list).execute()

        if response.data:
            logger.info(f"Successfully upserted/processed {len(response.data)} detailed weapon records.")
        else:
            # Check for errors in the response if data is empty or missing
            # Supabase client might have error details in other parts of the response object
            # For now, assuming no data might mean no changes or successful execution without returning data.
            logger.info("Detailed weapon upsert executed. Response data might be empty on success/no change, or check for errors.")
            # Example to log potential error (might need adjustment based on actual Supabase client library)
            if hasattr(response, 'error') and response.error:
                logger.error(f"Supabase upsert error: {response.error}")

    except InvalidRefreshTokenError:
        logger.error("Invalid refresh token. Cannot sync detailed weapons.")
    except Exception as e:
        logger.exception(f"An error occurred during detailed weapon sync: {e}")

async def main():
    sb_client, manifest_service, oauth_manager, catalyst_api, weapon_api = initialize_services()
    if not all([sb_client, manifest_service, oauth_manager, catalyst_api, weapon_api]):
        logger.critical("Service initialization failed. Exiting sync script.")
        return
    if not oauth_manager.token_data or not oauth_manager.token_data.get('access_token'):
        logger.error("No valid token data loaded by OAuthManager. Cannot proceed with sync.")
        logger.error("Please ensure token.json exists and is valid, or authenticate first.")
        return
    await sync_catalysts(sb_client, oauth_manager, catalyst_api)
    await sync_weapons(sb_client, oauth_manager, weapon_api)
    logger.info("Sync script finished.")

if __name__ == "__main__":
    asyncio.run(main()) 