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
from bungie_oauth import OAuthManager

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
    def __init__(self, oauth_manager: OAuthManager):
        """Initialize the Catalyst API with an OAuthManager instance"""
        self.base_url = "https://www.bungie.net/Platform"
        self.oauth_manager = oauth_manager
        self.session = self._create_session()
        self.definition_cache = {}  # Cache for definitions
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
        
    def get_membership_info(self) -> Optional[Dict[str, str]]:
        """Get the current user's membership info"""
        if self.cancel_event.is_set():
            return None
            
        try:
            url = f"{self.base_url}/User/GetMembershipsForCurrentUser/"
            logger.info(f"Fetching membership from: {url}")
            headers = self.oauth_manager.get_headers()
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
            
    def get_profile(self, membership_type: int, membership_id: str) -> Optional[Dict]:
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
            
            headers = self.oauth_manager.get_headers()
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
        """Get a definition from the Destiny 2 manifest with caching"""
        if self.cancel_event.is_set():
            return None
            
        # Check cache first
        cache_key = f"{table}_{hash_id}"
        if cache_key in self.definition_cache:
            return self.definition_cache[cache_key]
            
        try:
            url = f"{self.base_url}/Destiny2/Manifest/{table}/{hash_id}/"
            headers = self.oauth_manager.get_headers()
            response = self.session.get(url, headers=headers, timeout=10)
            if response.status_code != 200:
                logger.debug(f"Failed to get definition for {table} {hash_id}: {response.status_code}")
                return None
            definition = response.json()['Response']
            self.definition_cache[cache_key] = definition
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
            
            return {
                'name': name,
                'description': description,
                'icon': icon,
                'objectives': objectives,
                'complete': state['complete'],
                'unlocked': state['unlocked'],
                'recordHash': record_hash,
                'discovered': self.discovery_mode and record_hash not in CATALYST_RECORD_HASHES
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
            
    def get_catalysts(self) -> List[Dict]:
        """Get all catalysts and their completion status"""
        self.cancel_event.clear()
        start_time = time.time()
        catalysts = []
        found_hashes = set()
        
        # Get membership info
        logger.info("Getting membership info...")
        membership = self.get_membership_info()
        if not membership:
            logger.error("Failed to get membership info")
            return []
            
        logger.info(f"Found membership: Type={membership['type']}, ID={membership['id']}")
            
        # Get profile data
        logger.info("Getting profile data...")
        profile = self.get_profile(membership['type'], membership['id'])
        if not profile or 'Response' not in profile:
            logger.error("Failed to get profile data")
            return []
            
        # Get all relevant data
        profile_records = profile['Response'].get('profileRecords', {}).get('data', {}).get('records', {})
        character_records = profile['Response'].get('characterRecords', {}).get('data', {})
        
        logger.info(f"Found {len(profile_records)} profile records")
        logger.info(f"Found {len(character_records)} character records")
        
        # In discovery mode, first log potential missing catalysts
        if self.discovery_mode:
            logger.info("Running in discovery mode - searching for potential catalysts")
            discovered_count = 0
            
            for record_hash_str, record in profile_records.items():
                record_hash = int(record_hash_str)
                if record_hash not in CATALYST_RECORD_HASHES:
                    record_def = self.get_definition('DestinyRecordDefinition', record_hash)
                    if record_def:
                        name = record_def.get('displayProperties', {}).get('name', '')
                        if 'Catalyst' in name or self._is_catalyst_by_content(record_def):
                            discovered_count += 1
                            logger.info(f"Discovered potential catalyst: {name} (Hash: {record_hash})")
            
            logger.info(f"Discovered {discovered_count} potential new catalysts")
        
        # First process known catalyst hashes (always do this)
        logger.info(f"Processing {len(CATALYST_RECORD_HASHES)} known catalyst record hashes")
        
        for record_hash in CATALYST_RECORD_HASHES:
            if self.cancel_event.is_set():
                break
                
            try:
                # Check profile records first
                record = profile_records.get(str(record_hash))
                record_found = bool(record)
                
                # If not in profile records, check character records
                if not record:
                    for char_id, char_records in character_records.items():
                        if char_record := char_records.get('records', {}).get(str(record_hash)):
                            record = char_record
                            logger.info(f"Found catalyst {record_hash} in character {char_id}")
                            record_found = True
                            break
                
                if record_found:
                    catalyst_info = self._get_catalyst_info(record_hash, record)
                    if catalyst_info:
                        catalysts.append(catalyst_info)
                        found_hashes.add(record_hash)
                        logger.info(f"Added known catalyst: {catalyst_info['name']} (Complete: {catalyst_info['complete']}, Unlocked: {catalyst_info['unlocked']})")
                    else:
                        logger.debug(f"Skipped known catalyst record {record_hash} - not visible/unlocked or no objectives")
                else:
                    logger.debug(f"No record found for known catalyst hash {record_hash}")
                            
            except Exception as e:
                logger.error(f"Error processing known catalyst {record_hash}: {e}", exc_info=True)
                continue
                
            # Log progress occasionally
            if len(catalysts) % 10 == 0:
                progress = (len(found_hashes) / len(CATALYST_RECORD_HASHES)) * 100
                elapsed = time.time() - start_time
                logger.info(f"Progress: {progress:.1f}% ({len(catalysts)} catalysts found) in {elapsed:.1f}s")
        
        # In discovery mode, also check for additional catalysts
        if self.discovery_mode:
            logger.info("Searching for additional potential catalysts...")
            
            discovered_catalysts = []
            for record_hash_str, record in profile_records.items():
                if self.cancel_event.is_set():
                    break
                    
                record_hash = int(record_hash_str)
                if record_hash in found_hashes:
                    continue  # Skip already processed catalysts
                    
                try:
                    record_def = self.get_definition('DestinyRecordDefinition', record_hash)
                    if record_def:
                        name = record_def.get('displayProperties', {}).get('name', '')
                        # Use more precise detection in discovery mode
                        is_catalyst = 'Catalyst' in name or self._is_catalyst_by_content(record_def)
                        
                        if is_catalyst:
                            catalyst_info = self._get_catalyst_info(record_hash, record)
                            if catalyst_info:
                                discovered_catalysts.append(catalyst_info)
                                logger.info(f"Added discovered catalyst: {catalyst_info['name']} (Hash: {record_hash})")
                except Exception as e:
                    logger.error(f"Error processing discovered catalyst {record_hash}: {e}")
                    continue
            
            # Add discovered catalysts to the main list
            catalysts.extend(discovered_catalysts)
            logger.info(f"Added {len(discovered_catalysts)} discovered catalysts")
        
        elapsed = time.time() - start_time
        logger.info(f"Completed catalyst fetch in {elapsed:.1f} seconds")
        logger.info(f"Found {len(catalysts)} total catalysts")
        
        return catalysts 