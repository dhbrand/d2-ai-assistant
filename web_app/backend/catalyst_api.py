import os
import json
import logging
from typing import List, Dict, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import requests
import time
from threading import Event
from .catalyst_hashes import CATALYST_RECORD_HASHES
import hashlib
import pathlib
from .manifest import SupabaseManifestService
import asyncio

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Record state flags from Destiny 2 API
class DestinyRecordState:
    NONE = 0
    RECORD_REDEEMED = 1
    REWARD_UNAVAILABLE = 2
    OBJECTIVE_NOT_COMPLETED = 4
    OBSCURED = 8
    INVISIBLE = 16
    ENTITLEMENT_UNOWNED = 32
    CAN_EQUIP_TITLE = 64

class CatalystAPI:
    def __init__(self, oauth_manager, manifest_service: SupabaseManifestService):
        """Initialize the Catalyst API with OAuthManager and SupabaseManifestService."""
        self.base_url = "https://www.bungie.net/Platform"
        self.oauth_manager = oauth_manager
        self.session = self._create_session()
        self.cancel_event = Event()  # For cancelling operations
        self.discovery_mode = False  # Default to standard mode (known catalysts only)
        self.manifest_service = manifest_service
        
    def _create_session(self) -> requests.Session:
        """Create a requests session with retry logic"""
        session = requests.Session()
        retry = Retry(
            total=3,  # Increased retries
            backoff_factor=1,  # Increased backoff
            status_forcelist=[500, 502, 503, 504]
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session
        
    def _get_authenticated_headers(self) -> Dict[str, str]:
        """Gets the necessary headers for authenticated Bungie API requests."""
        # Get headers from OAuthManager, which handles refresh
        return self.oauth_manager.get_headers()
        
    async def get_membership_info(self) -> Optional[Dict[str, str]]:
        """Get the current user's membership info"""
        if self.cancel_event.is_set():
            return None
            
        try:
            url = f"{self.base_url}/User/GetMembershipsForCurrentUser/"
            logger.info(f"Fetching membership from: {url}")
            headers = self._get_authenticated_headers()
            response = self.session.get(url, headers=headers, timeout=8)
            if response.status_code != 200:
                logger.error(f"Failed to get membership info: {response.status_code} - {response.text}")
                return None
                
            data = response.json()
            if 'Response' not in data or not data['Response'].get('destinyMemberships'):
                logger.error("No destiny memberships found in response")
                return None
                
            membership = data['Response']['destinyMemberships'][0]
            logger.info(f"Found membership - Type: {membership['membershipType']}, ID: {membership['membershipId']}")
            return {
                'type': membership['membershipType'],
                'id': membership['membershipId']
            }
        except Exception as e:
            logger.error(f"Error getting membership info: {e}")
            return None
            
    async def get_profile(self, membership_type: int, membership_id: str) -> Optional[Dict]:
        """Get the user's profile with records"""
        if self.cancel_event.is_set():
            return None
            
        try:
            url = f"{self.base_url}/Destiny2/{membership_type}/Profile/{membership_id}/"
            
            # Request only components relevant to catalyst records/collectibles
            components = [
                "800",  # Profile collectibles (Might be needed to check weapon ownership?)
                "900"   # Profile records (Essential for catalyst status)
            ]
            
            params = {
                "components": ",".join(components)
            }
            logger.info("Fetching profile data with components: %s", params["components"])
            
            headers = self._get_authenticated_headers()
            response = self.session.get(url, headers=headers, params=params, timeout=15)
            logger.info("API URL: %s", response.url)
            
            if response.status_code != 200:
                logger.error(f"Failed to get profile: {response.status_code}")
                if response.text:
                    logger.error(f"Error response: {response.text}")
                return None
                
            data = response.json()
            if not data.get('Response'):
                logger.error("No Response field in profile data")
                return None
                
            # Log what components we got back
            components = data['Response'].keys()
            logger.info("Received profile components: %s", list(components))
            
            return data
            
        except Exception as e:
            logger.error(f"Error getting profile: {e}")
            return None
            
    def _get_record_state(self, record):
        """Get the state of a record using the same logic as DIM."""
        state = record.get('state', 0)
        logger.debug(f"Record state flags: {state}")
        
        # Check individual flags
        is_not_completed = bool(state & DestinyRecordState.OBJECTIVE_NOT_COMPLETED)
        is_redeemed = bool(state & DestinyRecordState.RECORD_REDEEMED)
        is_obscured = bool(state & DestinyRecordState.OBSCURED)
        is_invisible = bool(state & DestinyRecordState.INVISIBLE)
        
        logger.debug(f"State breakdown - Not Completed: {is_not_completed}, Redeemed: {is_redeemed}, Obscured: {is_obscured}, Invisible: {is_invisible}")
        
        return {
            'complete': (not is_not_completed) or is_redeemed,  # Complete if either objectives are done or it's redeemed
            'unlocked': not is_obscured,
            'visible': not is_invisible
        }
        
    async def _get_catalyst_info(self, record_hash: int, record_data: Dict, record_definition: Dict, objective_definitions_map: Dict[int, Dict]) -> Optional[Dict]:
        """Get detailed information about a catalyst record.
        Accepts pre-fetched record_definition and a map of all relevant objective_definitions.
        """
        if self.cancel_event.is_set():
            return None
        
        try:
            # record_def is now passed in as record_definition
            if not record_definition:
                logger.debug(f"No record definition provided for hash {record_hash}")
                return None
            
            # Get basic info
            display_props = record_definition.get('displayProperties', {})
            name = display_props.get('name', 'Unknown')
            description = display_props.get('description', '')
            icon = display_props.get('icon', '')
            
            logger.debug(f"Processing record: {name} (Hash: {record_hash})")
            
            # Get record state from record_data (the live player data for that record)
            state = self._get_record_state(record_data)
            
            # In standard mode, apply stricter filtering
            if not self.discovery_mode:
                # Only show visible and unlocked records in standard mode
                if not state['visible'] or not state['unlocked']:
                    logger.debug(f"[Standard Mode] Skipping invisible/locked record {record_hash}: {name}")
                    return None
                
                # In standard mode, must have "Catalyst" in the name
                if 'Catalyst' not in name:
                    logger.debug(f"[Standard Mode] Skipping non-catalyst record: {name}")
                    return None
            else:
                # In discovery mode, we're more lenient but still need some filters
                if not state['visible'] and not state['unlocked']:
                    logger.debug(f"[Discovery Mode] Skipping invisible and locked record {record_hash}: {name}")
                    return None
                
                # In discovery mode, check more thoroughly
                if not self._is_catalyst_by_content(record_definition) and 'Catalyst' not in name:
                    logger.debug(f"[Discovery Mode] Skipping non-catalyst-like record: {name}")
                    return None
            
            # Get objectives
            objectives = []
            record_objectives = record_data.get('objectives', [])
            
            for obj_data in record_objectives: # obj_data is the live player data for an objective
                if self.cancel_event.is_set():
                    return None
                
                obj_hash = obj_data.get('objectiveHash')
                # obj_def = await self.get_definition('destinyobjectivedefinition', obj_hash) # OLD CALL
                obj_def = objective_definitions_map.get(obj_hash) # NEW: Lookup from pre-fetched map

                if obj_def:
                    progress = obj_data.get('progress', 0)
                    completion = obj_data.get('completionValue', 100) # Use obj_data for live completionValue if available, else fallback to def
                    if 'completionValue' not in obj_data and obj_def.get('completionValue'): # Fallback to definition if not in live data
                        completion = obj_def['completionValue']

                    complete = obj_data.get('complete', False)
                    
                    objectives.append({
                        'description': obj_def.get('progressDescription', 'Unknown Objective'),
                        'progress': progress,
                        'completion': completion,
                        'complete': complete
                    })
                else:
                    logger.warning(f"Could not find pre-fetched objective definition for hash {obj_hash} for catalyst {name}")
            
            # In standard mode, require objectives
            if not objectives and not self.discovery_mode:
                logger.debug(f"[Standard Mode] Skipping record with no objectives: {name}")
                return None
                
            # In discovery mode, include even without objectives but mark it
            if not objectives and self.discovery_mode:
                logger.debug(f"[Discovery Mode] Record has no objectives: {name}. Adding anyway for review.")
                objectives.append({
                    'description': 'No objectives found - possible catalyst parent record',
                    'progress': 0,
                    'completion': 1,
                    'complete': False
                })
            
            logger.debug(f"Found valid catalyst record: {name} (Complete: {state['complete']}, Unlocked: {state['unlocked']}, Discovery: {self.discovery_mode})")
            if objectives:
                logger.debug(f"Objectives: {objectives}")
            
            # Determine weapon type - this is a new addition
            weapon_type = "Exotic"  # Default type
            
            # Could be enhanced to actually parse the weapon type from the catalyst or record name
            if "Pistol" in name or "Hand Cannon" in name:
                weapon_type = "Hand Cannon"
            elif "Rifle" in name or "Scout" in name:
                weapon_type = "Rifle"
            elif "Shotgun" in name:
                weapon_type = "Shotgun"
            elif "Sword" in name or "Blade" in name:
                weapon_type = "Sword"
            elif "Bow" in name:
                weapon_type = "Bow"
            elif "Launcher" in name:
                weapon_type = "Launcher"
            
            # Calculate overall progress
            total_progress = sum(obj['progress'] for obj in objectives)
            total_completion = sum(obj['completion'] for obj in objectives)
            overall_progress = (total_progress / total_completion * 100) if total_completion > 0 else (100.0 if state['complete'] else 0.0)
            
            return {
                'name': name,
                'description': description,
                'objectives': objectives,
                'complete': state['complete'],
                'record_hash': str(record_hash),
                'weapon_type': weapon_type,
                'progress': overall_progress
            }
        except Exception as e:
            logger.error(f"Error getting catalyst info for record {record_hash}: {e}", exc_info=True)
            return None
    
    def _is_catalyst_by_content(self, record_def):
        # Check if the record definition pertains to a weapon catalyst
        # This might involve looking for specific completion tags or other indicators.
        # Example: DIM checks for specific tags like "weapon.masterwork.catalyst.complete"
        # For now, keeping it simple:
        return "Catalyst" in record_def.get("displayProperties", {}).get("name", "")
            
    async def get_catalyst_status_for_db(self) -> Dict[int, Dict]:
        """Fetches catalyst status suitable for database upsertion.
        Returns a dictionary keyed by catalyst record hash.
        Each value is a dictionary with 'is_complete' and 'objectives' (list of dicts).
        """
        logger.info("Getting catalyst status for DB update.")
        status_map = {}
        membership = await self.get_membership_info()
        if not membership:
            logger.error("Could not retrieve membership info for catalyst status.")
            return status_map

        profile_data = await self.get_profile(int(membership['type']), membership['id'])
        if not profile_data:
            logger.error("Could not retrieve profile data for catalyst status.")
            return status_map

        # profileRecords.data.records is a dict of {recordHash: recordData}
        # characterRecords.data[characterId].records is also a dict of {recordHash: recordData}
        all_player_records_data: Dict[int, Dict] = {}
        if profile_data.get("Response", {}).get("profileRecords", {}).get("data", {}).get("records"):
            for record_hash_str, record_instance_data in profile_data["Response"]["profileRecords"]["data"]["records"].items():
                all_player_records_data[int(record_hash_str)] = record_instance_data
        
        if profile_data.get("Response", {}).get("characterRecords", {}).get("data"):
            for char_id, char_records_component in profile_data["Response"]["characterRecords"]["data"].items():
                if char_records_component.get("records"):
                    for record_hash_str, record_instance_data in char_records_component["records"].items():
                        # Profile records take precedence if a record appears in both (though unlikely for catalysts)
                        if int(record_hash_str) not in all_player_records_data:
                            all_player_records_data[int(record_hash_str)] = record_instance_data

        if not all_player_records_data:
            logger.warning("No records found in profile or character data.")
            return status_map

        # Collect all unique record hashes and objective hashes to fetch their definitions in batches
        all_record_hashes_to_fetch = set(CATALYST_RECORD_HASHES) # Start with known catalyst record hashes
        all_objective_hashes_to_fetch = set()

        for record_hash in CATALYST_RECORD_HASHES:
            player_record_data = all_player_records_data.get(record_hash)
            if player_record_data and player_record_data.get('objectives'):
                for obj_data in player_record_data['objectives']:
                    if obj_data.get('objectiveHash'):
                        all_objective_hashes_to_fetch.add(obj_data['objectiveHash'])
        
        logger.info(f"DB Update: Batch fetching {len(all_record_hashes_to_fetch)} DestinyRecordDefinitions.")
        record_definitions_map = await asyncio.to_thread(
            self.manifest_service.get_definitions_batch,
            'DestinyRecordDefinition',
            list(all_record_hashes_to_fetch)
        )

        logger.info(f"DB Update: Batch fetching {len(all_objective_hashes_to_fetch)} DestinyObjectiveDefinitions.")
        objective_definitions_map = await asyncio.to_thread(
            self.manifest_service.get_definitions_batch,
            'DestinyObjectiveDefinition',
            list(all_objective_hashes_to_fetch)
        )

        if not record_definitions_map:
            logger.warning("Failed to fetch any DestinyRecordDefinitions for catalysts.")
            # No point continuing if we don't have record definitions
            return status_map
        # It's okay if objective_definitions_map is empty if no objectives were found

        for record_hash in CATALYST_RECORD_HASHES:
            player_record_data = all_player_records_data.get(record_hash)
            record_def = record_definitions_map.get(record_hash)

            if not player_record_data or not record_def:
                # logger.debug(f"Skipping catalyst {record_hash}: No player data or definition found.")
                continue

            record_state = self._get_record_state(player_record_data)
            is_complete = record_state.get('complete', False)
            
            current_objectives_for_db = []
            if player_record_data.get('objectives'):
                for obj_data in player_record_data['objectives']:
                    obj_hash = obj_data.get('objectiveHash')
                    # obj_def = objective_definitions_map.get(obj_hash) # Not needed for DB schema
                    current_objectives_for_db.append({
                        "objectiveHash": obj_hash,
                        "progress": obj_data.get('progress', 0),
                        "completionValue": obj_data.get('completionValue', 1), # Default to 1 to avoid div by zero
                        "complete": obj_data.get('complete', False)
                    })
            
            status_map[record_hash] = {
                'is_complete': is_complete,
                'objectives': current_objectives_for_db
            }
            # logger.debug(f"Processed catalyst for DB: {record_hash}, Complete: {is_complete}, Objs: {len(current_objectives_for_db)}")
        
        logger.info(f"Finished processing catalyst statuses for DB. Found {len(status_map)} relevant catalysts.")
        return status_map

    async def get_catalysts(self) -> List[Dict]:
        """Main function to get detailed catalyst information for the agent."""
        start_total_time = time.time()
        logger.info("Starting get_catalysts process...")

        membership_info = await self.get_membership_info()
        if not membership_info:
            return [{"error": "Failed to get user membership info."}]

        profile_data = await self.get_profile(membership_info['type'], membership_info['id'])
        if not profile_data or 'profileRecords' not in profile_data['Response']:
            logger.error("No profile records found in GetProfile response")
            return [{"error": "Failed to retrieve profile records."}]
        
        profile_records_data = profile_data['Response']['profileRecords']['data']['records']
        catalysts = []

        # --- Step 1: Identify relevant record hashes and their objective hashes ---
        record_hashes_to_process = set()
        all_objective_hashes = set()

        logger.info(f"Processing all {len(profile_records_data)} profile records (Discovery: {self.discovery_mode}).")
        for record_hash_str, live_record_data in profile_records_data.items():
            if self.cancel_event.is_set(): break
            try:
                record_hash = int(record_hash_str)
                is_potential_catalyst = False
                if self.discovery_mode:
                    is_potential_catalyst = True # In discovery, consider all for initial def fetch
                elif record_hash in CATALYST_RECORD_HASHES:
                    is_potential_catalyst = True
                
                if is_potential_catalyst:
                    record_hashes_to_process.add(record_hash)
                    for obj_data in live_record_data.get('objectives', []):
                        if obj_hash := obj_data.get('objectiveHash'):
                            all_objective_hashes.add(obj_hash)
            except ValueError:
                logger.debug(f"Skipping non-integer record hash key: {record_hash_str}")
                continue
        
        if self.cancel_event.is_set():
            logger.info("get_catalysts operation cancelled during hash collection.")
            return [{"error": "Operation cancelled."}]

        logger.info(f"Identified {len(record_hashes_to_process)} potential catalyst records and {len(all_objective_hashes)} unique objective hashes.")

        # --- Step 2: Batch fetch all required definitions ---
        t_def_fetch_start = time.time()
        record_definitions_map: Dict[int, Dict[str, Any]] = {}
        objective_definitions_map: Dict[int, Dict[str, Any]] = {}

        if record_hashes_to_process:
            logger.info(f"Batch fetching {len(record_hashes_to_process)} DestinyRecordDefinitions.")
            record_definitions_map = await self.manifest_service.get_definitions_batch(
                "DestinyRecordDefinition", list(record_hashes_to_process)
            )
            logger.info(f"Fetched {len(record_definitions_map)} record definitions.")
        
        if all_objective_hashes:
            logger.info(f"Batch fetching {len(all_objective_hashes)} DestinyObjectiveDefinitions.")
            objective_definitions_map = await self.manifest_service.get_definitions_batch(
                "DestinyObjectiveDefinition", list(all_objective_hashes)
            )
            logger.info(f"Fetched {len(objective_definitions_map)} objective definitions.")
        
        t_def_fetch_end = time.time()
        logger.info(f"Batch definition fetching took {t_def_fetch_end - t_def_fetch_start:.2f} seconds.")

        if self.cancel_event.is_set():
            logger.info("get_catalysts operation cancelled after definition fetching.")
            return [{"error": "Operation cancelled."}]

        # --- Step 3: Process each identified record ---
        logger.info(f"Processing {len(record_hashes_to_process)} potential catalyst records with fetched definitions.")
        t_processing_start = time.time()
        for record_hash in record_hashes_to_process:
            if self.cancel_event.is_set(): break

            live_player_record_data = profile_records_data.get(str(record_hash))
            record_def_from_map = record_definitions_map.get(record_hash)

            if not live_player_record_data:
                logger.debug(f"No live player data for record hash {record_hash}. Skipping.")
                continue
            if not record_def_from_map:
                # This can happen in discovery mode if a record doesn't have a def, or if a known hash is missing a def.
                logger.debug(f"No record definition found in map for hash {record_hash}. Skipping further processing for this record.")
                continue

            # Filter based on CATALYST_RECORD_HASHES if not in discovery mode *after* fetching def
            if not self.discovery_mode and record_hash not in CATALYST_RECORD_HASHES:
                logger.debug(f"[Standard Mode] Record hash {record_hash} not in known CATALYST_RECORD_HASHES. Skipping post-def-fetch.")
                continue

            catalyst_detail = await self._get_catalyst_info(
                record_hash, 
                live_player_record_data, 
                record_def_from_map, # Pass the specific record def
                objective_definitions_map # Pass the whole map of objective defs
            )
            if catalyst_detail:
                # Add the record_hash to the returned catalyst_detail for Supabase upsert in agent_service
                catalyst_detail['record_hash'] = str(record_hash) # Ensure it's a string if needed, or keep as int
                catalysts.append(catalyst_detail)
        
        t_processing_end = time.time()
        logger.info(f"Detailed catalyst processing took {t_processing_end - t_processing_start:.2f} seconds.")
        
        if self.cancel_event.is_set():
            logger.info("get_catalysts operation cancelled during final processing.")
            return [{"error": "Operation cancelled."}]

        logger.info(f"Total get_catalysts execution time: {time.time() - start_total_time:.2f} seconds. Found {len(catalysts)} catalysts.")
        return catalysts
        
    def cancel_operations(self):
        """Signal any ongoing operations to cancel."""
        self.cancel_event.set() 