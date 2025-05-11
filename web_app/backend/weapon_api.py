import requests
import logging
from typing import List, Dict, Any, Optional
import asyncio # Import asyncio for potential gather later

from .models import Weapon, WeaponPerkDetail # Use explicit relative import, ADD WeaponPerkDetail
from .manifest import SupabaseManifestService # Import the new service
from .bungie_oauth import OAuthManager # Import OAuthManager
import time
from web_app.backend.dim_socket_hashes import (
    SocketCategoryHashes,
    COL1_CATEGORIES as BARREL_CATEGORY_HASHES,
    COL2_CATEGORIES as MAGAZINE_CATEGORY_HASHES,
    COL3_TRAIT_CATEGORIES as TRAIT_PERK_MAIN_CATEGORY_HASHES,
    ORIGIN_TRAIT_CATEGORIES as ORIGIN_TRAIT_CATEGORY_HASHES,
    INTRINSIC_TRAIT_CATEGORIES as INTRINSIC_CATEGORY_HASHES,
)

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

# # Build lists from the generated enum for each category
# BARREL_CATEGORY_HASHES = [h.value for h in SocketCategoryHashes if "BARREL" in h.name.upper()]
# MAGAZINE_CATEGORY_HASHES = [h.value for h in SocketCategoryHashes if "MAGAZINE" in h.name.upper()]
# TRAIT_PERK_MAIN_CATEGORY_HASHES = [h.value for h in SocketCategoryHashes if "TRAIT" in h.name.upper()]
# ORIGIN_TRAIT_CATEGORY_HASHES = [h.value for h in SocketCategoryHashes if "ORIGINTRAIT" in h.name.upper()]
# INTRINSIC_CATEGORY_HASHES = [h.value for h in SocketCategoryHashes if "INTRINSIC" in h.name.upper()]

class WeaponAPI:
    def __init__(self, oauth_manager: OAuthManager, manifest_service: SupabaseManifestService):
        self.oauth_manager = oauth_manager # Store OAuthManager
        self.base_url = "https://www.bungie.net/Platform"
        self.manifest_service = manifest_service # Store SupabaseManifestService
        self.session = self._create_session() # Keep synchronous session for now

    def _create_session(self) -> requests.Session: # Stays synchronous
        session = requests.Session()
        # ... (retry logic unchanged) ...
        return session

    def _get_authenticated_headers(self) -> Dict[str, str]: # Remove access_token param
        # Get headers from OAuthManager, which handles refresh
        return self.oauth_manager.get_headers()

    def get_membership_info(self) -> Optional[Dict[str, Any]]: # Remove access_token param, stays synchronous
        headers = self._get_authenticated_headers() # Call updated method
        url = f"{self.base_url}/User/GetMembershipsForCurrentUser/"
        try:
            response = self.session.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            if data['ErrorCode'] == 1 and data['Response']['destinyMemberships']:
                primary_membership_id = data['Response'].get('primaryMembershipId')
                membership = None
                if primary_membership_id:
                     membership = next((m for m in data['Response']['destinyMemberships'] if m['membershipId'] == primary_membership_id), None)
                if not membership and data['Response']['destinyMemberships']:
                    membership = data['Response']['destinyMemberships'][0]
                if membership:
                     logger.info(f"Found membership: Type={membership['membershipType']}, ID={membership['membershipId']}")
                     return {
                         "type": membership['membershipType'], 
                         "id": membership['membershipId'],
                         "bungieGlobalDisplayName": membership.get('bungieGlobalDisplayName', ''),
                         "bungieGlobalDisplayNameCode": membership.get('bungieGlobalDisplayNameCode', '')
                     }
                else:
                     logger.error("No destiny memberships found for user.")
                     return None
            else:
                logger.error(f"Error fetching membership info: {data.get('Message', 'Unknown error')}")
                return None
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP Error fetching membership info: {e}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Error processing membership info: {e}", exc_info=True)
            return None

    def get_all_weapons(self, membership_type: int, destiny_membership_id: str) -> List[Weapon]:
        logger.info(f"Fetching all weapons for user {destiny_membership_id}")
        start_time = time.time()
        try:
            # Call the now public get_profile_response method
            profile_data = self.get_profile_response(
                membership_type, destiny_membership_id, [102, 201, 205, 300, 305]
            )
            # The original profile_components_data was the whole JSON response,
            # get_profile_response now returns the whole JSON response as well.
            if not profile_data or "Response" not in profile_data:
                logger.error("Failed to get profile data or Response key missing")
                return []

            response_data = profile_data["Response"]
            item_sockets_data = response_data.get("itemComponents", {}).get("sockets", {}).get("data", {})
            plug_objectives_data = response_data.get("itemComponents", {}).get("plugObjectives", {}).get("data", {})

            all_item_hashes = set()
            all_plug_hashes = set()

            inventories_to_scan = []
            if response_data.get("characterInventories", {}).get("data"):
                for char_inv in response_data["characterInventories"]["data"].values():
                    inventories_to_scan.extend(char_inv.get("items", []))
            if response_data.get("characterEquipment", {}).get("data"):
                for char_equip in response_data["characterEquipment"]["data"].values():
                    inventories_to_scan.extend(char_equip.get("items", []))
            if response_data.get("profileInventory", {}).get("data"):
                inventories_to_scan.extend(response_data["profileInventory"]["data"].get("items", []))

            for item_data in inventories_to_scan:
                if "itemHash" in item_data:
                    all_item_hashes.add(item_data["itemHash"])
                    item_instance_id = item_data.get("itemInstanceId")
                    if item_instance_id and item_instance_id in item_sockets_data:
                        sockets = item_sockets_data[item_instance_id].get("sockets", [])
                        for socket in sockets:
                            if socket.get("plugHash"):
                                all_plug_hashes.add(socket["plugHash"])
            
            all_definition_hashes = list(all_item_hashes.union(all_plug_hashes))

            all_definitions_map: Dict[int, Dict[str, Any]] = {}
            if all_definition_hashes:
                logger.info(f"Batch fetching {len(all_definition_hashes)} item/plug definitions.")
                all_definitions_map = self.manifest_service.get_definitions_batch(
                    "destinyinventoryitemdefinition", 
                    all_definition_hashes
                )
                logger.info(f"Successfully fetched {len(all_definitions_map)} definitions.")
            else:
                logger.info("No item or plug hashes found to fetch definitions for.")
                return []

            weapons = []

            def process_item_sync(item_data: Dict[str, Any], location_prefix: str, definitions_cache: Dict[int, Dict[str, Any]]) -> Optional[Weapon]:
                if "itemHash" not in item_data: return None
                item_hash = item_data["itemHash"]
                item_instance_id = item_data.get("itemInstanceId")
                
                item_def = definitions_cache.get(item_hash)
                if not item_def or item_def.get('itemType') != ITEM_TYPE_WEAPON:
                    return None
                
                display_props = item_def.get('displayProperties', {})
                name = display_props.get('name', f"Unknown Weapon {item_hash}")
                description = display_props.get('description', '')
                icon_url = "https://www.bungie.net" + display_props.get('icon', '') if display_props.get('icon') else ''
                tier_type = item_def.get('inventory', {}).get('tierTypeName', 'Unknown')
                item_type_display = item_def.get('itemTypeDisplayName', 'Unknown Weapon Type')
                item_sub_type_str = str(item_def.get('itemSubType', 0))
                damage_type_int = item_def.get("defaultDamageType", 0)
                damage_type_str = DAMAGE_TYPE_MAP.get(damage_type_int, "Unknown")
                power_level = item_data.get("primaryStat", {}).get("value") if item_instance_id else None

                barrel_perks_list: List[WeaponPerkDetail] = []
                magazine_perks_list: List[WeaponPerkDetail] = []
                trait_perk_col1_list: List[WeaponPerkDetail] = []
                trait_perk_col2_list: List[WeaponPerkDetail] = []
                origin_trait_detail: Optional[WeaponPerkDetail] = None

                weapon_socket_categories = item_def.get("sockets", {}).get("socketCategories", [])
                
                instance_sockets = []
                if item_instance_id and item_instance_id in item_sockets_data:
                    instance_sockets = item_sockets_data[item_instance_id].get("sockets", [])

                socket_index_to_plug_hash_map: Dict[int, int] = {
                    idx: s.get("plugHash") for idx, s in enumerate(instance_sockets) 
                    if s.get("plugHash") and s.get("isEnabled", False) and s.get("isVisible", True)
                }

                processed_trait_socket_indexes = set()

                for category in weapon_socket_categories:
                    category_hash = category.get("socketCategoryHash")
                    socket_indexes_in_category = category.get("socketIndexes", [])
                    for socket_idx in socket_indexes_in_category:
                        plug_hash = socket_index_to_plug_hash_map.get(socket_idx)
                        if not plug_hash: continue
                        plug_def = definitions_cache.get(plug_hash)
                        if not plug_def: continue
                        plug_display_props = plug_def.get("displayProperties", {})
                        perk_name = plug_display_props.get("name")
                        perk_description = plug_display_props.get("description", "")
                        perk_icon_path = plug_display_props.get("icon", "")
                        perk_icon_url = f"https://www.bungie.net{perk_icon_path}" if perk_icon_path else "https://www.bungie.net/common/destiny2_content/icons/broken_icon.png"
                        if not perk_name or "shader" in plug_def.get("plug",{}).get("plugCategoryIdentifier"," ").lower() or "empty" in perk_name.lower() or "default" in perk_name.lower():
                            continue
                        perk_detail = WeaponPerkDetail(
                            perk_hash=plug_hash,
                            name=perk_name,
                            description=perk_description,
                            icon_url=perk_icon_url
                        )
                        if category_hash in BARREL_CATEGORY_HASHES:
                            barrel_perks_list.append(perk_detail)
                        elif category_hash in MAGAZINE_CATEGORY_HASHES:
                            magazine_perks_list.append(perk_detail)
                        elif category_hash in ORIGIN_TRAIT_CATEGORY_HASHES:
                            if not origin_trait_detail:
                                origin_trait_detail = perk_detail
                        elif category_hash in TRAIT_PERK_MAIN_CATEGORY_HASHES:
                            if socket_idx not in processed_trait_socket_indexes:
                                if not trait_perk_col1_list:
                                    trait_perk_col1_list.append(perk_detail)
                                    processed_trait_socket_indexes.add(socket_idx)
                                elif not trait_perk_col2_list:
                                    trait_perk_col2_list.append(perk_detail)
                                    processed_trait_socket_indexes.add(socket_idx)
                return Weapon(
                    item_hash=str(item_hash),
                    instance_id=item_instance_id,
                    name=name, 
                    description=description, 
                    icon_url=icon_url if icon_url else None,
                    tier_type=tier_type, 
                    item_type=item_type_display, 
                    item_sub_type=str(item_def.get("itemSubType", 0)),
                    damage_type=damage_type_str,
                    power_level=power_level,
                    barrel_perks=barrel_perks_list, # These are INSTANCE perks
                    magazine_perks=magazine_perks_list, # These are INSTANCE perks
                    trait_perk_col1=trait_perk_col1_list, # These are INSTANCE perks
                    trait_perk_col2=trait_perk_col2_list, # These are INSTANCE perks
                    origin_trait=origin_trait_detail, # This is an INSTANCE perk
                    location=location_prefix,
                    is_equipped="Equipped" in location_prefix,
                    raw_instance_sockets_list=instance_sockets # Pass along for potential detailed analysis
                )

            # Process items from character inventories
            if response_data.get("characterInventories", {}).get("data"):
                for char_id, char_inv in response_data["characterInventories"]["data"].items():
                    char_name = response_data.get("characters",{}).get("data",{}).get(char_id,{}).get("characterClassResolved","Character")
                    for item_data in char_inv.get("items", []):
                        weapon = process_item_sync(item_data, f"Inventory ({char_name})", all_definitions_map)
                        if weapon:
                            weapons.append(weapon)
            
            # Process items from character equipment
            if response_data.get("characterEquipment", {}).get("data"):
                for char_id, char_equip in response_data["characterEquipment"]["data"].items():
                    char_name = response_data.get("characters",{}).get("data",{}).get(char_id,{}).get("characterClassResolved","Character")
                    for item_data in char_equip.get("items", []):
                        weapon = process_item_sync(item_data, f"Equipped ({char_name})", all_definitions_map)
                        if weapon:
                            weapons.append(weapon)

            # Process items from profile inventory (vault)
            if response_data.get("profileInventory", {}).get("data"):
                for item_data in response_data["profileInventory"]["data"].get("items", []):
                    weapon = process_item_sync(item_data, "Vault", all_definitions_map)
                    if weapon:
                        weapons.append(weapon)
            
            end_time = time.time()
            logger.info(f"Finished fetching and processing all weapons in {end_time - start_time:.2f} seconds. Found {len(weapons)} weapons.")
            return weapons

        except Exception as e:
            logger.error(f"Unexpected error in get_all_weapons: {e}", exc_info=True)
            return []

    # Renamed from _get_profile_components and made public.
    # This method fetches the raw profile response from Bungie.
    def get_profile_response(self, membership_type: int, destiny_membership_id: str, components: List[int]) -> Optional[dict]:
        headers = self._get_authenticated_headers()
        if not headers:
            logger.error("Authentication headers are missing, cannot fetch profile components.")
            return None

        components_str = ",".join(map(str, components))
        url = f"{self.base_url}/Destiny2/{membership_type}/Profile/{destiny_membership_id}/?components={components_str}"
        
        logger.debug(f"Requesting profile components from: {url} with components: {components_str}")

        try:
            response = self.session.get(url, headers=headers)
            response.raise_for_status()  # Raises HTTPError for bad responses (4XX or 5XX)
            data = response.json() # This can raise ValueError if response is not JSON
            
            # Check Bungie API's own error code
            if data.get('ErrorCode') == 1: # 1 typically means success
                logger.info(f"Successfully fetched profile components for user {destiny_membership_id}.")
                return data # Return the entire successful response object
            else:
                # Log Bungie-specific error if ErrorCode is not 1
                error_message = data.get('Message', 'Unknown Bungie API error')
                status = data.get('ErrorStatus', 'Unknown Status')
                logger.error(f"Bungie API Error fetching profile components: {error_message} (ErrorCode: {data.get('ErrorCode')}, Status: {status}) for URL: {url}")
                return None
        except requests.exceptions.HTTPError as http_err:
            # This catches 4xx/5xx errors after raise_for_status()
            logger.error(f"HTTP error occurred while fetching profile components: {http_err} - URL: {url} - Response: {http_err.response.text}", exc_info=True)
            return None
        except requests.exceptions.RequestException as req_err:
            # This catches other request-related errors (DNS failure, connection timeout, etc.)
            logger.error(f"Request error occurred while fetching profile components: {req_err} - URL: {url}", exc_info=True)
            return None
        except ValueError as json_err: # Catches JSONDecodeError if response isn't valid JSON
            logger.error(f"JSON decode error while fetching profile components: {json_err} - URL: {url}", exc_info=True)
            # It might be useful to log response.text here if it's small enough and not sensitive
            # logger.debug(f"Non-JSON response text: {response.text}")
            return None
        except Exception as e:
            # Catch-all for any other unexpected errors
            logger.error(f"An unexpected error occurred while fetching profile components: {e} - URL: {url}", exc_info=True)
            return None

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