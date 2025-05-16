import requests
import sqlite3
import os
import json
import zipfile
import logging
from typing import Dict, Any, Optional, List
from supabase import Client as SupabaseClient # Use the synchronous client
from supabase import AsyncClient # REMOVE AsyncClient import
import asyncio # <--- Ensure asyncio is imported
from postgrest import APIError # <--- Import APIError for specific error handling

logger = logging.getLogger(__name__)

# Define a constant for the maximum number of hashes per Supabase request
MAX_HASHES_PER_REQUEST = 100

# New service for fetching definitions from Supabase
class SupabaseManifestService:
    """Provides access to Destiny 2 Manifest definitions stored in Supabase."""
    def __init__(self, sb_client: SupabaseClient):
        self.sb_client = sb_client

    async def get_definition(self, table_name: str, definition_hash: int) -> Optional[Dict[str, Any]]:
        """Fetches a specific definition from a Supabase manifest table by its hash.

        Args:
            table_name: The lowercase name of the Supabase table (e.g., 'destinyinventoryitemdefinition').
            definition_hash: The integer hash identifier (unsigned).

        Returns:
            A dictionary representing the definition JSON from the 'json_data' column,
            or None if not found or an error occurs.
        """
        if not self.sb_client:
            logger.error(f"Supabase client not available for fetching definition {definition_hash} from {table_name}.")
            return None
        try:
            query_table_name = table_name.lower()
            logger.debug(f"Fetching definition for hash {definition_hash} from Supabase table {query_table_name}...")
            response = await self.sb_client.table(query_table_name)\
                .select("json_data")\
                .eq("hash", definition_hash)\
                .maybe_single()\
                .execute()
            if response.data:
                return response.data.get('json_data')
            else:
                return None
        except Exception as e:
            logger.error(f"Error fetching definition {definition_hash} from Supabase table {table_name}: {e}", exc_info=True)
            return None

    async def get_definitions_batch(self, table_name: str, definition_hashes: List[int]) -> Dict[int, Dict[str, Any]]:
        """Fetches multiple definitions from a Supabase manifest table by their hashes,
        chunking requests if necessary and fetching chunks sequentially.

        Args:
            table_name: The lowercase name of the Supabase table (e.g., 'destinyinventoryitemdefinition').
            definition_hashes: A list of integer hash identifiers (unsigned).

        Returns:
            A dictionary mapping each hash to its definition JSON from the 'json_data' column.
            Hashes not found will be omitted from the result.
        """
        if not self.sb_client:
            logger.error(f"Supabase client not available for batch fetching from {table_name}.")
            return {}
        if not definition_hashes:
            logger.info(f"No definition hashes provided for batch fetching from {table_name}.")
            return {}
        query_table_name = table_name.lower()
        all_fetched_definitions: Dict[int, Dict[str, Any]] = {}
        num_hashes = len(definition_hashes)
        num_chunks = (num_hashes + MAX_HASHES_PER_REQUEST - 1) // MAX_HASHES_PER_REQUEST
        logger.info(f"Starting batch fetch for {num_hashes} definitions from {query_table_name} in {num_chunks} chunk(s).")
        for i in range(num_chunks):
            start_index = i * MAX_HASHES_PER_REQUEST
            end_index = start_index + MAX_HASHES_PER_REQUEST
            hash_chunk = definition_hashes[start_index:end_index]
            try:
                response = await self.sb_client.table(query_table_name)\
                    .select("hash, json_data")\
                    .in_("hash", hash_chunk)\
                    .execute()
                if response.data:
                    for record in response.data:
                        record_hash = int(record.get('hash'))
                        json_data_val = record.get('json_data')
                        if isinstance(json_data_val, str):
                            try:
                                json_data_val = json.loads(json_data_val)
                            except json.JSONDecodeError:
                                logger.error(f"Failed to parse json_data for hash {record_hash} in {query_table_name} from chunk {i+1}")
                                json_data_val = {}
                        elif not isinstance(json_data_val, dict):
                            logger.warning(f"json_data for hash {record_hash} in {query_table_name} (chunk {i+1}) is not a dict or string, it's {type(json_data_val)}. Using empty dict.")
                            json_data_val = {}
                        all_fetched_definitions[record_hash] = json_data_val
            except Exception as e:
                logger.error(f"Error processing chunk {i+1}/{num_chunks} for {query_table_name}: {e}", exc_info=True)
        logger.info(f"Batch fetch complete for {query_table_name}. Total definitions fetched: {len(all_fetched_definitions)} out of {num_hashes} requested.")
        return all_fetched_definitions

    def close_supabase_client(self):
        """Closes the Supabase client connection."""
        if self.sb_client:
            # No await needed for sync client
            self.sb_client = None
            logger.info("Supabase client connection closed.")

class ManifestManager:
    """Manages downloading, extracting, and accessing the Destiny 2 Manifest SQLite database.
    This class is primarily intended for use by scripts that populate other data stores (e.g., Supabase)
    with manifest data. For application runtime, use SupabaseManifestService to query definitions.
    """

    def __init__(self, api_key: str, manifest_dir: str = './manifest_data'):
        """Initializes ManifestManager for SQLite operations.
        
        Args:
            api_key: Bungie API key for fetching manifest metadata.
            manifest_dir: Directory to store manifest files (zip, SQLite DB, version.txt).
        """
        self.api_key = api_key
        self.manifest_dir = manifest_dir
        self.db_path: Optional[str] = None
        self.conn: Optional[sqlite3.Connection] = None
        # This initialization path is for scripts like populate_manifest_supabase.py
        self._ensure_manifest_updated() 

    def _get_manifest_metadata(self) -> Optional[Dict[str, Any]]:
        """Fetches the manifest metadata from the Bungie API."""
        url = "https://www.bungie.net/Platform/Destiny2/Manifest/"
        headers = {"X-API-Key": self.api_key}
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            if data['ErrorCode'] == 1:
                return data['Response']
            else:
                logger.error(f"Bungie API Error fetching manifest metadata: {data.get('Message', 'Unknown error')}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP Error fetching manifest metadata: {e}", exc_info=True)
            return None

    def _download_and_extract_manifest(self, mobile_world_content_path: str):
        """Downloads and extracts the manifest SQLite database."""
        download_url = f"https://www.bungie.net{mobile_world_content_path}"
        zip_filename = os.path.join(self.manifest_dir, 'manifest.zip')
        extracted_filename = os.path.join(self.manifest_dir, os.path.basename(mobile_world_content_path))

        try:
            logger.info(f"Downloading manifest from {download_url}...")
            response = requests.get(download_url, stream=True)
            response.raise_for_status()
            with open(zip_filename, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
            logger.info("Manifest downloaded. Extracting...")

            with zipfile.ZipFile(zip_filename, 'r') as zip_ref:
                zip_ref.extractall(self.manifest_dir)
            
            # Ensure the extracted file name matches what we expect
            # Sometimes the name inside the zip might differ slightly
            extracted_files = [f for f in os.listdir(self.manifest_dir) if f.endswith('.content')]
            if not extracted_files:
                 raise FileNotFoundError("Could not find .content file after extraction.")
            
            # Assume the largest file is the correct one if multiple exist
            actual_extracted_file = max(extracted_files, key=lambda f: os.path.getsize(os.path.join(self.manifest_dir, f)))
            actual_extracted_path = os.path.join(self.manifest_dir, actual_extracted_file)
            
            # Rename if necessary to the expected path
            if actual_extracted_path != extracted_filename:
                 logger.warning(f"Renaming extracted file from {actual_extracted_file} to {os.path.basename(extracted_filename)}")
                 os.rename(actual_extracted_path, extracted_filename)

            logger.info(f"Manifest extracted to {extracted_filename}")
            self.db_path = extracted_filename
            os.remove(zip_filename) # Clean up zip file
            return True

        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP Error downloading manifest: {e}", exc_info=True)
            return False
        except zipfile.BadZipFile:
            logger.error("Downloaded file is not a valid zip file.", exc_info=True)
            if os.path.exists(zip_filename): os.remove(zip_filename)
            return False
        except Exception as e:
            logger.error(f"Error downloading/extracting manifest: {e}", exc_info=True)
            if os.path.exists(zip_filename): os.remove(zip_filename)
            return False

    def _ensure_manifest_updated(self):
        """Checks if the local manifest is up-to-date and downloads if necessary."""
        os.makedirs(self.manifest_dir, exist_ok=True)
        version_file = os.path.join(self.manifest_dir, 'version.txt')
        current_local_version = None
        
        metadata = self._get_manifest_metadata()
        if not metadata:
            logger.error("Could not fetch manifest metadata. Cannot check for updates.")
            # Try to use existing DB if available
            existing_dbs = [f for f in os.listdir(self.manifest_dir) if f.endswith('.content')]
            if existing_dbs:
                self.db_path = os.path.join(self.manifest_dir, existing_dbs[0])
                logger.warning(f"Using existing manifest DB: {self.db_path}")
                self._connect_db()
            return

        remote_version = metadata.get('version')
        mobile_world_content_path = metadata.get('mobileWorldContentPaths', {}).get('en')

        if not remote_version or not mobile_world_content_path:
            logger.error("Manifest metadata missing version or English content path.")
            return

        if os.path.exists(version_file):
            with open(version_file, 'r') as f:
                current_local_version = f.read().strip()
            
            # Check if the DB file mentioned in version.txt actually exists
            expected_db_filename = os.path.join(self.manifest_dir, os.path.basename(mobile_world_content_path))
            if current_local_version == remote_version and os.path.exists(expected_db_filename):
                 self.db_path = expected_db_filename
                 logger.info(f"Manifest version {remote_version} is up-to-date.")
                 self._connect_db()
                 return
            else:
                 logger.info(f"Manifest version mismatch (Local: {current_local_version}, Remote: {remote_version}) or DB file missing. Redownloading.")
                 # Clean up old db file if it exists
                 if os.path.exists(expected_db_filename):
                     try:
                         self.close() # Ensure connection is closed before deleting
                         os.remove(expected_db_filename)
                         logger.info(f"Removed old database file: {expected_db_filename}")
                     except OSError as e:
                          logger.error(f"Error removing old database file {expected_db_filename}: {e}")

        if self._download_and_extract_manifest(mobile_world_content_path):
            with open(version_file, 'w') as f:
                f.write(remote_version)
            self._connect_db()
        else:
            logger.error("Failed to download and extract the new manifest.")
            # Attempt to connect if db_path was set by extraction before failure or previously
            if self.db_path and os.path.exists(self.db_path):
                 logger.warning(f"Attempting to connect to potentially stale DB: {self.db_path}")
                 self._connect_db()
            else:
                 logger.error("No valid manifest database available.")


    def _connect_db(self):
        """Connects to the SQLite database."""
        if not self.db_path or not os.path.exists(self.db_path):
            logger.error("Manifest database path not set or file does not exist.")
            return
        try:
            # Ensure thread safety for FastAPI background tasks / multiple workers if needed
            # self.conn = sqlite3.connect(self.db_path, check_same_thread=False) 
            self.conn = sqlite3.connect(self.db_path) 
            # Return rows as dictionaries
            self.conn.row_factory = sqlite3.Row 
            logger.info(f"Successfully connected to manifest database: {self.db_path}")
        except sqlite3.Error as e:
            logger.error(f"Error connecting to manifest database {self.db_path}: {e}", exc_info=True)
            self.conn = None
            self.db_path = None # Invalidate path if connection failed

    def get_definition(self, table_name: str, definition_hash: int) -> Optional[Dict[str, Any]]:
        """Fetches a specific definition from the manifest by its hash.

        Args:
            table_name: The name of the definition table (e.g., 'DestinyInventoryItemDefinition').
            definition_hash: The integer hash identifier.

        Returns:
            A dictionary representing the definition JSON, or None if not found or error.
        """
        if not self.conn:
            logger.error("Manifest database connection is not available.")
            # Maybe try reconnecting?
            # self._connect_db()
            # if not self.conn: return None
            return None

        # Convert hash to signed 32-bit integer if necessary (Bungie hashes > 2^31 are stored as negative in SQLite)
        if definition_hash > 2**31 - 1:
             definition_hash = definition_hash - 2**32

        cursor = self.conn.cursor()
        try:
            # Use parameterized query for safety, even though it's just an integer hash
            # Fixed f-string escaping for table name - NOTE: Table names generally shouldn't be parameterized directly in standard SQL APIs
            # Ensure table name is validated if it comes from user input (it doesn't here)
            cursor.execute(f"SELECT json FROM {table_name} WHERE id = ?", (definition_hash,))
            row = cursor.fetchone()
            if row:
                # Fixed potential JSON decoding issue: ensure row['json'] is string
                json_str = row['json']
                if isinstance(json_str, bytes):
                    json_str = json_str.decode('utf-8')
                return json.loads(json_str)
            else:
                # logger.debug(f"Definition not found for hash {definition_hash} in table {table_name}.")
                return None
        except sqlite3.Error as e:
            logger.error(f"SQLite error fetching definition {definition_hash} from {table_name}: {e}", exc_info=True)
            return None
        except json.JSONDecodeError as e:
            logger.error(f"Error decoding JSON for definition {definition_hash} from {table_name}: {e}", exc_info=True)
            return None
        finally:
            cursor.close()
            
    def get_all_definitions_for_table(self, table_name: str) -> List[Dict[str, Any]]:
        """Fetches all definitions from a specific manifest table.

        Args:
            table_name: The name of the definition table (e.g., 'DestinyInventoryItemDefinition').

        Returns:
            A list of dictionaries, where each dictionary represents a definition JSON,
            or an empty list if the table doesn't exist or an error occurs.
        """
        definitions = []
        if not self.conn:
            logger.error(f"Manifest database connection is not available for fetching all from {table_name}.")
            return definitions

        logger.info(f"Fetching all definitions from table: {table_name}...")
        cursor = self.conn.cursor()
        try:
            # Ensure table name is safe if coming from external sources (it's internal here)
            cursor.execute(f"SELECT id, json FROM {table_name}")
            rows = cursor.fetchall()
            logger.info(f"Retrieved {len(rows)} rows from {table_name}.")
            
            for row in rows:
                try:
                    json_str = row['json']
                    if isinstance(json_str, bytes):
                        json_str = json_str.decode('utf-8')
                    # We need both the hash (original, unsigned) and the JSON data
                    original_hash = row['id']
                    if original_hash < 0: # Convert signed negative back to unsigned
                        original_hash += 2**32
                        
                    definitions.append({
                        "hash": original_hash, 
                        "json_data": json.loads(json_str)
                    })
                except json.JSONDecodeError as json_e:
                    logger.error(f"Error decoding JSON for row with id {row['id']} in {table_name}: {json_e}")
                except Exception as inner_e:
                     logger.error(f"Error processing row with id {row['id']} in {table_name}: {inner_e}")
                     
        except sqlite3.Error as e:
            logger.error(f"SQLite error fetching all definitions from {table_name}: {e}", exc_info=True)
        finally:
            cursor.close()
            
        logger.info(f"Finished fetching. Returning {len(definitions)} definitions from {table_name}.")
        return definitions
            
    def close(self):
        """Closes the database connection."""
        if self.conn:
            self.conn.close()
            logger.info("Manifest database connection closed.")
            self.conn = None

# Example Usage (for standalone testing)
if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    # Requires BUNGIE_API_KEY environment variable to be set
    api_key = os.environ.get("BUNGIE_API_KEY")
    if not api_key:
        print("Error: BUNGIE_API_KEY environment variable not set.")
    else:
        manifest_manager = ManifestManager(api_key=api_key)
        if manifest_manager.conn:
            # Test fetching a known item (e.g., Gjallarhorn hash: 1364786882)
            item_hash = 1364786882
            item_def = manifest_manager.get_definition('DestinyInventoryItemDefinition', item_hash)
            if item_def:
                # Fixed f-string escaping
                print(f"Successfully fetched definition for {item_def.get('displayProperties', {}).get('name', 'Unknown Item')}:")
                # print(json.dumps(item_def, indent=2))
            else:
                # Fixed f-string escaping
                print(f"Could not fetch definition for hash {item_hash}.")

            manifest_manager.close()
        else:
             print("Failed to initialize ManifestManager or connect to DB.")
