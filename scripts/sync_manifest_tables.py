import sys
import os
from dotenv import load_dotenv
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions
import logging
import asyncio
import subprocess

# Ensure the project root is in sys.path for absolute imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Import manifest sync logic and table list
try:
    from sync_user_data_supabase import MANIFEST_TABLES_TO_SYNC, sync_all_manifest_definitions, initialize_services
except ImportError:
    print("Could not import manifest sync logic from sync_user_data_supabase.py. Please ensure the file exists and is in the correct location.")
    sys.exit(1)

# Always update DIM socket hashes before syncing manifest tables
update_script_path = os.path.join(os.path.dirname(__file__), "update_dim_hashes.py")
subprocess.run(["python", update_script_path], check=True)

# --- Configuration & Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Load Environment Variables ---
dotenv_path = os.path.join(project_root, '..', '.env')
if not load_dotenv(dotenv_path=dotenv_path):
    logger.warning(f".env file not found at {dotenv_path}. Using environment variables from system.")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
BUNGIE_API_KEY = os.getenv("BUNGIE_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY or not BUNGIE_API_KEY:
    logger.critical("Missing one or more required environment variables (SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, BUNGIE_API_KEY).")
    sys.exit(1)

# --- Main Manifest Sync Only ---
def main():
    logger.info("Initializing services for manifest sync...")
    sb_client, manifest_manager, _, _, _ = initialize_services()
    if not sb_client or not manifest_manager:
        logger.critical("Service initialization failed. Exiting manifest sync script.")
        return
    logger.info("Starting manifest table sync...")
    asyncio.run(sync_all_manifest_definitions(sb_client, manifest_manager))
    logger.info("Manifest table sync finished.")

if __name__ == "__main__":
    main() 