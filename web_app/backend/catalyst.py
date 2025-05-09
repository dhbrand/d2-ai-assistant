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
        
    def _get_authenticated_headers(self, access_token: str) -> Dict[str, str]:
        """Gets the necessary headers for authenticated Bungie API requests."""
        if not access_token:
            raise ValueError("Access token is required for authenticated headers")
        return {
            "Authorization": f"Bearer {access_token}",
            "X-API-Key": self.oauth_manager.api_key
        }
        
    async def get_membership_info(self, access_token: str) -> Optional[Dict[str, str]]:
        """Get the current user's membership info"""
        if self.cancel_event.is_set():
            return None
            
        try:
            url = f"{self.base_url}/User/GetMembershipsForCurrentUser/"
            logger.info(f"Fetching membership from: {url}")
            headers = self._get_authenticated_headers(access_token)
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
            
    async def get_profile(self, access_token: str, membership_type: int, membership_id: str) -> Optional[Dict]:
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
            
            headers = self._get_authenticated_headers(access_token)
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
            
    async def get_definition(self, table: str, hash_id: int) -> Optional[Dict]:
        """Get a definition from Supabase Manifest Service."""
        if self.cancel_event.is_set():
            return None
        return await self.manifest_service.get_definition(table, hash_id)
        
    async def _prefetch_definitions(self, profile_records: Dict) -> None:
        """Pre-fetch all needed definitions"""
        logger.info("Pre-fetching definitions...")
        start_time = time.time()
        for record_hash_str in profile_records.keys():
            if self.cancel_event.is_set(): return
            try:
                record_hash = int(record_hash_str)
                if self.discovery_mode or record_hash in CATALYST_RECORD_HASHES:
                    await self.get_definition('destinyrecorddefinition', record_hash)
                    record_data = profile_records.get(str(record_hash))
                    if record_data:
                        for obj in record_data.get('objectives', []):
                            if self.cancel_event.is_set(): return
                            if obj_hash := obj.get('objectiveHash'):
                                await self.get_definition('destinyobjectivedefinition', obj_hash)
            except ValueError:
                logger.debug(f"Skipping non-integer record key: {record_hash_str} during prefetch.")
                continue
        elapsed = time.time() - start_time
        logger.info(f"Pre-fetched definitions in {elapsed:.1f} seconds")
        
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
        
    async def _get_catalyst_info(self, record_hash, record):
        """Get detailed information about a catalyst record using DIM's approach."""
        if self.cancel_event.is_set():
            return None
        
        try:
            record_def = await self.get_definition('destinyrecorddefinition', record_hash)
            if not record_def:
                logger.debug(f"No record definition found for hash {record_hash}")
                return None
            
            # Get basic info
            display_props = record_def.get('displayProperties', {})
            name = display_props.get('name', 'Unknown')
            description = display_props.get('description', '')
            icon = display_props.get('icon', '')
            
            logger.debug(f"Processing record: {name} (Hash: {record_hash})")
            
            # Get record state
            state = self._get_record_state(record)
            
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
                if not self._is_catalyst_by_content(record_def) and 'Catalyst' not in name:
                    logger.debug(f"[Discovery Mode] Skipping non-catalyst-like record: {name}")
                    return None
            
            # Get objectives
            objectives = []
            record_objectives = record.get('objectives', [])
            
            for obj in record_objectives:
                if self.cancel_event.is_set():
                    return None
                
                obj_hash = obj.get('objectiveHash')
                obj_def = await self.get_definition('destinyobjectivedefinition', obj_hash)
                if obj_def:
                    progress = obj.get('progress', 0)
                    completion = obj.get('completionValue', 100)
                    complete = obj.get('complete', False)
                    
                    objectives.append({
                        'description': obj_def.get('progressDescription', 'Unknown'),
                        'progress': progress,
                        'completion': completion,
                        'complete': complete
                    })
            
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
        """Check if a record is a catalyst based on its content not just name"""
        if not record_def: return False
        name = record_def.get('displayProperties', {}).get('name', '').lower()
        if 'catalyst' in name: return True
        # Add more checks based on record_def content if needed
        # e.g., lore hash, specific objective types, etc.
        return False
            
    async def get_catalyst_status_for_db(self, access_token: str) -> Dict[int, Dict]:
        """
        Fetches catalyst status directly from profile records suitable for DB storage.
        Returns a dictionary mapping catalyst recordHash to its status.
        { recordHash: { "is_complete": bool, "objectives": { objectiveHash: progress, ... } } }
        """
        logger.info("Fetching catalyst status for database storage...")
        status_map = {}

        membership_info = await self.get_membership_info(access_token)
        if not membership_info:
            logger.error("Failed to get membership info for DB catalyst sync.")
            return status_map

        profile_data = await self.get_profile(access_token, membership_info['type'], membership_info['id'])
        if not profile_data or 'profileRecords' not in profile_data.get('Response', {}):
            logger.error("Failed to get profile records for DB catalyst sync.")
            return status_map

        profile_records_data = profile_data['Response']['profileRecords']['data']['records']
        
        for record_hash_str, record_data in profile_records_data.items():
            if self.cancel_event.is_set(): break
            try:
                record_hash = int(record_hash_str)
                is_known_catalyst = record_hash in CATALYST_RECORD_HASHES
                
                record_def_for_check = await self.get_definition('destinyrecorddefinition', record_hash)
                if not record_def_for_check:
                    continue

                is_catalyst_by_name = 'catalyst' in record_def_for_check.get('displayProperties', {}).get('name', '').lower()

                if not (is_known_catalyst or is_catalyst_by_name):
                    continue

                state_info = self._get_record_state(record_data)
                objectives_for_db = {}
                for obj_data in record_data.get('objectives', []):
                    obj_hash = obj_data.get('objectiveHash')
                    if obj_hash:
                        objectives_for_db[obj_hash] = obj_data.get('progress', 0)
                
                status_map[record_hash] = {
                    "is_complete": state_info['complete'],
                    "objectives": objectives_for_db
                }
            except ValueError:
                logger.debug(f"Skipping non-integer record key {record_hash_str} in get_catalyst_status_for_db")
                continue
            except Exception as e:
                logger.error(f"Error processing record {record_hash_str} for DB status: {e}", exc_info=True)

        logger.info(f"Prepared catalyst status for DB: {len(status_map)} items.")
        return status_map

    async def get_catalysts(self, access_token: str) -> List[Dict]:
        """Get all catalyst information for the user."""
        if self.cancel_event.is_set():
            return []
            
        logger.info("Starting catalyst retrieval process...")
        start_time = time.time()
        
        membership_info = await self.get_membership_info(access_token)
        if not membership_info:
            return []
            
        profile_data = await self.get_profile(access_token, membership_info['type'], membership_info['id'])
        if not profile_data or 'profileRecords' not in profile_data.get('Response', {}):
            logger.error("Profile records not found in API response.")
            return []
            
        records = profile_data['Response']['profileRecords']['data']['records']
        logger.info(f"Retrieved {len(records)} records from profile.")
        
        await self._prefetch_definitions(records)
        
        catalysts = []
        processed_hashes = set()
        
        if not self.discovery_mode:
            logger.info(f"Standard mode: Processing {len(CATALYST_RECORD_HASHES)} known catalyst hashes.")
            for record_hash in CATALYST_RECORD_HASHES:
                if self.cancel_event.is_set(): break
                record = records.get(str(record_hash))
                if record:
                    info = await self._get_catalyst_info(record_hash, record)
                    if info:
                        catalysts.append(info)
                    processed_hashes.add(record_hash)
                else:
                    logger.debug(f"Known catalyst hash {record_hash} not found in user's profile records.")
        
        logger.info(f"Processing all {len(records)} profile records (Discovery: {self.discovery_mode}).")
        for record_hash_str, record in records.items():
            if self.cancel_event.is_set(): break
            try:
                record_hash = int(record_hash_str)
                if record_hash in processed_hashes:
                    continue
                
                info = await self._get_catalyst_info(record_hash, record)
                if info:
                    catalysts.append(info)
                    processed_hashes.add(record_hash)
            except ValueError:
                logger.debug(f"Skipping non-integer record key: {record_hash_str}")
                continue
            except Exception as e:
                logger.error(f"Error processing record {record_hash_str} in get_catalysts: {e}", exc_info=True)

        elapsed = time.time() - start_time
        logger.info(f"Retrieved {len(catalysts)} catalysts in {elapsed:.1f} seconds")
        return catalysts
        
    def cancel_operations(self):
        """Signal any ongoing operations to cancel."""
        self.cancel_event.set() 