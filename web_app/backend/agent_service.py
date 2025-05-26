# Placeholder for DestinyAgentService class

import os
from agents import Agent, Runner, function_tool, WebSearchTool, set_default_openai_client, RunContextWrapper
from .weapon_api import WeaponAPI # Use relative import
from .catalyst_api import CatalystAPI # Use relative import
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
from .models import CatalystData, CatalystObjective, Weapon # <--- ensure Weapon is imported
from .bungie_oauth import AuthenticationRequiredError, InvalidRefreshTokenError # <-- IMPORT THESE
from web_app.backend.performance_logging import log_api_performance  # Import the profiling helper
from web_app.backend.utils import normalize_catalyst_data  # Import the normalization helper
from agents.mcp import MCPServerStdio
from dataclasses import dataclass
import yaml
from langsmith import Client  # Add at the top with other imports
import hashlib  # For prompt versioning

logger = logging.getLogger(__name__)

# Define Cache Time-To-Live (TTL)
CACHE_TTL = timedelta(hours=24) # Cache data for 24 hours

SUPABASE_ACCESS_TOKEN = os.getenv("SUPABASE_ACCESS_TOKEN")
REFRESH_INTERVAL = timedelta(hours=24)

PROMPTS_PATH = os.path.join(os.path.dirname(__file__), "prompts.yaml")
PERSONAS_PATH = os.path.join(os.path.dirname(__file__), "personas.yaml")

_prompts_cache = None
_personas_cache = None

def load_prompts():
    global _prompts_cache
    if _prompts_cache is None:
        with open(PROMPTS_PATH, "r") as f:
            _prompts_cache = yaml.safe_load(f)
    return _prompts_cache

def load_personas():
    global _personas_cache
    if _personas_cache is None:
        with open(PERSONAS_PATH, "r") as f:
            _personas_cache = yaml.safe_load(f)
    return _personas_cache

def load_system_prompt():
    prompts = load_prompts()["default"]
    sections = [
        prompts.get("role", ""),
        prompts.get("objective", ""),
        prompts.get("context", ""),
        prompts.get("tools", ""),
        prompts.get("tasks", ""),
        prompts.get("operating_guidelines", ""),
        prompts.get("constraints", "")
    ]
    return "\n\n".join(section.strip() for section in sections if section.strip())

@dataclass
class AgentContext:
    user_uuid: str
    # Add other fields as needed (e.g., logger, session, etc.)

# --- Tool Implementation Functions (outside class) ---

async def _get_user_info_impl(service: 'DestinyAgentService') -> dict:
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
    import time
    api_start = time.time()
    try:
        info = await service.weapon_api.get_membership_info()
        api_duration_ms = int((time.time() - api_start) * 1000)
        # Log Bungie API call duration
        if hasattr(service, 'sb_client'):
            asyncio.create_task(log_api_performance(
                service.sb_client,
                endpoint="agent_service.get_user_info",
                operation="weapon_api.get_membership_info",
                duration_ms=api_duration_ms,
                user_id=bungie_id
            ))
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
        return {"error": f"Failed to get user info due to an internal error: {str(e)}"}

async def _get_weapons_impl(service: 'DestinyAgentService', membership_type: int, membership_id: str) -> List[Weapon]:
    """(Implementation) Fetch all weapons for a user, using Supabase as cache."""
    logger.debug(f"Agent Tool Impl: get_weapons called for {membership_type}/{membership_id}")
    access_token = service._current_access_token
    user_uuid = service._current_user_uuid  # Must be a valid UUID string

    # TODO: Ensure _current_user_uuid is set at authentication/session start
    import uuid
    if not user_uuid or not isinstance(user_uuid, str):
        logger.error(f"Supabase user_uuid is not set or not a string: {user_uuid}")
        raise Exception("Supabase user_uuid must be set to a valid UUID string before querying weapons.")
    try:
        uuid.UUID(user_uuid)
    except Exception:
        logger.error(f"Supabase user_uuid is not a valid UUID: {user_uuid}")
        raise Exception("Supabase user_uuid must be a valid UUID string.")

    now = datetime.now(timezone.utc)
    import time
    supabase_start = time.time()
    try:
        logger.info(f"Attempting to fetch weapons from Supabase cache for user {user_uuid}")
        supabase_response = await (service.sb_client.table("user_weapon_inventory")
            .select("item_instance_id, item_hash, weapon_name, weapon_type, intrinsic_perk, col1_plugs, col2_plugs, col3_trait1, col4_trait2, origin_trait, masterwork, weapon_mods, shaders, location, is_equipped, last_updated")
            .eq("user_id", user_uuid)
            .execute())
        supabase_duration_ms = int((time.time() - supabase_start) * 1000)
        await log_api_performance(
            service.sb_client,
            endpoint="agent_service.get_weapons",
            operation="supabase_cache_read",
            duration_ms=supabase_duration_ms,
            user_id=user_uuid
        )

        if supabase_response.data:
            logger.info(f"Found {len(supabase_response.data)} weapon instance entries in Supabase for user {user_uuid}")
            
            cache_is_fresh = True
            oldest_update_time = None 

            for item_dict in supabase_response.data:
                last_updated_str = item_dict.get("last_updated")
                if last_updated_str:
                    try:
                        last_updated_dt = datetime.fromisoformat(last_updated_str)
                        if oldest_update_time is None or last_updated_dt < oldest_update_time:
                            oldest_update_time = last_updated_dt
                    except ValueError:
                        logger.warning(f"Invalid date format for last_updated for item_instance_id {item_dict.get('item_instance_id')}: {last_updated_str}. Considering cache stale.")
                        cache_is_fresh = False
                        break
                else:
                    cache_is_fresh = False
                    logger.info(f"Weapon instance {item_dict.get('item_instance_id')} missing last_updated, cache STALE for user {user_uuid}")
                    break
            
            if cache_is_fresh and oldest_update_time is not None:
                if (now - oldest_update_time > CACHE_TTL):
                    cache_is_fresh = False
                    logger.info(f"Supabase weapon cache is STALE for user {user_uuid} (oldest item updated at {oldest_update_time}).")
            elif cache_is_fresh and oldest_update_time is None and supabase_response.data: 
                cache_is_fresh = False
                logger.info(f"Supabase weapon cache for user {user_uuid} has items but no valid last_updated timestamps, considering STALE.")

            if cache_is_fresh:
                logger.info(f"Supabase weapon cache is FRESH for user {user_uuid}. Reconstructing Weapon list from cache data.")
                reconstructed_weapons: List[Weapon] = []
                for item_dict in supabase_response.data:
                    weapon_data_for_model = {
                        "item_hash": str(item_dict.get("item_hash")),
                        "instance_id": item_dict.get("item_instance_id"),
                        "name": item_dict.get("weapon_name", "Unknown Name"),
                        "description": "",  # Not in DB, can be filled from manifest if needed
                        "icon_url": None,    # Not in DB, can be filled from manifest if needed
                        "tier_type": None,   # Not in DB, can be filled from manifest if needed
                        "item_type": item_dict.get("weapon_type", "Unknown Item Type"),
                        "item_sub_type": None, # Not in DB, can be filled from manifest if needed
                        "location": item_dict.get("location"),
                        "is_equipped": item_dict.get("is_equipped", False),
                        "damage_type": None, # Not in DB, can be filled from manifest if needed
                        "barrel_perks": item_dict.get("col1_plugs", []),
                        "magazine_perks": item_dict.get("col2_plugs", []),
                        "trait_perk_col1": item_dict.get("col3_trait1", []),
                        "trait_perk_col2": item_dict.get("col4_trait2", []),
                        "origin_trait": item_dict.get("origin_trait", []),
                        # Optionally add masterwork, weapon_mods, shaders if Weapon model supports them
                    }
                    try:
                        weapon = Weapon(**weapon_data_for_model)
                        reconstructed_weapons.append(weapon)
                    except Exception as e:
                        logger.error(f"Pydantic validation error reconstructing weapon {item_dict.get('item_hash')} from cache: {e}. Data: {weapon_data_for_model}")
                logger.info(f"Cache HIT: Returning {len(reconstructed_weapons)} weapons from Supabase for user {user_uuid}")
                return reconstructed_weapons
            else:
                logger.warning(f"Failed to reconstruct all ({len(reconstructed_weapons)}/{len(supabase_response.data)}) weapons from cache for user {user_uuid}. Proceeding to API call.")
                # Fall through to API call

        else: 
            logger.info(f"Cache MISS: No weapon data in Supabase for user {user_uuid}")

    except Exception as e:
        logger.error(f"Error during Supabase weapon cache read or reconstruction for user {user_uuid}: {e}", exc_info=True)
        # Fall through to API call on any error

    # Cache miss, stale, or error in cache read/reconstruction: Call API
    logger.info(f"Calling Bungie API for weapons for user {user_uuid} (membership: {membership_type}/{membership_id})")
    api_start = time.time()
    try:
        # weapon_api.get_all_weapons is expected to return List[Weapon]
        # where Weapon objects are fully populated with manifest data.
        weapons_from_api = await service.weapon_api.get_all_weapons_with_detailed_perks(
            membership_type=membership_type,
            destiny_membership_id=membership_id,
            user_id=user_uuid,
            sb_client=service.sb_client
        )
        api_duration_ms = int((time.time() - api_start) * 1000)
        await log_api_performance(
            service.sb_client,
            endpoint="agent_service.get_weapons",
            operation="weapon_api.get_all_weapons_with_detailed_perks",
            duration_ms=api_duration_ms,
            user_id=user_uuid
        )

        if weapons_from_api:
            logger.info(f"Fetched {len(weapons_from_api)} weapons from API. Storing instance data in Supabase for user {user_uuid}.")
            
            try:
                await (service.sb_client.table("user_weapon_inventory")
                    .delete()
                    .eq("user_id", user_uuid)
                    .execute())
                logger.info(f"Successfully deleted old weapon inventory for user {user_uuid} from Supabase.")
            except Exception as del_e:
                logger.error(f"Failed to delete old weapon inventory for user {user_uuid} from Supabase: {del_e}", exc_info=True)

            weapons_to_insert = []
            current_timestamp_iso = now.isoformat()
            for weapon_model in weapons_from_api: # weapon_model is now a dict
                db_weapon_entry = {
                    "user_id": user_uuid,
                    "item_instance_id": weapon_model.get("item_instance_id"),
                    "item_hash": int(weapon_model["item_hash"]) if weapon_model.get("item_hash") is not None else None,
                    "weapon_name": weapon_model.get("weapon_name"),
                    "weapon_type": weapon_model.get("weapon_type"),
                    "intrinsic_perk": weapon_model.get("intrinsic_perk"),
                    "location": weapon_model.get("location"),
                    "is_equipped": weapon_model.get("is_equipped"),
                    "col1_plugs": weapon_model.get("col1_plugs", []),
                    "col2_plugs": weapon_model.get("col2_plugs", []),
                    "col3_trait1": weapon_model.get("col3_trait1", []),
                    "col4_trait2": weapon_model.get("col4_trait2", []),
                    "origin_trait": weapon_model.get("origin_trait", []),
                    "masterwork": weapon_model.get("masterwork", []),
                    "weapon_mods": weapon_model.get("weapon_mods", []),
                    "shaders": weapon_model.get("shaders", []),
                    "last_updated": current_timestamp_iso
                }
                weapons_to_insert.append(db_weapon_entry)
            
            if weapons_to_insert:
                try:
                    insert_response = await (service.sb_client.table("user_weapon_inventory")
                        .insert(weapons_to_insert)
                        .execute())
                    
                    if hasattr(insert_response, 'error') and insert_response.error:
                         logger.error(f"Supabase insert error for weapons user {user_uuid}: {insert_response.error}")
                    elif insert_response.data:
                         logger.info(f"Successfully inserted {len(insert_response.data)} weapon instances in Supabase for user {user_uuid}.")
                    else:
                         logger.info(f"Weapon instance insert for user {user_uuid} completed; no data/error in response.")
                except Exception as ins_e:
                    logger.error(f"Failed to insert weapon instances in Supabase for user {user_uuid}: {ins_e}", exc_info=True)
            else:
                logger.info(f"No valid weapons from API to insert into Supabase for user {user_uuid}.")
        else:
            logger.info(f"No weapons returned from API for user {user_uuid}. Cache will not be updated.")
        
        return weapons_from_api

    except (AuthenticationRequiredError, InvalidRefreshTokenError) as auth_err:
        logger.warning(f"Authentication error in get_weapons: {auth_err}")
        raise 
    except Exception as e:
        logger.error(f"Agent Tool Impl Error in get_weapons during API call/Supabase write: {e}", exc_info=True)
        raise Exception(f"Failed to get weapons due to an internal error: {str(e)}")

async def _get_catalysts_impl(service: 'DestinyAgentService', user_uuid: str) -> list:
    """(Implementation) Fetch all catalyst progress for a user, using Supabase as cache."""
    logger.debug("Agent Tool Impl: get_catalysts called")
    access_token = service._current_access_token

    if not user_uuid or not access_token:
        logger.error("Agent Tool Impl Error: User UUID or Access token not set in context.")
        raise Exception("User context not available for get_catalysts.")

    now = datetime.now(timezone.utc)
    processed_catalysts_from_cache = []
    import time
    supabase_start = time.time()
    try:
        logger.info(f"Attempting to fetch catalysts from Supabase cache for user {user_uuid}")
        supabase_response = await service.sb_client.table("user_catalyst_status") \
            .select("catalyst_record_hash, is_complete, objectives, last_updated") \
            .eq("user_id", user_uuid) \
            .execute()
        supabase_duration_ms = int((time.time() - supabase_start) * 1000)
        await log_api_performance(
            service.sb_client,
            endpoint="agent_service.get_catalysts",
            operation="supabase_cache_read",
            duration_ms=supabase_duration_ms,
            user_id=user_uuid
        )

        if supabase_response.data:
            logger.info(f"Found {len(supabase_response.data)} catalyst entries in Supabase for user {user_uuid}")
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
                        logger.info(f"Supabase cache for catalyst {cached_item_dict.get('catalyst_record_hash')} is STALE for user {user_uuid}.")
                        break # One stale item makes the whole cache miss for now
                else:
                    all_cache_fresh = False # Missing last_updated means it's effectively stale
                    logger.info(f"Supabase cache for catalyst {cached_item_dict.get('catalyst_record_hash')} has no last_updated timestamp for user {user_uuid}.")
                    break
            
            if all_cache_fresh:
                logger.info(f"Supabase catalyst cache is FRESH for user {user_uuid}. Reconstructing CatalystData.")
                
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
                            is_complete=cached_item_dict["is_complete"],
                            progress=overall_progress # Placeholder/Simple Derivation
                            # record_hash is not part of CatalystData model, but we have it.
                        )
                    )
                if processed_catalysts_from_cache: # If we successfully reconstructed some/all items
                    logger.info(f"Cache HIT: Returning {len(processed_catalysts_from_cache)} catalysts from Supabase for user {user_uuid}")
                    return processed_catalysts_from_cache
                else:
                    # This case means we found entries, they were fresh, but failed to process all of them.
                    logger.warning(f"Found fresh cache entries for user {user_uuid} but failed to reconstruct CatalystData for all items. Proceeding to API call.")
                    all_cache_fresh = False # Treat as a cache miss to force API refresh

        else:
            logger.info(f"Cache MISS: No catalyst data in Supabase for user {user_uuid}")
            all_cache_fresh = False # Explicitly a cache miss

    except Exception as e:
        logger.error(f"Error during Supabase catalyst cache check for user {user_uuid}: {e}", exc_info=True)
        all_cache_fresh = False # Treat as a cache miss on error

    # If cache was not fresh, or empty, or error during cache check: Call API
    if not all_cache_fresh:
        logger.info(f"Calling Bungie API for catalysts for user {user_uuid} due to cache miss or staleness.")
        api_start = time.time()
        try:
            # This is expected to return List[CatalystData] or list of dicts that can be validated into it
            # It should include record_hash if it's a list of dicts.
            api_catalysts_result = await service.catalyst_api.get_catalysts()
            api_duration_ms = int((time.time() - api_start) * 1000)
            await log_api_performance(
                service.sb_client,
                endpoint="agent_service.get_catalysts",
                operation="catalyst_api.get_catalysts",
                duration_ms=api_duration_ms,
                user_id=user_uuid
            )

            # Prepare data for Supabase upsert
            catalysts_to_upsert = []
            # The result from get_catalysts should be List[CatalystData] or conform to it.
            # We need to ensure record_hash is available for each item to use as primary key for upsert.
            # Assuming service.catalyst_api.get_catalysts() result contains objects/dicts that have a 'record_hash' field/key.
            # For now, this part requires that the objects returned by get_catalysts have a .record_hash attribute.
            # And that CatalystData has .name, .description, .objectives, .is_complete, .progress fields.

            # Re-validate/structure into CatalystData if not already
            validated_api_catalysts = [] # Will store tuples of (CatalystData, record_hash_str)
            for item_data in api_catalysts_result: # item_data is a dict from catalyst_api
                if isinstance(item_data, dict):
                    current_record_hash = item_data.get('record_hash')
                    if not current_record_hash:
                        logger.warning(f"API item_data missing 'record_hash': {item_data.get('name', 'Unknown Catalyst')}")
                        continue
                    try:
                        # Normalize the dict before validation
                        normalized_item_data = normalize_catalyst_data(item_data)
                        validated_item = CatalystData(**normalized_item_data)
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
                    "user_id": user_uuid,
                    "catalyst_record_hash": catalyst_hash_int,
                    "is_complete": item.is_complete,
                    "objectives": json.dumps(objectives_for_json),
                    "last_updated": now.isoformat()
                })
            
            if catalysts_to_upsert:
                try:
                    supabase_upsert_response = await service.sb_client.table("user_catalyst_status").upsert(catalysts_to_upsert).execute()
                    if supabase_upsert_response.data:
                        logger.info(f"Successfully upserted/updated {len(supabase_upsert_response.data)} catalysts to Supabase for user {user_uuid}")
                    else:
                        # Log error but don't fail the whole operation if some items were processed
                        logger.error(f"Supabase upsert for catalysts failed or returned no data for user {user_uuid}. Error: {supabase_upsert_response.error}")
                except Exception as db_e:
                    logger.error(f"Exception during Supabase catalyst upsert for user {user_uuid}: {db_e}", exc_info=True)
            
            logger.info(f"Cache SET: Returning {[item for item, _ in validated_api_catalysts]} catalysts from API for user {user_uuid}") # Return only CatalystData objects
            return [item for item, _ in validated_api_catalysts] # Return only CatalystData objects

        except (AuthenticationRequiredError, InvalidRefreshTokenError) as auth_err: # <-- CATCH SPECIFIC AUTH ERRORS
            logger.warning(f"Authentication error in get_catalysts API call: {auth_err}")
            raise # Re-raise auth-specific errors
        except Exception as e:
            logger.error(f"Error calling Bungie API for catalysts for user {user_uuid}: {e}", exc_info=True)
            # Return an error structure or empty list for the agent if API fails for other reasons
            return {"error": f"Failed to fetch catalysts from API due to an internal error: {str(e)}"}
    
    # This should ideally not be reached if all_cache_fresh was true and processing happened,
    # but as a fallback if cache was fresh but processing failed to return.
    logger.warning(f"Returning empty list or error for _get_catalysts_impl for user {user_uuid} as no data path was conclusive.")
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

# --- Data Refresh Logic ---
async def refresh_user_data_if_stale(user_id, sb_client, bungie_api):
    result = await sb_client.table("user_weapon_inventory").select("last_updated").eq("user_id", user_id).order("last_updated", desc=True).limit(1).execute()
    last_updated = None
    if result.data and result.data[0].get("last_updated"):
        last_updated = datetime.fromisoformat(result.data[0]["last_updated"])
    if last_updated is None or (datetime.utcnow() - last_updated) > REFRESH_INTERVAL:
        weapons = await bungie_api.fetch_weapons(user_id)
        catalysts = await bungie_api.fetch_catalysts(user_id)
        await sb_client.table("user_weapon_inventory").upsert(weapons).execute()
        await sb_client.table("user_catalyst_status").upsert(catalysts).execute()

# --- DestinyAgentService Refactor ---
class DestinyAgentService:
    SUPABASE_PROJECT_ID = "grwqemflswabswphkute"
    def __init__(self, openai_client, catalyst_api, weapon_api, sb_client, manifest_service):
        logger.info("Initializing DestinyAgentService with pre-configured API clients and Supabase client.")
        self.openai_client = openai_client
        set_default_openai_client(self.openai_client) # Set for the agents library
        self.catalyst_api = catalyst_api
        self.weapon_api = weapon_api
        self.sb_client = sb_client 
        self.manifest_service = manifest_service

        prompts = load_prompts()
        self.DEFAULT_AGENT_SYSTEM_PROMPT = load_system_prompt()
        self.AGENT_CORE_ABILITIES_PROMPT = prompts["default"]["core_abilities"]
        self.SUPABASE_MCP_ACCESS_PROMPT = prompts["default"]["supabase_access"]
        self.EMOJI_ENCOURAGEMENT = prompts["default"]["emoji_encouragement"]
        self.persona_map = load_personas()
        
        self.supabase_mcp_server = None
        self.supabase_mcp_server_started = False
        self._main_agent_mcp_servers = []
        # Default agent created with a combined default system prompt
        default_full_system_prompt = f"{self.DEFAULT_AGENT_SYSTEM_PROMPT} {self.AGENT_CORE_ABILITIES_PROMPT} {self.SUPABASE_MCP_ACCESS_PROMPT} {self.EMOJI_ENCOURAGEMENT}"
        self.agent = self._create_agent_internal(instructions=default_full_system_prompt)
        # Add MCP servers to agent if any (will be updated by start_supabase_mcp_server)
        if self._main_agent_mcp_servers:
            self.agent.mcp_servers = self._main_agent_mcp_servers

        self._current_access_token: Optional[str] = None
        self._current_bungie_id: Optional[str] = None
        self._current_user_uuid: Optional[str] = None
        self._current_project_id = self.SUPABASE_PROJECT_ID
        
        self._user_info_cache: Dict[str, tuple[datetime, dict]] = {}
        self._sheet_cache: Dict[str, tuple[datetime, list[dict]]] = {}
        self.langsmith_client = Client()

    def _create_agent_internal(self, instructions: str) -> Agent:
        """Internal helper to create an agent instance with specific instructions."""
        logger.debug(f"Creating agent with instructions: '{instructions[:100]}...'" ) # Log first 100 chars
        tools = [
            # get_user_info,
            # get_weapons,
            # get_catalysts,
            # get_pve_bis_weapons_from_sheet,
            # get_pve_activity_bis_weapons_from_sheet,
            # get_endgame_analysis_data
        ]
        return Agent(
            name="Destiny2Assistant",
            instructions=instructions,
            tools=tools,
            model="gpt-4o",
            mcp_servers=getattr(self, '_main_agent_mcp_servers', [])
        )

    async def start_supabase_mcp_server(self):
        if self.supabase_mcp_server_started:
            logger.info("Supabase MCP server already started.")
            return  # Already started
        self.supabase_mcp_server = MCPServerStdio(
            params={
                "command": "npx",
                "args": [
                    "-y",
                    "@supabase/mcp-server-supabase@latest",
                    "--access-token",
                    SUPABASE_ACCESS_TOKEN,
                    "--project-ref",
                    "grwqemflswabswphkute",
                ],
            }
        )
        await self.supabase_mcp_server.__aenter__()
        # Ensure all future agents inherit the MCP server
        if self.supabase_mcp_server not in self._main_agent_mcp_servers:
            self._main_agent_mcp_servers.append(self.supabase_mcp_server)
        self.supabase_mcp_server_started = True
        logger.info("Supabase MCP server started and attached to agent.")

        # List and log available tools
        try:
            tools = await self.supabase_mcp_server.list_tools()
            logger.info(f"Available tools from Supabase MCP: {[tool.name for tool in tools]}")
        except Exception as e:
            logger.error(f"Failed to list tools from Supabase MCP: {e}")

    async def close_supabase_mcp_server(self):
        if self.supabase_mcp_server and self.supabase_mcp_server_started:
            await self.supabase_mcp_server.__aexit__(None, None, None)
            self.supabase_mcp_server_started = False

    async def answer_user_query(self, user_input: str):
        # Ensure MCP server is started before using the agent
        if not self.supabase_mcp_server_started:
            await self.start_supabase_mcp_server()
        context = {"user_uuid": self._current_user_uuid}
        result = await Runner.run(self.agent, input=user_input, context=context, max_turns=25)
        return result

    # Optionally, keep legacy methods for direct DB/API access for refresh only
    async def refresh_user_data(self, user_id):
        await refresh_user_data_if_stale(user_id, self.sb_client, self.weapon_api)

    async def run_chat(self, prompt: str, access_token: str, bungie_id: str, supabase_uuid: str, history: Optional[List[Dict[str, str]]] = None, persona: Optional[str] = None, conversation_id: Optional[str] = None, message_id: Optional[str] = None):
        logger.debug(f"DestinyAgentService run_chat called for bungie_id: {bungie_id}, persona: {persona}")
        self._current_access_token = access_token
        self._current_bungie_id = bungie_id
        self._current_user_uuid = supabase_uuid  # Use the real Supabase UUID
        agent_to_use = self.agent # Default to the standard agent

        uuid_instructions = f"The user's UUID is: {self._current_user_uuid}. Always use this UUID for any user-specific queries or tool calls. "

        if persona:
            persona_base_instructions = self.persona_map.get(persona)
            if persona_base_instructions:
                effective_system_prompt = (
                    f"{persona_base_instructions} "
                    f"{self.AGENT_CORE_ABILITIES_PROMPT} "
                    f"{uuid_instructions}"
                    f"{self.SUPABASE_MCP_ACCESS_PROMPT} "
                    f"{self.EMOJI_ENCOURAGEMENT} "
                )
                logger.info(f"Using effective system prompt for persona '{persona}': '{effective_system_prompt[:150]}...'")
                agent_to_use = self._create_agent_internal(instructions=effective_system_prompt)
                # Attach MCP server if started
                if self.supabase_mcp_server and self.supabase_mcp_server_started:
                    if not hasattr(agent_to_use, "mcp_servers"):
                        agent_to_use.mcp_servers = []
                    if self.supabase_mcp_server not in agent_to_use.mcp_servers:
                        agent_to_use.mcp_servers.append(self.supabase_mcp_server)
            else:
                logger.warning(f"Persona '{persona}' selected but no matching instructions found in persona_map. Using default agent.")
        else:
            # Default agent with UUID injected
            default_full_system_prompt = (
                f"{self.DEFAULT_AGENT_SYSTEM_PROMPT} "
                f"{uuid_instructions}"
            )
            agent_to_use = self._create_agent_internal(instructions=default_full_system_prompt)
            if self.supabase_mcp_server and self.supabase_mcp_server_started:
                if not hasattr(agent_to_use, "mcp_servers"):
                    agent_to_use.mcp_servers = []
                if self.supabase_mcp_server not in agent_to_use.mcp_servers:
                    agent_to_use.mcp_servers.append(self.supabase_mcp_server)

        messages_for_run: List[Dict[str, str]] = []
        if history:
            messages_for_run.extend(history)
        messages_for_run.append({"role": "user", "content": prompt})

        import time
        total_start = time.time()
        weapon_fetch_duration = None
        catalyst_fetch_duration = None
        manifest_lookup_duration = None
        llm_duration = None
        try:
            # --- Profile weapon fetch ---
            weapon_start = time.time()
            # Simulate or call weapon fetch if part of the flow
            # weapons = await self.get_weapons(...)
            weapon_fetch_duration = int((time.time() - weapon_start) * 1000)
            await log_api_performance(
                self.sb_client,
                endpoint="agent_service.run_chat",
                operation="weapon_fetch",
                duration_ms=weapon_fetch_duration,
                user_id=bungie_id,
                conversation_id=conversation_id,
                message_id=message_id
            )
            # --- Profile catalyst fetch ---
            catalyst_start = time.time()
            # Simulate or call catalyst fetch if part of the flow
            # catalysts = await self.get_catalysts(...)
            catalyst_fetch_duration = int((time.time() - catalyst_start) * 1000)
            await log_api_performance(
                self.sb_client,
                endpoint="agent_service.run_chat",
                operation="catalyst_fetch",
                duration_ms=catalyst_fetch_duration,
                user_id=bungie_id,
                conversation_id=conversation_id,
                message_id=message_id
            )
            # --- Profile manifest lookups ---
            manifest_start = time.time()
            # Simulate or call manifest lookups if part of the flow
            # ...
            manifest_lookup_duration = int((time.time() - manifest_start) * 1000)
            await log_api_performance(
                self.sb_client,
                endpoint="agent_service.run_chat",
                operation="manifest_lookup",
                duration_ms=manifest_lookup_duration,
                user_id=bungie_id,
                conversation_id=conversation_id,
                message_id=message_id
            )
            # --- Profile LLM call ---
            llm_start = time.time()
            response_obj = await Runner.run(agent_to_use, messages_for_run, context={"user_uuid": self._current_user_uuid}, max_turns=25)
            llm_duration = int((time.time() - llm_start) * 1000)
            await log_api_performance(
                self.sb_client,
                endpoint="agent_service.run_chat",
                operation="llm_call",
                duration_ms=llm_duration,
                user_id=bungie_id,
                conversation_id=conversation_id,
                message_id=message_id
            )
            response_text = response_obj.final_output if hasattr(response_obj, 'final_output') else "Error: Could not get final output from agent."

            # --- LangSmith Logging ---
            # Compute prompt version as a hash of the system prompt (including persona if used)
            system_prompt = agent_to_use.instructions
            prompt_version = hashlib.sha256(system_prompt.encode("utf-8")).hexdigest()[:8]  # Short hash
            try:
                self.langsmith_client.create_run(
                    name="agent_chat",
                    run_type="llm",
                    inputs={
                        "user_uuid": self._current_user_uuid,
                        "persona": persona,
                        "prompt_version": prompt_version,
                        "system_prompt": system_prompt,
                        "user_input": prompt,
                        "history": history,
                    },
                    outputs={"response": response_text},
                    tags=["agent_chat", prompt_version, persona or "default"]
                )
            except Exception as e:
                logger.warning(f"LangSmith logging failed: {e}")
            # --- End LangSmith Logging ---

            return response_text
        except (AuthenticationRequiredError, InvalidRefreshTokenError) as auth_err:
            logger.warning(f"Authentication error during agent chat execution: {auth_err}")
            raise 
        except Exception as e:
            logger.error(f"Error during agent chat execution: {e}", exc_info=True)
            return f"An unexpected error occurred while processing your request: {str(e)}"
        finally:
            total_duration_ms = int((time.time() - total_start) * 1000)
            await log_api_performance(
                self.sb_client,
                endpoint="agent_service.run_chat",
                operation="total_run_chat",
                duration_ms=total_duration_ms,
                user_id=bungie_id,
                conversation_id=conversation_id,
                message_id=message_id
            )
            # Alert if any sub-operation or total duration exceeds 10 seconds
            threshold = 10000
            if (weapon_fetch_duration and weapon_fetch_duration > threshold) or \
               (catalyst_fetch_duration and catalyst_fetch_duration > threshold) or \
               (manifest_lookup_duration and manifest_lookup_duration > threshold) or \
               (llm_duration and llm_duration > threshold) or \
               (total_duration_ms > threshold):
                await log_api_performance(
                    self.sb_client,
                    endpoint="agent_service.run_chat",
                    operation="slow_request_alert",
                    duration_ms=total_duration_ms,
                    user_id=bungie_id,
                    conversation_id=conversation_id,
                    message_id=message_id,
                    extra_data={
                        "weapon_fetch_duration": weapon_fetch_duration,
                        "catalyst_fetch_duration": catalyst_fetch_duration,
                        "manifest_lookup_duration": manifest_lookup_duration,
                        "llm_duration": llm_duration,
                        "total_duration_ms": total_duration_ms
                    }
                )
            self._current_access_token = None
            self._current_bungie_id = None
            self._current_user_uuid = None

    def get_persona_prompt(self, persona_name: str) -> str:
        # This method might become less necessary or simplified
        # as persona instructions are now directly used from persona_map
        # and combined with core abilities in run_chat.
        # For now, let it return the base persona instruction from the map.
        return self.persona_map.get(persona_name, f"{self.DEFAULT_AGENT_SYSTEM_PROMPT}")

# --- Agent tool functions for OpenAI Agents SDK ---
@function_tool
async def get_user_info(ctx: RunContextWrapper['DestinyAgentService']) -> dict:
    """
    Fetch the user's D2 membership type and ID. Use this tool to retrieve the user's Bungie membership information when needed for other operations.
    """
    return await _get_user_info_impl(ctx.context)

@function_tool
async def get_weapons(ctx: RunContextWrapper['DestinyAgentService'], membership_type: int, membership_id: str) -> list:
    """
    Fetch all weapons for a user, using Supabase as cache.
    """
    return await _get_weapons_impl(ctx.context, membership_type, membership_id)

@function_tool
async def get_catalysts(ctx: RunContextWrapper['DestinyAgentService'], user_uuid: str) -> list:
    """
    Fetch all catalyst progress for a user, using Supabase as cache.
    """
    return await _get_catalysts_impl(ctx.context, user_uuid)

@function_tool
async def get_pve_bis_weapons_from_sheet(ctx: RunContextWrapper['DestinyAgentService']) -> list:
    """
    Fetches PvE BiS weapons from the public Google Sheet.
    """
    return _get_pve_bis_weapons_impl(ctx.context)

@function_tool
async def get_pve_activity_bis_weapons_from_sheet(ctx: RunContextWrapper['DestinyAgentService']) -> list:
    """
    Fetches PvE BiS weapons BY ACTIVITY from the public Google Sheet.
    """
    return _get_pve_activity_bis_weapons_impl(ctx.context)

@function_tool
async def get_endgame_analysis_data(ctx: RunContextWrapper['DestinyAgentService'], sheet_name: str = None) -> list | str:
    """
    Fetches data from a specific sheet in the Endgame Analysis spreadsheet using the Google Sheets API and a service account.
    """
    return _get_endgame_analysis_impl(ctx.context, sheet_name)

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