import requests
import logging
from typing import List, Dict, Any, Optional
import asyncio # Import asyncio for potential gather later

from .models import Weapon, WeaponPerkDetail # Use explicit relative import, ADD WeaponPerkDetail
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

    async def get_all_weapons(self, membership_type: int, destiny_membership_id: str) -> List[Weapon]:
        logger.info(f"Fetching all weapons for user {destiny_membership_id}")
        start_time = time.time()
        try:
            profile_components_data = self._get_profile_components(
                membership_type, destiny_membership_id, [102, 201, 205, 300, 305] # Added 300 for item plug states (sockets)
            )
            if not profile_components_data or "Response" not in profile_components_data:
                logger.error("Failed to get profile components data or Response key missing")
                return []

            response_data = profile_components_data["Response"]
            item_sockets_data = response_data.get("itemComponents", {}).get("sockets", {}).get("data", {})
            # For itemPlugObjectives component 300
            plug_objectives_data = response_data.get("itemComponents", {}).get("plugObjectives", {}).get("data", {})

            all_item_hashes = set()
            all_plug_hashes = set()

            # --- Step 1: Collect all item and plug hashes ---
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
            
            # Combine all hashes that need to be looked up in DestinyInventoryItemDefinition
            all_definition_hashes = list(all_item_hashes.union(all_plug_hashes))

            # --- Step 2: Batch fetch all definitions ---
            all_definitions_map: Dict[int, Dict[str, Any]] = {}
            if all_definition_hashes:
                logger.info(f"Batch fetching {len(all_definition_hashes)} item/plug definitions.")
                all_definitions_map = await self.manifest_service.get_definitions_batch(
                    "destinyinventoryitemdefinition", 
                    all_definition_hashes
                )
                logger.info(f"Successfully fetched {len(all_definitions_map)} definitions.")
            else:
                logger.info("No item or plug hashes found to fetch definitions for.")
                return [] # Or handle as appropriate if no items means no weapons

            weapons = []

            # --- Step 3: Define synchronous process_item helper ---
            def process_item_sync(item_data: Dict[str, Any], location_prefix: str, definitions_cache: Dict[int, Dict[str, Any]]) -> Optional[Weapon]:
                if "itemHash" not in item_data: return None
                item_hash = item_data["itemHash"]
                item_instance_id = item_data.get("itemInstanceId")
                
                item_def = definitions_cache.get(item_hash)
                if not item_def or item_def.get('itemType') != ITEM_TYPE_WEAPON:
                    # logger.debug(f"Skipping item {item_hash} as it's not a weapon or has no definition.")
                    return None
                
                display_props = item_def.get('displayProperties', {})
                name = display_props.get('name', f"Unknown Weapon {item_hash}")
                # logger.debug(f"Processing weapon: {name} ({item_hash}), Instance: {item_instance_id}")

                description = display_props.get('description', '')
                icon_url = "https://www.bungie.net" + display_props.get('icon', '') if display_props.get('icon') else ''
                tier_type = item_def.get('inventory', {}).get('tierTypeName', 'Unknown')
                item_type_display = item_def.get('itemTypeDisplayName', 'Unknown Weapon Type')
                item_sub_type_str = str(item_def.get('itemSubType', 0)) # Match Pydantic model if it expects string
                damage_type_int = item_def.get("defaultDamageType", 0)
                damage_type_str = DAMAGE_TYPE_MAP.get(damage_type_int, "Unknown")
                power_level = item_data.get("primaryStat", {}).get("value") if item_instance_id else None # Get power level for instanced items

                # Initialize perk lists for the new model structure
                barrel_perks_list: List[WeaponPerkDetail] = []
                magazine_perks_list: List[WeaponPerkDetail] = []
                trait_perk_col1_list: List[WeaponPerkDetail] = []
                trait_perk_col2_list: List[WeaponPerkDetail] = []
                origin_trait_detail: Optional[WeaponPerkDetail] = None

                # Socket definitions from the weapon's manifest entry
                weapon_socket_entries = item_def.get("sockets", {}).get("socketEntries", [])
                weapon_socket_categories = item_def.get("sockets", {}).get("socketCategories", [])

                # --- Known Socket Category Hashes (approximations, verify these with manifest inspection) ---
                # These hashes can be found by inspecting DestinySocketCategoryDefinition in manifest
                # Or by looking at weapon definitions (e.g. item_def['sockets']['socketCategories'])
                BARREL_CATEGORY_HASHES = [4241085061] # Example: "Weapon Barrel"
                MAGAZINE_CATEGORY_HASHES = [192609005] # Example: "Weapon Magazine"
                # Trait perks often fall under a general category, might need index-based or plugCategoryIdentifier filtering
                TRAIT_PERK_MAIN_CATEGORY_HASHES = [2685412097] # Example: "Weapon Perks"
                ORIGIN_TRAIT_CATEGORY_HASHES = [270265983, 3379164202, 2237050098] # Example hashes for origin traits, REMOVED "reforming_frame_category_hash"

                # Get the actual sockets and their plugged perks for this specific item instance
                instance_sockets = []
                if item_instance_id and item_instance_id in item_sockets_data:
                    instance_sockets = item_sockets_data[item_instance_id].get("sockets", [])

                # Create a map of socketIndex to plugHash for easy lookup for this instance
                # Only consider enabled plugs
                socket_index_to_plug_hash_map: Dict[int, int] = {
                    idx: s.get("plugHash") for idx, s in enumerate(instance_sockets) 
                    if s.get("plugHash") and s.get("isEnabled", False) and s.get("isVisible", True)
                }

                processed_trait_socket_indexes = set()

                for category in weapon_socket_categories:
                    category_hash = category.get("socketCategoryHash")
                    socket_indexes_in_category = category.get("socketIndexes", [])

                    # logger.debug(f"Weapon: {name}, Category: {category_hash}, Sockets: {socket_indexes_in_category}")

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
                        
                        # Ensure we have a name, skip if it's a hidden/default/empty plug
                        if not perk_name or "shader" in plug_def.get("plug",{}).get("plugCategoryIdentifier","").lower() or "empty" in perk_name.lower() or "default" in perk_name.lower():
                            continue

                        perk_detail = WeaponPerkDetail(
                            perk_hash=plug_hash,
                            name=perk_name,
                            description=perk_description,
                            icon_url=perk_icon_url
                        )

                        # Categorize the perk
                        if category_hash in BARREL_CATEGORY_HASHES:
                            barrel_perks_list.append(perk_detail)
                        elif category_hash in MAGAZINE_CATEGORY_HASHES:
                            magazine_perks_list.append(perk_detail)
                        elif category_hash in ORIGIN_TRAIT_CATEGORY_HASHES:
                            if not origin_trait_detail: # Only take the first one if multiple are somehow present
                                origin_trait_detail = perk_detail
                        elif category_hash in TRAIT_PERK_MAIN_CATEGORY_HASHES:
                            # This is where it gets tricky. We need to ensure we get the two main trait perks in order.
                            # We also need to avoid intrinsic perks if they share this category.
                            # The `socket_indexes_in_category` from weapon_def should represent the order.
                            # Check if it's an intrinsic plug (sometimes plugCategoryIdentifier helps, e.g. "frames")
                            plug_category_id = plug_def.get("plug", {}).get("plugCategoryIdentifier", "").lower()
                            if "frames" in plug_category_id or "intrinsics" in plug_category_id or "enhancements.season" in plug_category_id:
                                # logger.debug(f"Skipping intrinsic/frame perk {perk_name} in TRAIT_PERK_MAIN_CATEGORY for {name}")
                                continue # Skip intrinsic frames that might be in the main perk category
                            
                            if socket_idx not in processed_trait_socket_indexes:
                                if not trait_perk_col1_list:
                                    trait_perk_col1_list.append(perk_detail)
                                    processed_trait_socket_indexes.add(socket_idx)
                                elif not trait_perk_col2_list:
                                    trait_perk_col2_list.append(perk_detail)
                                    processed_trait_socket_indexes.add(socket_idx)
                                # else: logger.debug(f"Already filled trait perk slots for {name}, found extra: {perk_name}")

                        # else:
                            # logger.debug(f"Perk '{perk_name}' (cat hash {category_hash}) for {name} did not fit predefined categories.")

                return Weapon(
                    item_hash=str(item_hash),
                    instance_id=item_instance_id,
                    name=name, 
                    description=description, 
                    icon_url=icon_url if icon_url else None, # Ensure None if empty string
                    tier_type=tier_type, 
                    item_type=item_type_display, 
                    item_sub_type=str(item_def.get("itemSubType", 0)), # Ensure string
                    damage_type=damage_type_str,
                    power_level=power_level,
                    barrel_perks=barrel_perks_list,
                    magazine_perks=magazine_perks_list,
                    trait_perk_col1=trait_perk_col1_list,
                    trait_perk_col2=trait_perk_col2_list,
                    origin_trait=origin_trait_detail,
                    location=location_prefix,
                    is_equipped="Equipped" in location_prefix # Simple check for equipped status
                )

            # --- Step 4: Process items using the synchronous helper and cached definitions ---
            # Character Inventories
            if response_data.get("characterInventories", {}).get("data"):
                for char_id, char_inv in response_data["characterInventories"]["data"].items():
                    for item_data_loop in char_inv.get("items", []):
                        weapon = process_item_sync(item_data_loop, f"Character {char_id} Inventory", all_definitions_map)
                        if weapon: weapons.append(weapon)
            # Character Equipment
            if response_data.get("characterEquipment", {}).get("data"):
                for char_id, char_equip in response_data["characterEquipment"]["data"].items():
                    for item_data_loop in char_equip.get("items", []):
                        weapon = process_item_sync(item_data_loop, f"Character {char_id} Equipped", all_definitions_map)
                        if weapon: weapons.append(weapon)
            # Profile Inventory (Vault)
            if response_data.get("profileInventory", {}).get("data"):
                for item_data_loop in response_data["profileInventory"]["data"].get("items", []):
                    weapon = process_item_sync(item_data_loop, "Vault", all_definitions_map)
                    if weapon: weapons.append(weapon)
            
            elapsed_time = time.time() - start_time
            logger.info(f"Fetched and processed {len(weapons)} weapons in {elapsed_time:.2f} seconds.")
            return weapons

        except Exception as e:
            logger.error(f"Error in get_all_weapons: {e}", exc_info=True)
            return []

    def _get_profile_components(self, membership_type: int, destiny_membership_id: str, components: List[int]) -> Optional[dict]: # Remove access_token param
        headers = self._get_authenticated_headers() # Call updated method
        components_str = ",".join(map(str, components))
        url = f"{self.base_url}/Destiny2/{membership_type}/Profile/{destiny_membership_id}/?components={components_str}"
        try:
            response = self.session.get(url, headers=headers)
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP Error fetching profile components {components_str}: {e}\nURL: {url}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Error processing profile components {components_str}: {e}\nURL: {url}", exc_info=True)
            return None

# Example usage (for testing standalone if needed)
if __name__ == '__main__':
    # This part would require setting up a dummy OAuthManager or actual credentials
    # and is primarily for demonstrating the structure.
    print("WeaponAPI module loaded. Run within the FastAPI app context.") 