import requests
import logging
import asyncio # Added for asyncio.to_thread
from typing import List, Dict, Any, Optional # Added Optional for type hinting
from requests.adapters import HTTPAdapter # Added import
from urllib3.util.retry import Retry # Added import

from .manifest import SupabaseManifestService # Import the new service
from .bungie_oauth import OAuthManager # Import OAuthManager
import time

logger = logging.getLogger(__name__)

# Mapping from Bungie API itemType enum
ITEM_TYPE_WEAPON = 3
# Mapping from Bungie API damageType enum
DAMAGE_TYPE_MAP = {
    0: "None",
    1: "Kinetic",
    2: "Arc",
    3: "Solar",
    4: "Void",
    5: "Raid", # Deprecated?
    6: "Stasis",
    7: "Strand"
}

# Define PCI sets for _get_plug_category at class or module level if preferred,
# or directly within the method as it's self-contained.
# For clarity here, we can define them before the class or as class attributes.
_PCI_COL1 = {"barrels", "tubes", "bowstrings", "blades", "hafts", "scopes"}
_PCI_COL2 = {"magazines", "batteries", "guards", "arrows"}
_TRAIT_PCI = {"grips", "traits"}
_ORIGIN_PCI = {"origin"}
_FRAME_PCI = {"frames"} # New set for frame identification for intrinsics

class WeaponAPI:
    def __init__(self, oauth_manager: OAuthManager, manifest_service: SupabaseManifestService):
        self.oauth_manager = oauth_manager # Store OAuthManager
        self.base_url = "https://www.bungie.net/Platform"
        self.manifest_service = manifest_service # Store SupabaseManifestService
        self.session = self._create_session() # Keep synchronous session for now

    def _create_session(self) -> requests.Session: # Stays synchronous
        session = requests.Session()
        retry = Retry(
            total=3,  # Total number of retries
            backoff_factor=1,  # A delay factor to apply between attempts
            status_forcelist=[500, 502, 503, 504],  # HTTP status codes to retry on
            allowed_methods=["HEAD", "GET", "OPTIONS"] # Set of uppercased HTTP method verbs that we should retry on.
        )
        adapter = HTTPAdapter(max_retries=retry)
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        return session

    def _get_headers(self) -> Dict[str, str]: # Modified to match CatalystAPI's _get_authenticated_headers
        """Gets the necessary headers for authenticated Bungie API requests."""
        return self.oauth_manager.get_headers()

    def _fetch_membership_info_sync(self) -> Optional[Dict[str, str]]:
        """Synchronous helper to fetch and process membership info."""
        headers = self._get_headers()
        url = f"{self.base_url}/User/GetMembershipsForCurrentUser/"
        try:
            # Using a timeout similar to CatalystAPI
            response = self.session.get(url, headers=headers, timeout=8)
            if response.status_code != 200:
                logger.error(f"Failed to get membership info: {response.status_code} - {response.text}")
                return None
                
            data = response.json()
            # Simplified logic to match CatalystAPI
            if 'Response' not in data or not data['Response'].get('destinyMemberships'):
                logger.error("No destiny memberships found in response for WeaponAPI.")
                return None
                
            # Prioritize primaryMembershipId if available, else take the first one.
            # This part is a bit more robust than CatalystAPI's current simple [0] access.
            primary_membership_id = data['Response'].get('primaryMembershipId')
            membership_to_use = None
            
            if primary_membership_id:
                for m in data['Response']['destinyMemberships']:
                    if m['membershipId'] == primary_membership_id:
                        membership_to_use = m
                        break
            
            if not membership_to_use and data['Response']['destinyMemberships']:
                membership_to_use = data['Response']['destinyMemberships'][0]

            if membership_to_use:
                logger.info(f"WeaponAPI found membership - Type: {membership_to_use['membershipType']}, ID: {membership_to_use['membershipId']}")
                return {
                    'type': str(membership_to_use['membershipType']), # Ensure type is string
                    'id': membership_to_use['membershipId']
                    # Removed bungieGlobalDisplayName and Code to match CatalystAPI's typical return for this specific method
                }
            else:
                logger.error("No usable destiny membership found after checking primary and first entry.")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP Error fetching membership info for WeaponAPI: {e}", exc_info=True)
            return None
        except Exception as e: # Catching generic Exception for other issues like JSON parsing
            logger.error(f"Error processing membership info for WeaponAPI: {e}", exc_info=True)
            return None

    async def get_membership_info(self) -> Optional[Dict[str, str]]: # Changed to async
        """Get the current user's membership info, matching CatalystAPI's async pattern."""
        logger.info("WeaponAPI: Fetching membership info...")
        return await asyncio.to_thread(self._fetch_membership_info_sync)
        
    def get_single_item_component(self, membership_type: int, destiny_membership_id: str, item_instance_id: str, components: List[int]) -> dict:
        # This method remains synchronous as it's not directly part of the main failing flow being refactored
        # If it needs to be async, it would follow a similar pattern.
        headers = self._get_headers()
        components_str = ",".join(map(str, components))
        url = (
            f"{self.base_url}/Destiny2/{membership_type}/Profile/"
            f"{destiny_membership_id}/Item/{item_instance_id}/?components={components_str}"
        )
        response = self.session.get(url, headers=headers)
        response.raise_for_status()
        return response.json()

    def _fetch_profile_sync(self, membership_type: int, destiny_membership_id: str, components: List[int]) -> Optional[dict]:
        """Synchronous helper to fetch and process profile data."""
        headers = self._get_headers()
        if not headers: # Should not happen if oauth_manager.get_headers() works
            logger.error("Authentication headers are missing in _fetch_profile_sync (WeaponAPI).")
            return None

        components_str = ",".join(map(str, components))
        url = f"{self.base_url}/Destiny2/{membership_type}/Profile/{destiny_membership_id}/?components={components_str}"
        
        logger.debug(f"WeaponAPI requesting profile components from: {url} with components: {components_str}")

        try:
            # Adding a timeout similar to CatalystAPI's get_profile
            response = self.session.get(url, headers=headers, timeout=15)
            response.raise_for_status()
            data = response.json()
            
            if data.get('ErrorCode') == 1:
                logger.info(f"WeaponAPI successfully fetched profile components for user {destiny_membership_id}.")
                return data
            else:
                error_message = data.get('Message', 'Unknown Bungie API error')
                status = data.get('ErrorStatus', 'Unknown Status')
                logger.error(f"WeaponAPI: Bungie API Error fetching profile components: {error_message} (ErrorCode: {data.get('ErrorCode')}, Status: {status}) for URL: {url}")
                return None
        except requests.exceptions.HTTPError as http_err:
            logger.error(f"WeaponAPI: HTTP error occurred while fetching profile components: {http_err} - URL: {url} - Response: {hasattr(http_err, 'response') and hasattr(http_err.response, 'text') and http_err.response.text}", exc_info=True)
            return None
        except requests.exceptions.RequestException as req_err:
            logger.error(f"WeaponAPI: Request error occurred while fetching profile components: {req_err} - URL: {url}", exc_info=True)
            return None
        except ValueError as json_err: 
            logger.error(f"WeaponAPI: JSON decode error while fetching profile components: {json_err} - URL: {url}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"WeaponAPI: An unexpected error occurred while fetching profile components: {e} - URL: {url}", exc_info=True)
            return None

    async def get_profile(self, membership_type: int, destiny_membership_id: str, components: List[int]) -> Optional[dict]: # Renamed and made async
        """Get the user's profile, matching CatalystAPI's async pattern."""
        logger.info(f"WeaponAPI: Getting profile for {destiny_membership_id}, type {membership_type} with components {components}")
        return await asyncio.to_thread(self._fetch_profile_sync, membership_type, destiny_membership_id, components)

    def _get_plug_category(self, plug_def: Dict[str, Any]) -> str:
        if not plug_def or not isinstance(plug_def, dict):
            return "other"
            
        pci = plug_def.get('plug', {}).get('plugCategoryIdentifier', '').lower()
        name = plug_def.get('displayProperties', {}).get('name', '')
        item_type_display_name = plug_def.get('itemTypeDisplayName', '').lower()

        # Check for intrinsic frames first
        if any(key in pci for key in _FRAME_PCI) or item_type_display_name in ("weapon frame", "intrinsic"): # Adjusted keywords
            return "intrinsic_frame"
        elif any(key in pci for key in _PCI_COL1):
            return "col1_barrel"
        elif any(key in pci for key in _PCI_COL2):
            return "col2_magazine"
        elif any(key in pci for key in _TRAIT_PCI) or \
             plug_def.get('itemTypeDisplayName') in ("Trait", "Enhanced Trait", "Grip"):
            return "trait"
        elif any(key in pci for key in _ORIGIN_PCI) or \
             plug_def.get('itemTypeDisplayName') == "Origin Trait":
            return "origin_trait"
        elif "masterworks.stat." in pci or \
             (pci.startswith("masterwork.") and ".stat." in pci) or \
             (pci.endswith(".masterwork") and ".weapon." in pci) or \
             ('masterworks' in pci and name.startswith('Masterworked:')):
            return "masterwork"
        elif "shader" in pci:
            return "shader"
        elif "weapon.mod_guns" in pci or "weapon mod" in item_type_display_name:
            return "weapon_mod"
        else:
            return "other"

    def _map_item_location_enum_to_string(self, location_enum: Optional[int]) -> str:
        if location_enum is None:
            return "unknown"
        mapping = {
            0: "unknown",
            1: "inventory",  # Character inventory / General
            2: "vault",
            3: "vendor",     # Unlikely for owned items being synced
            4: "postmaster"
        }
        # If an item is equipped, its location might still be 1 (Inventory)
        # The `is_equipped` boolean from item instance data is the definitive source for equipped status.
        return mapping.get(location_enum, "unknown")

    async def get_all_weapons_with_detailed_perks(self, membership_type: str, destiny_membership_id: str) -> List[Dict[str, Any]]:
        logger.info(f"WeaponAPI: Fetching all weapons with detailed perks for {destiny_membership_id} (type: {membership_type})")
        components = [
            102,  # profileInventory
            201,  # characterInventories
            205,  # characterEquipment
            310   # reusablePlugs (for all selectable perks on an item instance)
        ]

        profile_response = None # Initialize to None
        try:
            # Call the new async get_profile method directly
            profile_response = await self.get_profile(
                int(membership_type), # Ensure membership_type is passed as an int
                destiny_membership_id,
                components
            )
        except Exception as e: 
            logger.error(f"WeaponAPI: Error calling get_profile: {e}", exc_info=True)
            return [] 

        if profile_response is None:
            logger.error(f"WeaponAPI: Failed to get profile response from Bungie API for {destiny_membership_id} (profile_response is None).")
            return []

        if profile_response.get("ErrorCode", 1) != 1: 
            error_message = profile_response.get('Message', 'Unknown error or malformed error response')
            logger.error(f"WeaponAPI: Failed to get profile response from Bungie API for {destiny_membership_id}: {error_message}. ErrorCode: {profile_response.get('ErrorCode')}")
            return []

        response_data = profile_response.get("Response", {})
        if not response_data:
            logger.warning(f"Profile response for {destiny_membership_id} was empty or malformed.")
            return []

        character_equipment_data = response_data.get("characterEquipment", {}).get("data", {})
        character_inventories_data = response_data.get("characterInventories", {}).get("data", {})
        profile_inventory_data = response_data.get("profileInventory", {}).get("data", {})
        item_instances_data = response_data.get("itemComponents", {}).get("instances", {}).get("data", {})
        reusable_plugs_data = response_data.get("itemComponents", {}).get("reusablePlugs", {}).get("data", {})

        all_items_from_profile_refs = []
        if character_equipment_data:
            for char_id, equip_data in character_equipment_data.items():
                all_items_from_profile_refs.extend(equip_data.get('items', []))
        if character_inventories_data:
            for char_id, inv_data in character_inventories_data.items():
                all_items_from_profile_refs.extend(inv_data.get('items', []))
        if profile_inventory_data and profile_inventory_data.get("items"):
            all_items_from_profile_refs.extend(profile_inventory_data.get('items', []))
        
        if not all_items_from_profile_refs:
            logger.info(f"No items found in profile for {destiny_membership_id}.")
            return []
        logger.info(f"Found {len(all_items_from_profile_refs)} item references in total from profile for {destiny_membership_id}.")

        instance_socket_plug_hashes = {}
        all_unique_plug_hashes = set()

        for item_ref in all_items_from_profile_refs:
            instance_id = item_ref.get('itemInstanceId')
            if not instance_id:
                continue
            
            # Plugs for this instance are in reusable_plugs_data.data[instance_id].plugs
            # This is a dictionary where keys are socketIndexes (strings)
            # and values are lists of plug objects {'plugItemHash': hash, 'canInsert': bool, ...}
            instance_component_data = reusable_plugs_data.get(instance_id, {})
            instance_sockets_dict = instance_component_data.get('plugs', {}) # dict: {socketIndexStr: [plugObj, ...]}
            
            socket_to_plug_hashes_map = {}
            for socket_index_str, plug_object_list in instance_sockets_dict.items():
                current_socket_plug_hashes = [
                    p.get("plugItemHash") for p in plug_object_list if p and p.get("plugItemHash")
                ]
                if current_socket_plug_hashes:
                    socket_to_plug_hashes_map[int(socket_index_str)] = current_socket_plug_hashes
                    all_unique_plug_hashes.update(current_socket_plug_hashes)
            
            if socket_to_plug_hashes_map:
                instance_socket_plug_hashes[instance_id] = socket_to_plug_hashes_map

        if not all_unique_plug_hashes:
            logger.info("No plug hashes collected from reusable plugs.")
            # This might mean no items with such plugs or issue in data.
        else:
             logger.info(f"WeaponAPI: Collected {len(all_unique_plug_hashes)} unique plug hashes to fetch definitions for.")


        plug_definitions = await asyncio.to_thread(
            self.manifest_service.get_definitions_batch,
            'DestinyInventoryItemDefinition',
            list(all_unique_plug_hashes)
        )
        if not plug_definitions:
            logger.warning("No plug definitions returned from manifest service. Perk names might be missing.")
            plug_definitions = {} # Ensure it's a dict to prevent errors later


        detailed_weapon_list = []
        processed_hashes = set() # To avoid reprocessing if an item appears in multiple lists (e.g. equipped and char inventory)

        for item_ref in all_items_from_profile_refs:
            item_hash = item_ref.get('itemHash')
            instance_id = item_ref.get('itemInstanceId')

            if not instance_id or not item_hash:
                continue
            
            # Avoid reprocessing the same instance if it was listed multiple times (e.g. bug in flattening)
            # However, item_ref itself comes from distinct lists (equip, char inv, profile inv), so this might be redundant.
            # A single item instance should only be in one place.
            # If we are just building a list of weapon data, we want one entry per unique instance_id.
            if instance_id in processed_hashes:
                continue
            processed_hashes.add(instance_id)


            static_def_item = await asyncio.to_thread(
                self.manifest_service.get_definition,
                'DestinyInventoryItemDefinition', 
                item_hash
            )

            if not static_def_item or static_def_item.get('itemType') != 3:  # 3 is DestinyItemType.Weapon
                continue

            item_instance_specifics = item_instances_data.get(instance_id, {})
            location_enum = item_instance_specifics.get('location')
            is_equipped = item_instance_specifics.get('isEquipped', False)
            location_str = self._map_item_location_enum_to_string(location_enum)
            
            current_item_socket_plugs_map = instance_socket_plug_hashes.get(instance_id, {})
            
            socket_plug_defs = {}
            for socket_idx, p_hashes in current_item_socket_plugs_map.items():
                defs = [plug_definitions.get(p_hash) for p_hash in p_hashes if plug_definitions.get(p_hash)]
                if defs: # Only add if there are valid definitions
                    socket_plug_defs[socket_idx] = defs
            
            trait_socket_indexes = sorted([
                idx for idx, p_defs_list in socket_plug_defs.items()
                if any(self._get_plug_category(p_def) == "trait" for p_def in p_defs_list if p_def)
            ])

            col1_plugs, col2_plugs, col3_trait1, col4_trait2 = set(), set(), set(), set()
            origin_trait_plugs, masterwork_plugs, weapon_mod_plugs, shader_plugs = set(), set(), set(), set()
            intrinsic_perk_names = set() # For collecting intrinsic perk names

            for socket_index, plug_defs_list in socket_plug_defs.items():
                for plug_def in plug_defs_list:
                    if not plug_def:
                        continue
                    
                    name = plug_def.get('displayProperties', {}).get('name')
                    if not name: # Skip if plug has no name
                        continue

                    category = self._get_plug_category(plug_def)

                    if category == "intrinsic_frame": intrinsic_perk_names.add(name)
                    elif category == "col1_barrel": col1_plugs.add(name)
                    elif category == "col2_magazine": col2_plugs.add(name)
                    elif category == "trait":
                        # Ensure trait sockets are correctly identified and assigned
                        # This logic assumes trait_socket_indexes are purely based on 'trait' category
                        # Intrinsic frames are now separate and won't be in trait_socket_indexes
                        if trait_socket_indexes and socket_index == trait_socket_indexes[0]:
                            col3_trait1.add(name)
                        elif len(trait_socket_indexes) > 1 and socket_index == trait_socket_indexes[1]:
                            col4_trait2.add(name)
                        # else: # A trait in a socket not matching the first two trait sockets.
                               # Could be assigned to a generic trait list or ignored based on requirements.
                               # For now, unassigned if not in col3 or col4 based on current logic.
                    elif category == "origin_trait": origin_trait_plugs.add(name)
                    elif category == "masterwork": masterwork_plugs.add(name)
                    elif category == "weapon_mod": weapon_mod_plugs.add(name)
                    elif category == "shader": shader_plugs.add(name)
            
            weapon_data = {
                "item_instance_id": instance_id,
                "item_hash": item_hash,
                "weapon_name": static_def_item.get("displayProperties", {}).get("name"),
                "weapon_type": static_def_item.get("itemTypeDisplayName"),
                "intrinsic_perk": sorted(list(intrinsic_perk_names))[0] if intrinsic_perk_names else None,
                "location": location_str,
                "is_equipped": is_equipped,
                "col1_plugs": sorted(list(col1_plugs)),
                "col2_plugs": sorted(list(col2_plugs)),
                "col3_trait1": sorted(list(col3_trait1)),
                "col4_trait2": sorted(list(col4_trait2)),
                "origin_trait": sorted(list(origin_trait_plugs)),
                "masterwork": sorted(list(masterwork_plugs)),
                "weapon_mods": sorted(list(weapon_mod_plugs)),
                "shaders": sorted(list(shader_plugs)),
            }
            detailed_weapon_list.append(weapon_data)

        logger.info(f"Processed {len(detailed_weapon_list)} weapons with detailed perks for {destiny_membership_id}.")
        return detailed_weapon_list

# Example usage (for testing this file directly, if needed)
if __name__ == '__main__':
    # Setup basic logging for testing
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    
    # This is a placeholder for actual OAuth and Manifest setup
    # You would need to replace these with actual initialized instances
    # from dotenv import load_dotenv
    # import os
    # load_dotenv(dotenv_path='../../.env') # Adjust path as necessary

    # class MockOAuthManager:
    #     def get_headers(self):
    #         return {
    #             "X-API-Key": os.getenv("BUNGIE_API_KEY"),
    #             "Authorization": f"Bearer {os.getenv('BUNGIE_ACCESS_TOKEN')}" # You need a valid token
    #         }

    # class MockManifestService:
    #     def get_definition(self, def_type, def_hash):
    #         # Simplified mock
    #         print(f"MockManifestService: Requesting {def_type} for {def_hash}")
    #         return {"displayProperties": {"name": f"Mock Item {def_hash}"}, "itemType": 3} 
        
    #     def get_definitions_batch(self, def_type, def_hashes):
    #         print(f"MockManifestService: Batch requesting {len(def_hashes)} of {def_type}")
    #         return {h: {"displayProperties": {"name": f"Mock Item {h}"}, "itemType": 3} for h in def_hashes}


    # # Replace with your actual membership details
    # test_membership_type = 3 # e.g., 3 for Steam
    # test_destiny_membership_id = "YOUR_MEMBERSHIP_ID_HERE" # "YourDestinyMembershipId"
    # # bungie_api_key = os.getenv("BUNGIE_API_KEY") # Assumed to be handled by MockOAuthManager or real OAuthManager
    # # access_token = os.getenv("BUNGIE_ACCESS_TOKEN") # Needs to be fresh, handled by MockOAuthManager or real OAuthManager

    # # if not all([test_membership_type, test_destiny_membership_id != "YOUR_MEMBERSHIP_ID_HERE"]):
    # #     logger.error("Please set test_membership_type and test_destiny_membership_id in the script for testing.")
    # # else:
    # #     oauth_manager_mock = MockOAuthManager() # Replace with real OAuthManager for actual calls
    # #     manifest_service_mock = MockManifestService() # Replace with real SupabaseManifestService
    # #     weapon_api_instance = WeaponAPI(oauth_manager=oauth_manager_mock, manifest_service=manifest_service_mock)
        
    #     # Test get_profile_response
    #     # logger.info(f"Attempting to get profile response for Type: {test_membership_type}, ID: {test_destiny_membership_id}")
    #     # profile_data = weapon_api_instance.get_profile_response(test_membership_type, test_destiny_membership_id, [102, 201, 205, 300])
    #     # if profile_data and profile_data.get("Response"):
    #     #     logger.info("Successfully got profile response.")
    #     #     # Example: Print number of items in vault
    #     #     vault_items = profile_data.get("Response", {}).get("profileInventory", {}).get("data", {}).get("items", [])
    #     #     logger.info(f"Number of items in vault: {len(vault_items)}")
    #     #     if vault_items:
    #     #          logger.info(f"First vault item (hash): {vault_items[0].get('itemHash')}")
    #     # else:
    #     #     logger.error(f"Failed to get profile response. Data: {profile_data}")

    #     # Test get_all_weapons (will use the mocked services if mocks are used, or real services)
    #     # all_weapons = weapon_api_instance.get_all_weapons(test_membership_type, test_destiny_membership_id)
    #     # logger.info(f"Found {len(all_weapons)} weapons.")
    #     # if all_weapons:
    #     #     logger.info(f"First weapon: {all_weapons[0].name}, Instance ID: {all_weapons[0].instance_id}")
    #     #     logger.info(f"Raw instance sockets for first weapon: {all_weapons[0].raw_instance_sockets_list}")


    print("WeaponAPI module loaded. Run within the FastAPI app context or with appropriate mocks for standalone testing.") 