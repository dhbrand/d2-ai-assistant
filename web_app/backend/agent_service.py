# Placeholder for DestinyAgentService class

import os
from agents import Agent, Runner, function_tool, WebSearchTool
from .weapon_api import WeaponAPI # Use relative import
from .catalyst import CatalystAPI # Use relative import
from .manifest import ManifestManager # Use relative import
import logging
import functools # Import functools
import asyncio # Import asyncio
from datetime import datetime, timedelta, timezone # Import datetime components
import pandas as pd # <--- Import pandas
from typing import Optional, List, Dict
import requests
import xml.etree.ElementTree as ET
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import difflib
import re

logger = logging.getLogger(__name__)

# Define Cache Time-To-Live (TTL)
CACHE_TTL = timedelta(minutes=30) # Cache data for 30 minutes

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
        info = service.weapon_api.get_membership_info(access_token)
        if not info or 'id' not in info or 'type' not in info:
            logger.warning("Agent Tool Impl: get_membership_info returned incomplete data.")
            return {"error": "Could not retrieve valid membership info."}

        # Store in cache
        service._user_info_cache[bungie_id] = (now, info)
        logger.info(f"Cache SET for user_info for bungie_id {bungie_id}")
        return info
    except Exception as e:
        logger.error(f"Agent Tool Impl Error in get_user_info: {e}", exc_info=True)
        raise # Re-raise the exception for the agent runner to handle

def _get_weapons_impl(service: 'DestinyAgentService', membership_type: int, membership_id: str) -> list:
    """(Implementation) Fetch all weapons for a user, using cache."""
    # Note: membership_type/id are required by the API call itself,
    # but we use bungie_id (primary account identifier) for caching consistency.
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
        weapons_data = service.weapon_api.get_all_weapons(
            access_token=access_token,
            membership_type=membership_type,
            destiny_membership_id=membership_id
        )
        # Store in cache (converting Pydantic models to dicts might be safer for serialization/agent)
        # For now, storing the list of Pydantic objects directly.
        service._weapons_cache[bungie_id] = (now, weapons_data)
        logger.info(f"Cache SET for weapons for bungie_id {bungie_id}")
        return weapons_data
    except Exception as e:
        logger.error(f"Agent Tool Impl Error in get_weapons: {e}", exc_info=True)
        raise

def _get_catalysts_impl(service: 'DestinyAgentService') -> list:
    """(Implementation) Fetch all catalyst progress for a user, using cache."""
    logger.debug("Agent Tool Impl: get_catalysts called")
    bungie_id = service._current_bungie_id
    access_token = service._current_access_token

    if not bungie_id or not access_token:
        logger.error("Agent Tool Impl Error: Bungie ID or Access token not set in context.")
        raise Exception("User context not available for get_catalysts.")

    # Check cache
    now = datetime.now(timezone.utc)
    if bungie_id in service._catalysts_cache:
        timestamp, cached_data = service._catalysts_cache[bungie_id]
        if now - timestamp < CACHE_TTL:
            logger.info(f"Cache HIT for catalysts for bungie_id {bungie_id}")
            return cached_data
        else:
            logger.info(f"Cache STALE for catalysts for bungie_id {bungie_id}")
    else:
        logger.info(f"Cache MISS for catalysts for bungie_id {bungie_id}")

    # Cache miss or stale, call API
    try:
        catalysts_data = service.catalyst_api.get_catalysts(access_token)
        # Store in cache (again, assuming Pydantic models or dicts)
        service._catalysts_cache[bungie_id] = (now, catalysts_data)
        logger.info(f"Cache SET for catalysts for bungie_id {bungie_id}")
        return catalysts_data
    except Exception as e:
        logger.error(f"Agent Tool Impl Error in get_catalysts: {e}", exc_info=True)
        raise

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
    def __init__(self, bungie_api_key: str, openai_api_key: str, manifest_manager: ManifestManager):
        if not openai_api_key:
            raise ValueError("OpenAI API key is required for DestinyAgentService")
        
        logger.info("Initializing DestinyAgentService...")
        self.bungie_api_key = bungie_api_key
        self.openai_api_key = openai_api_key # Store OpenAI key if needed later for client
        self.manifest_manager = manifest_manager
        
        # Initialize API clients within the service
        self.weapon_api = WeaponAPI(api_key=self.bungie_api_key, manifest_manager=self.manifest_manager)
        self.catalyst_api = CatalystAPI(api_key=self.bungie_api_key, manifest_manager=self.manifest_manager)
        
        # Initialize caches
        self._user_info_cache = {} # { bungie_id: (timestamp, data) }
        self._weapons_cache = {}   # { bungie_id: (timestamp, data) }
        self._catalysts_cache = {} # { bungie_id: (timestamp, data) }
        self._sheet_cache = {}      # { cache_key: (timestamp, data) }

        # Variables to hold context for the current run
        self._current_access_token: str | None = None
        self._current_bungie_id: str | None = None
        
        # Create the agent instance (moved agent creation logic here)
        try:
             self.agent = self._create_agent()
             logger.info("DestinyAgentService agent created successfully.")
        except Exception as e:
            logger.error(f"Failed to create agent during DestinyAgentService initialization: {e}", exc_info=True)
            # Depending on requirements, you might want to raise this error
            # or allow the service to initialize without a functional agent.
            # For now, we log and continue, but run_chat will fail later.
            self.agent = None

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
        """Creates the Agent instance with instructions and tools."""
        
        # Create partials first (these hold the 'self' context)
        partial_get_user_info = functools.partial(_get_user_info_impl, service=self)
        partial_get_weapons = functools.partial(_get_weapons_impl, service=self)
        partial_get_catalysts = functools.partial(_get_catalysts_impl, service=self)
        partial_get_pve_weapons = functools.partial(_get_pve_bis_weapons_impl, service=self)
        partial_get_activity_weapons = functools.partial(_get_pve_activity_bis_weapons_impl, service=self)
        partial_get_endgame_analysis = functools.partial(_get_endgame_analysis_impl, service=self)

        # Now, define wrapper functions that call the partials.
        # Decorate these wrappers with @function_tool.
        
        @function_tool
        def get_user_info() -> dict:
            """Fetch the user's Destiny membership info (required before fetching weapons)."""
            return partial_get_user_info()

        @function_tool
        def get_weapons(membership_type: int, membership_id: str) -> list:
            """Fetch all weapons for a user given their membership_type and membership_id (obtained from get_user_info)."""
            return partial_get_weapons(membership_type=membership_type, membership_id=membership_id)
        
        @function_tool
        def get_catalysts() -> list:
            """Fetch all catalyst progress for the user."""
            return partial_get_catalysts()

        @function_tool
        def get_pve_bis_weapons_from_sheet() -> list[dict]:
            """
            Fetches the list of community-recommended PvE Best-in-Slot (BiS) LEGENDARY weapons for The Final Shape from a general PvE spreadsheet.
            Use this ONLY for general weapon recommendations by type or slot. Do NOT use this tool if the user mentions 'endgame analysis' or requests a specific sheet from the Endgame Analysis spreadsheet.
            """
            return partial_get_pve_weapons()
            
        # ---> ADDED: Wrapper for the second sheet tool <---
        @function_tool
        def get_pve_activity_bis_weapons_from_sheet() -> list[dict]:
            """
            Fetches community weapon recommendations SPECIFICALLY FOR DIFFERENT PVE ACTIVITIES (e.g., raids, dungeons, nightfalls) from a public Google Sheet. Use this to find what weapons are good for a particular activity.
            """
            return partial_get_activity_weapons()

        # ---> MODIFIED: Wrapper for the Endgame Analysis tool <---
        @function_tool
        def get_endgame_analysis_data(sheet_name: Optional[str] = None) -> list[dict] | str:
            """
            Fetches data from the 'Destiny 2: Endgame Analysis' community spreadsheet.
            Use this tool ONLY if the user mentions 'endgame analysis' or requests a detailed breakdown from that specific spreadsheet.
            You MUST specify a 'sheet_name' (e.g., 'Archetypes', 'Perks', 'Shotguns', 'Shopping List', 'Auto Rifles').
            The sheet_name does NOT need to be exact; fuzzy and partial matches are supported (e.g., 'auto rifles', 'autorifle', 'autorifles', etc. will all match the 'Auto Rifles' sheet).
            If the user does not specify a sheet_name, return a list of available sheets.
            """
            return partial_get_endgame_analysis(sheet_name=sheet_name)

        # The agent needs the decorated wrapper functions
        agent_tools = [
            get_user_info, 
            get_weapons, 
            get_catalysts,
            get_pve_bis_weapons_from_sheet, 
            get_pve_activity_bis_weapons_from_sheet, 
            get_endgame_analysis_data,
            WebSearchTool()
        ]
        
        agent = Agent(
            name="Destiny2Agent",
            instructions=(
                "You are a Destiny 2 assistant. Use the tools to fetch the user's info, weapons, and catalysts as needed. "
                "You can also consult community-curated spreadsheets for weapon recommendations and analysis: " 
                "1. Use 'get_pve_bis_weapons_from_sheet' for general PvE LEGENDARY weapon recommendations by type/slot. "
                "2. Use 'get_pve_activity_bis_weapons_from_sheet' for recommendations specific to PvE ACTIVITIES like raids or dungeons. " 
                "3. Use 'get_endgame_analysis_data' for detailed information from the 'Endgame Analysis' sheet. **You MUST specify a 'sheet_name' when calling this tool (e.g., 'Archetypes', 'Perks', 'Shotguns', 'Shopping List').** " # Emphasized sheet_name requirement
                "When using the get_weapons tool, you MUST first use the get_user_info tool to get the required membership_type and membership_id. "
                "When presenting catalyst information, list completed catalysts separately from incomplete ones. "
                "For incomplete catalysts, ALWAYS include the specific objective description(s) along with the progress (e.g., 'Targets defeated: 150/500'). Do not just show a percentage."
                "\n\n**NEW CAPABILITY:** You also have a 'WebSearchTool' available. Use it to find information about current events, topics outside of Destiny 2, or details not covered by the specific Destiny tools or spreadsheets (e.g., recent TWID summaries, external community guides, general knowledge)."
            ),
            model="gpt-4.1",
            tools=agent_tools,
        )
        return agent

    # --- Run Method (now async) ---
    
    async def run_chat(self, prompt: str, access_token: str, bungie_id: str, history: Optional[List[Dict[str, str]]] = None, persona: Optional[str] = None):
        """Runs the agent for a single chat turn asynchronously, using conversation history and persona."""
        if not self.agent:
             logger.error("Agent is not initialized. Cannot run chat.")
             return {"error": "Agent service not available"}
        messages_for_agent = history if history is not None else []
        if not messages_for_agent or messages_for_agent[-1]["content"] != prompt or messages_for_agent[-1]["role"] != "user":
             logger.warning("History format mismatch or latest prompt missing from history. Appending prompt.")
             messages_for_agent.append({"role": "user", "content": prompt})
        log_prompt_info = f"with history ({len(messages_for_agent)} messages)" if messages_for_agent else f"with prompt: '{prompt[:30]}...'"
        logger.info(f"Running agent async {log_prompt_info}. Access token set. Bungie ID: {bungie_id}")
        self._current_access_token = access_token
        self._current_bungie_id = bungie_id
        # --- Persona logic ---
        persona_instructions = ""
        if persona and persona in self.persona_map:
            persona_instructions = f"\n\n[Persona Mode: {persona}] {self.get_persona_prompt(persona)}\n"
        try:
            # Prepend persona instructions to the agent's system prompt for this run
            orig_instructions = self.agent.instructions
            self.agent.instructions = orig_instructions + persona_instructions
            logger.info(f"Agent persona set to: {persona if persona else 'Default'}")
            result = await Runner.run(self.agent, messages_for_agent)
            self.agent.instructions = orig_instructions  # Reset after run
            logger.info("Agent run completed.")
            return result 
        except Exception as e:
            logger.error(f"Error during agent run: {e}", exc_info=True)
            return {"error": f"An error occurred while processing your request: {e}"} 
        finally:
            self._current_access_token = None
            self._current_bungie_id = None
            logger.debug("Agent context (token, user_id) cleared.") 

    def get_persona_prompt(self, persona_name: str) -> str:
        base = self.persona_map.get(persona_name, "You are a helpful Destiny 2 assistant.")
        return f"{base}\n\nAlways use relevant Destiny-themed emojis liberally in your responses to add flavor and personality!" # Encourage emoji use 