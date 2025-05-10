# Placeholder for DestinyAgentService class

import os
from agents import Agent, Runner, function_tool, WebSearchTool, set_default_openai_client
from .weapon_api import WeaponAPI # Use relative import
from .catalyst import CatalystAPI # Use relative import
from .manifest import ManifestManager # Use relative import
import logging
import functools # Import functools
import asyncio # Import asyncio
from datetime import datetime, timedelta, timezone # Import datetime components
import pandas as pd # <--- Import pandas
from typing import Optional, List, Dict, Any
import requests
import xml.etree.ElementTree as ET
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import difflib
import re
from openai import OpenAI # Ensure OpenAI is imported for type hinting
from supabase import Client, AsyncClient
import json
from .models import CatalystData, CatalystObjective # <--- ADD THIS IMPORT
from .bungie_oauth import AuthenticationRequiredError, InvalidRefreshTokenError # <-- IMPORT THESE

logger = logging.getLogger(__name__)

# Define Cache Time-To-Live (TTL)
CACHE_TTL = timedelta(hours=24) # Cache data for 24 hours

# --- Tool Implementation Functions (outside class) ---

def _get_user_info_impl(service: 'DestinyAgentService') -> dict:
    """(Implementation) Fetch the user's Destiny membership info, using cache."""
    logger.debug("Agent Tool Impl: get_user_info called")
    bungie_id = service._current_bungie_id
    access_token = service._current_access_token

    if not bungie_id or not access_token:
        logger.error("Agent Tool Impl Error: Bungie ID or Access token not set in context.")
        raise Exception("User context not available for get_user_info.")

    # Check cache
    now = datetime.now(timezone.utc)
    if bungie_id in service._user_info_cache:
        timestamp, cached_data = service._user_info_cache[bungie_id]
        if now - timestamp < CACHE_TTL:
            logger.info(f"Cache HIT for user_info for bungie_id {bungie_id}")
            return cached_data
        else:
            logger.info(f"Cache STALE for user_info for bungie_id {bungie_id}")
    else:
        logger.info(f"Cache MISS for user_info for bungie_id {bungie_id}")

    # Cache miss or stale, call API
    try:
        info = service.weapon_api.get_membership_info()
        if not info or 'id' not in info or 'type' not in info:
            logger.warning("Agent Tool Impl: get_membership_info returned incomplete data.")
            return {"error": "Could not retrieve valid membership info."}

        # Store in cache
        service._user_info_cache[bungie_id] = (now, info)
        logger.info(f"Cache SET for user_info for bungie_id {bungie_id}")
        return info
    except (AuthenticationRequiredError, InvalidRefreshTokenError) as auth_err: # <-- CATCH SPECIFIC AUTH ERRORS
        logger.warning(f"Authentication error in get_user_info: {auth_err}")
        raise # Re-raise auth-specific errors to be caught by FastAPI
    except Exception as e:
        logger.error(f"Agent Tool Impl Error in get_user_info: {e}", exc_info=True)
        # For other errors, return a dict error for the agent to formulate a response
        return {"error": f"Failed to get user info due to an internal error: {str(e)}"}

async def _get_weapons_impl(service: 'DestinyAgentService', membership_type: int, membership_id: str) -> list:
    """(Implementation) Fetch all weapons for a user, using cache."""
    logger.debug(f"Agent Tool Impl: get_weapons called for {membership_type}/{membership_id}")
    bungie_id = service._current_bungie_id
    access_token = service._current_access_token

    if not bungie_id or not access_token:
        logger.error("Agent Tool Impl Error: Bungie ID or Access token not set in context.")
        raise Exception("User context not available for get_weapons.")

    # Check cache
    now = datetime.now(timezone.utc)
    cache_key = f"{bungie_id}_{membership_type}_{membership_id}" # Use combined key for weapon cache if needed, or just bungie_id if sufficient
    if bungie_id in service._weapons_cache: # Using bungie_id as primary cache key
        timestamp, cached_data = service._weapons_cache[bungie_id]
        if now - timestamp < CACHE_TTL:
            logger.info(f"Cache HIT for weapons for bungie_id {bungie_id}")
            # Convert cached Pydantic models back to dicts if necessary for agent?
            # Assuming agent handles Pydantic models or they were stored as dicts
            return cached_data
        else:
            logger.info(f"Cache STALE for weapons for bungie_id {bungie_id}")
    else:
        logger.info(f"Cache MISS for weapons for bungie_id {bungie_id}")

    # Cache miss or stale, call API
    try:
        # Use await for the async API call, without access_token
        weapons_data = await service.weapon_api.get_all_weapons(
            membership_type=membership_type,
            destiny_membership_id=membership_id
        )
        # Store in cache (converting Pydantic models to dicts might be safer for serialization/agent)
        # For now, storing the list of Pydantic objects directly.
        service._weapons_cache[bungie_id] = (now, weapons_data)
        logger.info(f"Cache SET for weapons for bungie_id {bungie_id}")
        return weapons_data
    except (AuthenticationRequiredError, InvalidRefreshTokenError) as auth_err: # <-- CATCH SPECIFIC AUTH ERRORS
        logger.warning(f"Authentication error in get_weapons: {auth_err}")
        raise # Re-raise auth-specific errors
    except Exception as e:
        logger.error(f"Agent Tool Impl Error in get_weapons: {e}", exc_info=True)
        return {"error": f"Failed to get weapons due to an internal error: {str(e)}"} # Return dict error

async def _get_catalysts_impl(service: 'DestinyAgentService') -> list:
    """(Implementation) Fetch all catalyst progress for a user, using Supabase as cache."""
    logger.debug("Agent Tool Impl: get_catalysts called")
    bungie_id = service._current_bungie_id
    access_token = service._current_access_token

    if not bungie_id or not access_token:
        logger.error("Agent Tool Impl Error: Bungie ID or Access token not set in context.")
        raise Exception("User context not available for get_catalysts.")

    now = datetime.now(timezone.utc)
    processed_catalysts_from_cache = []
    all_cache_fresh = True # Assume fresh until a stale or missing entry is found

    try:
        logger.info(f"Attempting to fetch catalysts from Supabase cache for user {bungie_id}")
        supabase_response = await service.sb_client.table("user_catalyst_status") \
            .select("catalyst_record_hash, is_complete, objectives, last_updated") \
            .eq("user_id", bungie_id) \
            .execute()

        if supabase_response.data:
            logger.info(f"Found {len(supabase_response.data)} catalyst entries in Supabase for user {bungie_id}")
            # Check if we have at least one entry and if it might be stale
            # A more robust check might involve knowing all expected catalysts, but for now, check recency.
            # If any entry is older than CACHE_TTL, we consider the whole cache stale for simplicity.
            # Alternatively, one could try to refresh only stale individual entries.
            for cached_item_dict in supabase_response.data:
                last_updated_str = cached_item_dict.get("last_updated")
                if last_updated_str:
                    last_updated_dt = datetime.fromisoformat(last_updated_str)
                    if now - last_updated_dt > CACHE_TTL:
                        all_cache_fresh = False
                        logger.info(f"Supabase cache for catalyst {cached_item_dict.get('catalyst_record_hash')} is STALE for user {bungie_id}.")
                        break # One stale item makes the whole cache miss for now
                else:
                    all_cache_fresh = False # Missing last_updated means it's effectively stale
                    logger.info(f"Supabase cache for catalyst {cached_item_dict.get('catalyst_record_hash')} has no last_updated timestamp for user {bungie_id}.")
                    break
            
            if all_cache_fresh:
                logger.info(f"Supabase catalyst cache is FRESH for user {bungie_id}. Reconstructing CatalystData.")
                
                # --- Step 1: Collect all record hashes ---
                all_record_hashes = list(set(item['catalyst_record_hash'] for item in supabase_response.data if 'catalyst_record_hash' in item))
                record_definitions_map: Dict[int, Dict[str, Any]] = {}

                # --- Step 2: Batch fetch all record definitions ---
                if all_record_hashes:
                    logger.info(f"Batch fetching {len(all_record_hashes)} DestinyRecordDefinition for cached catalysts.")
                    record_definitions_map = await service.manifest_service.get_definitions_batch(
                        "DestinyRecordDefinition", 
                        all_record_hashes
                    )
                    logger.info(f"Successfully fetched {len(record_definitions_map)} record definitions for cached catalysts.")
                else:
                    logger.info("No record hashes found in cached catalyst data to fetch definitions for.")

                # --- Step 3: Process cached items using the fetched definitions ---
                for cached_item_dict in supabase_response.data:
                    record_hash = cached_item_dict["catalyst_record_hash"]
                    
                    record_def = record_definitions_map.get(record_hash) # Get from pre-fetched map

                    if not record_def:
                        logger.warning(f"Could not find pre-fetched record definition for {record_hash} when reconstructing from cache.")
                        continue
                    
                    display_props = record_def.get('displayProperties', {})
                    name = display_props.get('name', f'Unknown Catalyst {record_hash}')
                    description = display_props.get('description', '')
                    # weapon_type and overall progress needs more sophisticated derivation similar to CatalystAPI
                    # For now, we'll use placeholders or derive simply if possible.
                    # TODO: Enhance weapon_type and overall progress derivation from manifest/objectives.
                    weapon_type = "Unknown"
                    
                    objectives_json = cached_item_dict.get("objectives")
                    objectives_list = []
                    if objectives_json:
                        if isinstance(objectives_json, str): # If objectives are stored as a JSON string
                            try:
                                objectives_list = [CatalystObjective(**obj) for obj in json.loads(objectives_json)]
                            except json.JSONDecodeError:
                                logger.error(f"Failed to parse objectives JSON for {record_hash}: {objectives_json}")
                        elif isinstance(objectives_json, list): # If already a list of dicts (from direct JSONB handling)
                             objectives_list = [CatalystObjective(**obj) for obj in objectives_json]

                    overall_progress = 0.0
                    if objectives_list:
                        total_prog = sum(obj.progress for obj in objectives_list)
                        total_comp = sum(obj.completion for obj in objectives_list)
                        if total_comp > 0:
                            overall_progress = (total_prog / total_comp) * 100
                        elif cached_item_dict["is_complete"]:
                            overall_progress = 100.0

                    processed_catalysts_from_cache.append(
                        CatalystData(
                            name=name,
                            description=description,
                            weapon_type=weapon_type, # Placeholder
                            objectives=objectives_list,
                            complete=cached_item_dict["is_complete"],
                            progress=overall_progress # Placeholder/Simple Derivation
                            # record_hash is not part of CatalystData model, but we have it.
                        )
                    )
                if processed_catalysts_from_cache: # If we successfully reconstructed some/all items
                    logger.info(f"Cache HIT: Returning {len(processed_catalysts_from_cache)} catalysts from Supabase for user {bungie_id}")
                    return processed_catalysts_from_cache
                else:
                    # This case means we found entries, they were fresh, but failed to process all of them.
                    logger.warning(f"Found fresh cache entries for user {bungie_id} but failed to reconstruct CatalystData for all items. Proceeding to API call.")
                    all_cache_fresh = False # Treat as a cache miss to force API refresh

        else:
            logger.info(f"Cache MISS: No catalyst data in Supabase for user {bungie_id}")
            all_cache_fresh = False # Explicitly a cache miss

    except Exception as e:
        logger.error(f"Error during Supabase catalyst cache check for user {bungie_id}: {e}", exc_info=True)
        all_cache_fresh = False # Treat as a cache miss on error

    # If cache was not fresh, or empty, or error during cache check: Call API
    if not all_cache_fresh:
        logger.info(f"Calling Bungie API for catalysts for user {bungie_id} due to cache miss or staleness.")
        try:
            # This is expected to return List[CatalystData] or list of dicts that can be validated into it
            # It should include record_hash if it's a list of dicts.
            api_catalysts_result = await service.catalyst_api.get_catalysts()

            # Prepare data for Supabase upsert
            catalysts_to_upsert = []
            # The result from get_catalysts should be List[CatalystData] or conform to it.
            # We need to ensure record_hash is available for each item to use as primary key for upsert.
            # Assuming service.catalyst_api.get_catalysts() result contains objects/dicts that have a 'record_hash' field/key.
            # For now, this part requires that the objects returned by get_catalysts have a .record_hash attribute.
            # And that CatalystData has .name, .description, .objectives, .complete, .progress fields.

            # Re-validate/structure into CatalystData if not already
            validated_api_catalysts = [] # Will store tuples of (CatalystData, record_hash_str)
            for item_data in api_catalysts_result: # item_data is a dict from catalyst_api
                if isinstance(item_data, dict):
                    current_record_hash = item_data.get('record_hash')
                    if not current_record_hash:
                        logger.warning(f"API item_data missing 'record_hash': {item_data.get('name', 'Unknown Catalyst')}")
                        continue
                    try:
                        # Validate the dict into CatalystData. record_hash is not part of the model,
                        # so it won't be included in 'validated_item'.
                        validated_item = CatalystData(**item_data)
                        validated_api_catalysts.append((validated_item, current_record_hash)) # Store as tuple
                    except Exception as val_err:
                        logger.error(f"Failed to validate item_data from catalyst_api into CatalystData: {item_data.get('name', 'Unknown')}, error: {val_err}")
                        continue
                else:
                    logger.warning(f"Unexpected item type from catalyst_api: {type(item_data)}")
                    continue

            for item, item_record_hash_str in validated_api_catalysts: # Unpack the tuple, item_record_hash_str is a string
                objectives_for_json = [obj.model_dump() for obj in item.objectives]
                try:
                    # Convert record hash string to integer for Supabase int8 column
                    catalyst_hash_int = int(item_record_hash_str)
                except ValueError:
                    logger.error(f"Could not convert catalyst_record_hash '{item_record_hash_str}' to int for item '{item.name}'. Skipping upsert for this item.")
                    continue

                catalysts_to_upsert.append({
                    "user_id": bungie_id,
                    "catalyst_record_hash": catalyst_hash_int, # Use the integer hash
                    "is_complete": item.complete,
                    "objectives": json.dumps(objectives_for_json),
                    "last_updated": now.isoformat()
                })
            
            if catalysts_to_upsert:
                try:
                    supabase_upsert_response = await service.sb_client.table("user_catalyst_status").upsert(catalysts_to_upsert).execute()
                    if supabase_upsert_response.data:
                        logger.info(f"Successfully upserted/updated {len(supabase_upsert_response.data)} catalysts to Supabase for user {bungie_id}")
                    else:
                        # Log error but don't fail the whole operation if some items were processed
                        logger.error(f"Supabase upsert for catalysts failed or returned no data for user {bungie_id}. Error: {supabase_upsert_response.error}")
                except Exception as db_e:
                    logger.error(f"Exception during Supabase catalyst upsert for user {bungie_id}: {db_e}", exc_info=True)
            
            logger.info(f"Cache SET: Returning {[item for item, _ in validated_api_catalysts]} catalysts from API for user {bungie_id}") # Return only CatalystData objects
            return [item for item, _ in validated_api_catalysts] # Return only CatalystData objects

        except (AuthenticationRequiredError, InvalidRefreshTokenError) as auth_err: # <-- CATCH SPECIFIC AUTH ERRORS
            logger.warning(f"Authentication error in get_catalysts API call: {auth_err}")
            raise # Re-raise auth-specific errors
        except Exception as e:
            logger.error(f"Error calling Bungie API for catalysts for user {bungie_id}: {e}", exc_info=True)
            # Return an error structure or empty list for the agent if API fails for other reasons
            return {"error": f"Failed to fetch catalysts from API due to an internal error: {str(e)}"}
    
    # This should ideally not be reached if all_cache_fresh was true and processing happened,
    # but as a fallback if cache was fresh but processing failed to return.
    logger.warning(f"Returning empty list or error for _get_catalysts_impl for user {bungie_id} as no data path was conclusive.")
    return {"error": "Could not determine catalyst status."}

# ---> ADDED: Google Sheet Tool Implementation <---
def _get_pve_bis_weapons_impl(service: 'DestinyAgentService') -> list[dict]:
    """(Implementation) Fetches PvE BiS weapons from the public Google Sheet."""
    logger.debug("Agent Tool Impl: get_pve_bis_weapons called")
    sheet_id = "1FF5HERxelE0PDiUjfu2eoSPrWNtOmsiHd5KggEXEC8g"
    # ---> Use the correct GID for the first sheet <--- 
    sheet_gid = 620327328 
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={sheet_gid}"
    
    cache_key = f"google_sheet_{sheet_id}_{sheet_gid}"
    now = datetime.now(timezone.utc)

    # Check cache (use service's generic cache dict or a dedicated one)
    if cache_key in service._sheet_cache:
        cache_time, cached_data = service._sheet_cache[cache_key]
        # Use a longer TTL for sheet data as it changes less often? Or keep same as others? Let's use CACHE_TTL for now.
        if now - cache_time < CACHE_TTL: 
            logger.info(f"Cache HIT for Google Sheet {sheet_id}")
            return cached_data
        else:
             logger.info(f"Cache STALE for Google Sheet {sheet_id}")
             
    logger.info(f"Cache MISS for Google Sheet {sheet_id}. Fetching from URL: {csv_url}")
    try:
        # Use pandas to read the CSV directly from the URL
        df = pd.read_csv(csv_url)
        
        # Optional: Basic cleaning - drop rows where all values are NaN 
        # (often happens with empty rows in sheets)
        df.dropna(how='all', inplace=True) 
        
        # Convert DataFrame to list of dictionaries for easier agent consumption
        data = df.to_dict(orient='records')
        
        # Store in cache
        service._sheet_cache[cache_key] = (now, data)
        logger.info(f"Cache SET for Google Sheet {sheet_id}. Read {len(data)} rows.")
        
        return data
    except Exception as e:
        logger.error(f"Agent Tool Impl Error fetching/parsing Google Sheet {sheet_id}: {e}", exc_info=True)
        raise Exception(f"Failed to read or parse the weapon data sheet: {e}")

# ---> ADDED: Second Google Sheet Tool Implementation <---
def _get_pve_activity_bis_weapons_impl(service: 'DestinyAgentService') -> list[dict]:
    """(Implementation) Fetches PvE BiS weapons BY ACTIVITY from the public Google Sheet."""
    logger.debug("Agent Tool Impl: get_pve_activity_bis_weapons called")
    sheet_id = "1FF5HERxelE0PDiUjfu2eoSPrWNtOmsiHd5KggEXEC8g"
    # ---> Use the correct GID <--- 
    sheet_gid = 82085161 
    csv_url = f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={sheet_gid}"
    
    cache_key = f"google_sheet_{sheet_id}_{sheet_gid}" # Unique cache key
    now = datetime.now(timezone.utc)

    # Check cache
    if cache_key in service._sheet_cache:
        cache_time, cached_data = service._sheet_cache[cache_key]
        if now - cache_time < CACHE_TTL: 
            logger.info(f"Cache HIT for Google Sheet {sheet_id} (gid={sheet_gid})")
            return cached_data
        else:
             logger.info(f"Cache STALE for Google Sheet {sheet_id} (gid={sheet_gid})")
             
    logger.info(f"Cache MISS for Google Sheet {sheet_id} (gid={sheet_gid}). Fetching from URL: {csv_url}")
    try:
        df = pd.read_csv(csv_url)
        df.dropna(how='all', inplace=True)
        data = df.to_dict(orient='records')
        service._sheet_cache[cache_key] = (now, data)
        logger.info(f"Cache SET for Google Sheet {sheet_id} (gid={sheet_gid}). Read {len(data)} rows.")
        return data
    except Exception as e:
        logger.error(f"Agent Tool Impl Error fetching/parsing Google Sheet {sheet_id} (gid={sheet_gid}): {e}", exc_info=True)
        raise Exception(f"Failed to read or parse the activity weapon data sheet: {e}")

# ---> MODIFIED: Endgame Analysis Sheet Tool Implementation <---
def _get_endgame_analysis_impl(service: 'DestinyAgentService', sheet_name: Optional[str] = None) -> list[dict] | str:
    """Fetches data from a specific sheet in the Endgame Analysis spreadsheet using the Google Sheets API and a service account."""
    logger.debug(f"Agent Tool Impl: get_endgame_analysis_data called. Target sheet: {sheet_name}")
    SHEET_ID = "1JM-0SlxVDAi-C6rGVlLxa-J1WGewEeL8Qvq4htWZHhY"
    SERVICE_ACCOUNT_FILE = os.path.join(os.path.dirname(__file__), "service_account.json")
    SCOPES = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    # Step 1: Authenticate and get sheet metadata
    try:
        creds = Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        service_gs = build("sheets", "v4", credentials=creds)
        meta = service_gs.spreadsheets().get(spreadsheetId=SHEET_ID).execute()
        sheets = meta.get("sheets", [])
        # Filter out sheets with 'old' or 'outdated' in the name
        active_sheets = [
            (s["properties"]["title"], s["properties"]["sheetId"])
            for s in sheets
            if "old" not in s["properties"]["title"].lower() and "outdated" not in s["properties"]["title"].lower()
        ]
        sheet_name_map = {title: gid for title, gid in active_sheets}
        available_sheet_names = list(sheet_name_map.keys())
    except Exception as e:
        logger.error(f"Failed to fetch sheet metadata: {e}")
        return f"Error: Could not fetch sheet metadata. {e}"
    # If no sheet_name provided, return available sheets
    if not sheet_name:
        return f"Please specify which sheet you want data from. Available sheets: {available_sheet_names}"
    # Fuzzy match the requested sheet name
    matches = difflib.get_close_matches(sheet_name, available_sheet_names, n=1, cutoff=0.6)
    if not matches:
        # Try regex partial match
        pattern = re.compile(re.escape(sheet_name), re.IGNORECASE)
        matches = [name for name in available_sheet_names if pattern.search(name)]
    if not matches:
        return f"Error: Unknown sheet name '{sheet_name}'. Available sheets: {available_sheet_names}"
    selected_sheet = matches[0]
    gid = sheet_name_map[selected_sheet]
    cache_key = f"endgame_analysis_{SHEET_ID}_{gid}"
    now = datetime.now(timezone.utc)
    # Check cache
    if cache_key in service._sheet_cache:
        cache_time, cached_data = service._sheet_cache[cache_key]
        if now - cache_time < CACHE_TTL:
            logger.info(f"Cache HIT for Endgame Analysis Sheet (key: {cache_key})")
            return cached_data
        else:
            logger.info(f"Cache STALE for Endgame Analysis Sheet (key: {cache_key})")
    # Fetch the sheet data as CSV
    try:
        csv_url = f"https://docs.google.com/spreadsheets/d/{SHEET_ID}/export?format=csv&gid={gid}"
        df = pd.read_csv(csv_url)
        df.dropna(how='all', inplace=True)
        # --- Preserve and distinguish perk columns ---
        # If the sheet has columns like 'Perk 1', 'Perk 2', etc., keep them as-is in the returned dicts
        # This allows downstream logic to reason about rolls that match only one column versus both
        data = df.to_dict(orient='records')
        service._sheet_cache[cache_key] = (now, data)
        logger.info(f"Cache SET for Endgame Analysis Sheet (key: {cache_key}). Read {len(data)} rows.")
        if len(data) > 200:
            return f"Sheet '{selected_sheet}' contains {len(data)} rows, which is too large to return directly. Please ask a more specific query about this sheet."
        return data
    except Exception as e:
        logger.error(f"Failed to fetch/parse sheet '{selected_sheet}' (gid={gid}): {e}")
        return f"Error: Failed to fetch or parse the sheet '{selected_sheet}'. {e}"

# --- Agent Service Class ---

class DestinyAgentService:
    def __init__(self, 
                 openai_client: OpenAI, 
                 catalyst_api: CatalystAPI, 
                 weapon_api: WeaponAPI,
                 supabase_client: AsyncClient,
                 # TODO: Add google_sheets_service or similar if used by endgame_analysis directly
                 # For now, endgame_analysis creates its own GSheets client.
                 ):
        logger.info("Initializing DestinyAgentService with pre-configured API clients and Supabase client.")
        self.openai_client = openai_client
        set_default_openai_client(self.openai_client)
        self.catalyst_api = catalyst_api
        self.weapon_api = weapon_api
        self.sb_client = supabase_client

        self.agent = self._create_agent()
        self._current_access_token: Optional[str] = None
        self._current_bungie_id: Optional[str] = None
        
        # Initialize caches
        self._user_info_cache: Dict[str, tuple[datetime, dict]] = {}
        self._weapons_cache: Dict[str, tuple[datetime, list]] = {}
        self._catalysts_cache: Dict[str, tuple[datetime, list]] = {}
        self._sheet_cache: Dict[str, tuple[datetime, list[dict]]] = {} # For Google Sheets

        self.persona_map = {
            "Saint-14": "You are Saint-14, the legendary Titan. Speak with honor, warmth, and a touch of old-world chivalry. Use phrases like 'my friend' and reference the Lighthouse or Trials. Use plenty of shield 🛡️, helmet 🪖, and sun ☀️ emojis.",
            "Cayde-6": "You are Cayde-6, the witty Hunter. Be playful, crack jokes, and use lots of chicken 🐔, ace of spades 🂡, and dice 🎲 emojis. Don't be afraid to be cheeky!",
            "Ikora": "You are Ikora Rey, the wise Warlock. Speak with calm authority, offer insight, and use book 📚, eye 👁️, and star ✨ emojis.",
            "Saladin": "You are Lord Saladin, the Iron Banner champion. Be stoic, proud, and use wolf 🐺, fire 🔥, and shield 🛡️ emojis.",
            "Zavala": "You are Commander Zavala, the steadfast Titan. Be direct, inspiring, and use shield 🛡️, fist ✊, and tower 🏰 emojis.",
            "Eris Morn": "You are Eris Morn, the mysterious Guardian. Speak cryptically, reference the Hive, and use eye 👁️, darkness 🌑, and worm 🪱 emojis.",
            "Shaxx": "You are Lord Shaxx, the Crucible announcer. Be loud, encouraging, and use sword ⚔️, explosion 💥, and helmet 🪖 emojis.",
            "Drifter": "You are the Drifter, the rogue Gambit handler. Speak with sly humor, streetwise slang, and a morally gray perspective. Reference Gambit and 'motes'.",
            "Mara Sov": "You are Mara Sov, the enigmatic Queen of the Awoken. Speak with regal poise, subtlety, and a sense of cosmic perspective.",
        }

    def _create_agent(self) -> Agent:
        """Creates the agent with all its tools and persona."""
        logger.debug("Creating agent with tools...")
        tools = [
            function_tool(self.get_user_info),
            function_tool(self.get_weapons),
            function_tool(self.get_catalysts),
            function_tool(self.get_pve_bis_weapons_from_sheet),
            function_tool(self.get_pve_activity_bis_weapons_from_sheet),
            function_tool(self.get_endgame_analysis_data)
            # WebSearchTool(enabled=False) # Disabled for now
        ]
        # If a persona is provided, prepend its instructions to the system prompt
        system_prompt = "You are a helpful Destiny 2 assistant, knowledgeable about game mechanics, weapons, catalysts, and lore. Your goal is to provide accurate and concise information to the player. If you need a user's specific Bungie ID or access token for a tool, and it's not provided in the context, you must call 'get_user_info' first."
        # The Runner is not passed to Agent constructor. OpenAI client is set globally.
        return Agent(name="Destiny2Assistant", instructions=system_prompt, tools=tools)

    # Tool-bound methods - these will call the _impl functions
    # Make them async if their _impl is async

    # get_user_info can remain sync if _get_user_info_impl is sync
    def get_user_info(self) -> dict:
        """Agent Tool: Fetch the user's D2 membership type and ID."""
        return _get_user_info_impl(self)

    async def get_weapons(self, membership_type: int, membership_id: str) -> list: # BECOMES ASYNC
        """Agent Tool: Fetch all weapons for a given D2 user."""
        return await _get_weapons_impl(self, membership_type, membership_id) # Use await

    async def get_catalysts(self) -> list: # BECOMES ASYNC
        """Agent Tool: Fetch all catalyst progress for the current D2 user."""
        return await _get_catalysts_impl(self) # Use await

    # Google Sheet tools remain synchronous
    def get_pve_bis_weapons_from_sheet(self) -> list[dict]:
        """Agent Tool: Fetches PvE BiS weapons from the community Google Sheet."""
        return _get_pve_bis_weapons_impl(self)

    def get_pve_activity_bis_weapons_from_sheet(self) -> list[dict]:
        """Agent Tool: Fetches PvE BiS weapons BY ACTIVITY from the community Google Sheet."""
        return _get_pve_activity_bis_weapons_impl(self)
    
    def get_endgame_analysis_data(self, sheet_name: Optional[str] = None) -> list[dict] | str:
        """Agent Tool: Fetches data from a specified sheet in the Endgame Analysis spreadsheet."""
        return _get_endgame_analysis_impl(self, sheet_name)

    async def run_chat(self, prompt: str, access_token: str, bungie_id: str, history: Optional[List[Dict[str, str]]] = None, persona: Optional[str] = None):
        logger.debug(f"DestinyAgentService run_chat called for bungie_id: {bungie_id}")
        # Set user context for this run
        self._current_access_token = access_token
        self._current_bungie_id = bungie_id
        
        # Construct the input list including history and the current user prompt
        agent_input = history or [] # Start with history or an empty list
        agent_input.append({"role": "user", "content": prompt}) # Add current user message
        
        try:
            # Execute agent using Runner.run static method, passing the list as input
            response_obj = await Runner.run(self.agent, agent_input)
            # Extract the final text output
            response_text = response_obj.final_output if hasattr(response_obj, 'final_output') else "Error: Could not get final output from agent."
            return response_text
        except (AuthenticationRequiredError, InvalidRefreshTokenError) as auth_err: # <-- CATCH AUTH ERRORS FIRST
            logger.warning(f"Authentication error during agent chat execution: {auth_err}")
            raise # Re-raise to be caught by FastAPI
        except Exception as e:
            logger.error(f"Error during agent chat execution: {e}", exc_info=True)
            # For other errors, the agent runner likely already formulated a polite response if it was tool error.
            # If it's an error in the agent execution itself, return a generic error message.
            return f"An unexpected error occurred while processing your request: {str(e)}"
        finally:
            # Clear user context after run
            self._current_access_token = None
            self._current_bungie_id = None

    def get_persona_prompt(self, persona_name: str) -> str:
        base = self.persona_map.get(persona_name, "You are a helpful Destiny 2 assistant.")
        return f"{base}\n\nAlways use relevant Destiny-themed emojis liberally in your responses to add flavor and personality!" # Encourage emoji use 

# Function to get AgentService (dependency for FastAPI)
# This needs to be updated if AgentService __init__ changes significantly,
# but since __init__ now takes pre-configured services passed from main.py's startup,
# this function might just return the global agent_service_instance initialized in main.py.
# For now, we assume agent_service_instance is correctly populated in main.py's startup.

def get_agent_service() -> DestinyAgentService:
    from web_app.backend.main import agent_service_instance # Access the global instance from main
    if agent_service_instance is None:
        # This should not happen if main.py startup_event completed successfully.
        logger.error("AgentService not initialized. Check main.py startup_event.")
        raise Exception("AgentService not available. Initialization failed.")
    return agent_service_instance 