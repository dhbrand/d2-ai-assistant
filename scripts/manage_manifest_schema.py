import sys
import os
from dotenv import load_dotenv
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions
import logging
import subprocess

# Ensure the project root is in sys.path for absolute imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Always update DIM socket hashes before managing manifest schema
update_script_path = os.path.join(os.path.dirname(__file__), "update_dim_hashes.py")
subprocess.run(["python", update_script_path], check=True)

# Adjust path to import from project root
sys.path.insert(0, project_root)
sys.path.insert(0, os.path.dirname(project_root))  # To import from parent if needed

# Import the manifest table list from sync_user_data_supabase.py
try:
    from sync_user_data_supabase import MANIFEST_TABLES_TO_SYNC
except ImportError:
    print("Could not import MANIFEST_TABLES_TO_SYNC from sync_user_data_supabase.py. Please ensure the file exists and is in the correct location.")
    sys.exit(1)

# --- Configuration & Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Load Environment Variables ---
dotenv_path = os.path.join(project_root, '..', '.env')
if not load_dotenv(dotenv_path=dotenv_path):
    logger.warning(f".env file not found at {dotenv_path}. Using environment variables from system.")

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.critical("Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY environment variables.")
    sys.exit(1)

# --- Initialize Supabase Client ---
sb_client = create_client(SUPABASE_URL, SUPABASE_KEY, options=ClientOptions(schema="public", postgrest_client_timeout=60))

# --- Table Creation Logic ---
def ensure_manifest_table_exists(table_name: str) -> bool:
    """
    Calls the execute_dynamic_sql Postgres function to create the manifest table if it does not exist.
    Returns True if successful, False otherwise.
    """
    supabase_table_name = table_name.lower()
    create_table_sql = f"""
    CREATE TABLE IF NOT EXISTS public.{supabase_table_name} (
        hash BIGINT PRIMARY KEY,
        json_data JSONB
    );
    """
    try:
        logger.info(f"Ensuring table {supabase_table_name} exists...")
        response = sb_client.rpc("execute_dynamic_sql", {"sql": create_table_sql}).execute()
        if hasattr(response, 'error') and response.error:
            logger.error(f"Error creating table {supabase_table_name}: {response.error}")
            return False
        logger.info(f"Table {supabase_table_name} exists or was created successfully.")
        return True
    except Exception as e:
        logger.error(f"Exception while creating table {supabase_table_name}: {e}", exc_info=True)
        return False

def main():
    logger.info("Starting manifest schema management script...")
    success_count = 0
    for table_name in MANIFEST_TABLES_TO_SYNC:
        if ensure_manifest_table_exists(table_name):
            success_count += 1
    logger.info(f"Finished. {success_count}/{len(MANIFEST_TABLES_TO_SYNC)} tables ensured.")

if __name__ == "__main__":
    main() 