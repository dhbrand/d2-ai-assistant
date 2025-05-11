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
    logger.info("Starting weapon sync...")
    try:
        oauth_manager.refresh_if_needed()
        bungie_user_id_for_db = oauth_manager.token_data['membership_id']
        if not bungie_user_id_for_db:
            logger.error("Bungie Membership ID not found in token data. Cannot determine user for DB upsert.")
            return
        logger.info(f"Fetching Destiny membership info for user {bungie_user_id_for_db}...")
        membership_info = weapon_api.get_membership_info()
        if not membership_info:
            logger.error(f"Could not get Destiny membership info for user {bungie_user_id_for_db}. Cannot sync weapons.")
            return
        membership_type = membership_info['type']
        destiny_membership_id = membership_info['id']
        logger.info(f"Found Destiny membership type {membership_type}, ID {destiny_membership_id}.")
        logger.info(f"Fetching weapon data from Bungie API using Destiny ID {destiny_membership_id}...")
        weapon_list = await weapon_api.get_all_weapons(membership_type, destiny_membership_id)
        if not weapon_list:
            logger.warning("No weapon data returned from API.")
            return
        upsert_list = []
        now_iso = datetime.now(timezone.utc).isoformat()
        for weapon in weapon_list:
            if not weapon.instance_id:
                continue
            upsert_list.append({
                "user_id": str(bungie_user_id_for_db),
                "item_instance_id": weapon.instance_id,
                "item_hash": int(weapon.item_hash),
                "location": weapon.location,
                "is_equipped": weapon.is_equipped,
                "barrel_perks": [perk.model_dump(mode="json") for perk in weapon.barrel_perks] if weapon.barrel_perks else [],
                "magazine_perks": [perk.model_dump(mode="json") for perk in weapon.magazine_perks] if weapon.magazine_perks else [],
                "trait_perk_col1": [perk.model_dump(mode="json") for perk in weapon.trait_perk_col1] if weapon.trait_perk_col1 else [],
                "trait_perk_col2": [perk.model_dump(mode="json") for perk in weapon.trait_perk_col2] if weapon.trait_perk_col2 else [],
                "origin_trait": weapon.origin_trait.model_dump(mode="json") if weapon.origin_trait else None,
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