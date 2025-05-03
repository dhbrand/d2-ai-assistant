import os
import json
import logging
from typing import List, Dict, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import requests
import time
from threading import Event
from catalyst_hashes import CATALYST_RECORD_HASHES
import hashlib
import pathlib

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
    def __init__(self, api_key: str):
        """Initialize the Catalyst API"""
        self.base_url = "https://www.bungie.net/Platform"
        self.api_key = api_key
        self.session = self._create_session()
        self.definition_cache = {}  # Memory cache for definitions
        self.cache_dir = pathlib.Path("definition_cache")  # Directory for persistent cache
        self.cache_dir.mkdir(exist_ok=True)  # Create cache directory if it doesn't exist
        self.cancel_event = Event()  # For cancelling operations
        self.discovery_mode = False  # Default to standard mode (known catalysts only)
        
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
            "X-API-Key": self.api_key
        }
        
    def get_membership_info(self, access_token: str) -> Optional[Dict[str, str]]:
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
            
    def get_profile(self, access_token: str, membership_type: int, membership_id: str) -> Optional[Dict]:
        """Get the user's profile with records"""
        if self.cancel_event.is_set():
            return None
            
        try:
            url = f"{self.base_url}/Destiny2/{membership_type}/Profile/{membership_id}/"
            
            # Request all relevant components for triumphs and records
            components = [
                "100",  # Profile info
                "102",  # Profile inventory
                "200",  # Characters
                "201",  # Character inventories 
                "202",  # Character progressions
                "800",  # Profile collectibles
                "900"   # Profile records
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
            
    def get_definition(self, table: str, hash_id: int) -> Optional[Dict]:
        """Get a definition from the Destiny 2 manifest (No auth required)"""
        if self.cancel_event.is_set():
            return None
            
        # Check memory cache first
        cache_key = f"{table}_{hash_id}"
        if cache_key in self.definition_cache:
            return self.definition_cache[cache_key]
        
        # Check disk cache
        cache_file = self.cache_dir / f"{cache_key}.json"
        if cache_file.exists():
            try:
                with open(cache_file, 'r') as f:
                    definition = json.load(f)
                # Store in memory cache too
                self.definition_cache[cache_key] = definition
                return definition
            except Exception as e:
                logger.debug(f"Error reading cache file {cache_file}: {e}")
                # Continue to fetch from API if cache read fails
            
        # Fetch from API if not in cache
        try:
            url = f"{self.base_url}/Destiny2/Manifest/{table}/{hash_id}/"
            headers = {"X-API-Key": self.api_key}
            response = self.session.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                logger.debug(f"Failed to get definition for {table} {hash_id}: {response.status_code}")
                return None
            definition = response.json()['Response']
            
            # Store in memory cache
            self.definition_cache[cache_key] = definition
            
            # Store on disk
            try:
                with open(cache_file, 'w') as f:
                    json.dump(definition, f)
            except Exception as e:
                logger.debug(f"Error writing to cache file {cache_file}: {e}")
                # Continue even if we can't write to cache
                
            return definition
        except Exception as e:
            logger.debug(f"Error getting definition for {table} {hash_id}: {e}")
            return None
            
    def _prefetch_definitions(self, profile_records: Dict) -> None:
        """Pre-fetch all needed definitions"""
        logger.info("Pre-fetching definitions...")
        start_time = time.time()
        
        # First, get all record definitions
        for record_hash in CATALYST_RECORD_HASHES:
            if self.cancel_event.is_set():
                return
                
            if str(record_hash) in profile_records:
                self.get_definition('DestinyRecordDefinition', record_hash)
                
        # Then get objective definitions
        for record_hash in CATALYST_RECORD_HASHES:
            if self.cancel_event.is_set():
                return
                
            record = profile_records.get(str(record_hash))
            if record:
                for obj in record.get('objectives', []):
                    if obj_hash := obj.get('objectiveHash'):
                        self.get_definition('DestinyObjectiveDefinition', obj_hash)
                        
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
        
    def _get_catalyst_info(self, record_hash, record):
        """Get detailed information about a catalyst record using DIM's approach."""
        if self.cancel_event.is_set():
            return None
        
        try:
            record_def = self.get_definition('DestinyRecordDefinition', record_hash)
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
                obj_def = self.get_definition('DestinyObjectiveDefinition', obj_hash)
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
            
            return {
                'name': name,
                'description': description,
                'icon': icon,
                'objectives': objectives,
                'complete': state['complete'],
                'unlocked': state['unlocked'],
                'recordHash': record_hash,
                'discovered': self.discovery_mode and record_hash not in CATALYST_RECORD_HASHES,
                'weaponType': weapon_type  # Add weaponType to the return value
            }
        except Exception as e:
            logger.error(f"Error getting catalyst info for record {record_hash}: {e}")
            return None
    
    def _is_catalyst_by_content(self, record_def):
        """Check if a record is a catalyst based on its content not just name"""
        try:
            # Skip category records (these often have "Exotic Weapons" in description)
            if record_def.get('recordValueStyle', 0) == 1:  # This indicates a category/parent record
                return False

            # Skip parent records that contain many children
            if 'parentNodeHashes' in record_def or 'children' in record_def:
                children_count = len(record_def.get('children', {}).get('records', []))
                if children_count > 3:  # If it has multiple children, it's likely a category
                    return False

            # Check for actual catalyst evidence in description
            description = record_def.get('displayProperties', {}).get('description', '').lower()
            
            # Look for specific catalyst phrases (more precise than general terms)
            catalyst_phrases = [
                'weapon catalyst', 
                'catalyst for', 
                'masterwork the', 
                'exotic catalyst', 
                'catalyst objectives'
            ]
            
            if any(phrase in description for phrase in catalyst_phrases):
                return True
                
            # Check objectives descriptions for catalyst-specific language
            if 'objectiveHashes' in record_def:
                for obj_hash in record_def['objectiveHashes']:
                    obj_def = self.get_definition('DestinyObjectiveDefinition', obj_hash)
                    if obj_def:
                        desc = obj_def.get('progressDescription', '').lower()
                        if any(phrase in desc for phrase in ['catalyst', 'masterwork']):
                            if 'defeat' in desc or 'kills' in desc or 'precision' in desc:
                                return True  # Common catalyst objectives involve defeating enemies
            
            return False
        except Exception as e:
            logger.error(f"Error in _is_catalyst_by_content: {e}")
            return False
            
    def get_catalysts(self, access_token: str) -> List[Dict]:
        """Get all known catalyst records for the user."""
        logger.info("Starting catalyst fetch process...")
        start_total = time.time()
        
        if self.cancel_event.is_set():
            return []
            
        # 1. Get Membership Info
        start_time = time.time()
        membership = self.get_membership_info(access_token)
        if not membership:
            logger.error("Failed to get membership info.")
            return []
        elapsed = time.time() - start_time
        logger.info(f"Got membership in {elapsed:.1f} seconds")
        
        if self.cancel_event.is_set():
            return []
        
        # 2. Get Profile Data
        start_time = time.time()
        profile_data = self.get_profile(access_token, membership['type'], membership['id'])
        if not profile_data:
            logger.error("Failed to get profile data.")
            return []
        elapsed = time.time() - start_time
        logger.info(f"Got profile in {elapsed:.1f} seconds")
        
        profile_records = profile_data.get('Response', {}).get('profileRecords', {}).get('data', {}).get('records', {})
        self._prefetch_definitions(profile_records)

        catalysts = []
        for record_hash in CATALYST_RECORD_HASHES:
            if self.cancel_event.is_set():
                return []

            record = profile_records.get(str(record_hash))
            if record:
                catalyst_info = self._get_catalyst_info(record_hash, record)
                if catalyst_info:
                    catalysts.append(catalyst_info)

        return catalysts 