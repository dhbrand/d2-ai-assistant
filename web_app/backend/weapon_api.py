import requests
import logging
from typing import List, Dict, Any, Optional
import asyncio # Import asyncio for potential gather later

from .models import Weapon # Use explicit relative import
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

    async def get_all_weapons(self, membership_type: int, destiny_membership_id: str) -> List[Weapon]: # Remove access_token param
        logger.info(f"Fetching all weapons for user {destiny_membership_id}")
        start_time = time.time()
        try:
            # Call updated _get_profile_components without access_token
            profile_components_data = self._get_profile_components(
                membership_type, destiny_membership_id, [102, 201, 205, 305]
            )
            if not profile_components_data:
                logger.error("Failed to get profile components data")
                return []
            item_sockets_data = profile_components_data.get("Response", {}).get("itemComponents", {}).get("sockets", {}).get("data", {})
            weapons = []

            async def process_item(item: Dict[str, Any], location_prefix: str) -> Optional[Weapon]: # BECOMES ASYNC
                if "itemHash" not in item: return None
                item_hash = item["itemHash"]
                item_instance_id = item.get("itemInstanceId")
                item_def = await self.manifest_service.get_definition("destinyinventoryitemdefinition", item_hash) # Use await
                if not item_def or item_def.get('itemType') != ITEM_TYPE_WEAPON: return None
                
                display_props = item_def.get('displayProperties', {})
                name = display_props.get('name', f"Unknown Weapon {item_hash}")
                description = display_props.get('description', '')
                icon_url = "https://www.bungie.net" + display_props.get('icon', '') if display_props.get('icon') else ''
                tier_type = item_def.get('inventory', {}).get('tierTypeName', 'Unknown')
                item_type_display = item_def.get('itemTypeDisplayName', 'Unknown Weapon Type') # Renamed to avoid conflict with item_type model field
                item_sub_type = item_def.get('itemSubTypeDisplayName', '')
                damage_type_int = item_def.get("defaultDamageType", 0)
                damage_type_str = DAMAGE_TYPE_MAP.get(damage_type_int, "Unknown")

                perk_names = []
                if item_instance_id and item_instance_id in item_sockets_data:
                    sockets = item_sockets_data[item_instance_id].get("sockets", [])
                    for socket in sockets:
                        plug_hash = socket.get("plugHash")
                        if plug_hash and socket.get("isEnabled", True):
                            plug_def = await self.manifest_service.get_definition("destinyinventoryitemdefinition", plug_hash) # Use await
                            if plug_def:
                                plug_category_id = plug_def.get("plug", {}).get("plugCategoryIdentifier", "")
                                plug_display_name = plug_def.get("displayProperties", {}).get("name", "")
                                wanted_categories = ["intrinsics", "barrels", "tubes", "magazines", "batteries", "magazines_gl", "arrows", "stocks", "grips", "guards", "blades", "origins", "frames"]
                                excluded_substrings = ["shader", "masterworks", "tracker", "memento", "crafting", "empty", "default", "v400.weapon.mod"]
                                is_wanted = plug_category_id in wanted_categories
                                is_excluded = False
                                if not plug_display_name: is_excluded = True
                                else:
                                     for sub in excluded_substrings:
                                          if sub in plug_category_id or sub in plug_display_name.lower():
                                               is_excluded = True; break
                                if is_wanted and not is_excluded:
                                     perk_names.append(plug_display_name)
                                elif not is_excluded:
                                     logger.debug(f"Skipping plug '{plug_display_name}' (Hash: {plug_hash}) with category '{plug_category_id}' for weapon {name}")
                
                return Weapon(
                    item_hash=str(item_hash),
                    instance_id=item_instance_id,
                    name=name, description=description, icon_url=icon_url,
                    tier_type=tier_type, item_type=item_type_display, item_sub_type=item_sub_type, # Ensure correct field name
                    damage_type=damage_type_str,
                    perks=perk_names,
                    location=location_prefix
                )

            # Process items from various inventory locations
            # Character Inventories
            if profile_components_data.get("Response", {}).get("characterInventories", {}).get("data"):
                for char_id, char_inv in profile_components_data["Response"]["characterInventories"]["data"].items():
                    for item in char_inv.get("items", []):
                        weapon = await process_item(item, f"Character {char_id} Inventory") # Use await
                        if weapon: weapons.append(weapon)
            # Character Equipment
            if profile_components_data.get("Response", {}).get("characterEquipment", {}).get("data"):
                for char_id, char_equip in profile_components_data["Response"]["characterEquipment"]["data"].items():
                    for item in char_equip.get("items", []):
                        weapon = await process_item(item, f"Character {char_id} Equipped") # Use await
                        if weapon: weapons.append(weapon)
            # Profile Inventory (Vault)
            if profile_components_data.get("Response", {}).get("profileInventory", {}).get("data"):
                for item in profile_components_data["Response"]["profileInventory"]["data"].get("items", []):
                    weapon = await process_item(item, "Vault") # Use await
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