import requests
import logging
from typing import List, Dict, Any, Optional
from .models import Weapon # Use explicit relative import
# Assuming a manifest manager class exists, e.g., in manifest.py
# from manifest import ManifestManager 
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
    def __init__(self, api_key: str, manifest_manager: Any): # Accept manifest_manager
        self.api_key = api_key
        self.base_url = "https://www.bungie.net/Platform"
        self.manifest = manifest_manager # Store manifest manager

    def _get_authenticated_headers(self, access_token: str) -> Dict[str, str]:
        """Gets the necessary headers for authenticated Bungie API requests."""
        if not access_token:
            raise ValueError("Access token is required for authenticated headers")
        
        return {
            "Authorization": f"Bearer {access_token}",
            "X-API-Key": self.api_key
        }

    def get_membership_info(self, access_token: str) -> Optional[Dict[str, Any]]:
        """Gets the user's primary Destiny membership ID and type."""
        headers = self._get_authenticated_headers(access_token)
        url = f"{self.base_url}/User/GetMembershipsForCurrentUser/"
        
        try:
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            if data['ErrorCode'] == 1 and data['Response']['destinyMemberships']:
                # Prefer Steam (3) > PSN (2) > Xbox (1) > Stadia (5) etc. or just take the first one?
                # For simplicity, let's take the first one or primary if set
                primary_membership_id = data['Response'].get('primaryMembershipId')
                membership = None
                if primary_membership_id:
                     membership = next((m for m in data['Response']['destinyMemberships'] if m['membershipId'] == primary_membership_id), None)

                if not membership and data['Response']['destinyMemberships']:
                    membership = data['Response']['destinyMemberships'][0] # Fallback to first

                if membership:
                     logger.info(f"Found membership: Type={membership['membershipType']}, ID={membership['membershipId']}")
                     return {"type": membership['membershipType'], "id": membership['membershipId']}
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

    def get_all_weapons(self, access_token: str, membership_type: int, destiny_membership_id: str) -> List[Weapon]:
        """
        Get all weapons for a user from the Destiny 2 API.
        
        Args:
            access_token: The user's access token.
            membership_type: The user's membership type.
            destiny_membership_id: The user's Destiny membership ID.
        
        Returns:
            A list of Weapon objects.
        """
        logger.info(f"Fetching all weapons for user {destiny_membership_id}")
        start_time = time.time() # Start timing
        
        try:
            # Get profile data
            profile_components_data = self._get_profile_components(
                access_token,
                membership_type,
                destiny_membership_id,
                # Request vault, character inventories, instances, and sockets
                [201, 205, 300, 305]  # 201=ProfileInv, 205=CharInv, 300=ItemInstances, 305=ItemSockets
            )
            
            if not profile_components_data:
                logger.error("Failed to get profile components data")
                return []
                
            # Pre-fetch socket data if available
            item_sockets_data = profile_components_data.get("Response", {}).get("itemComponents", {}).get("sockets", {}).get("data", {})

            # Process the weapons from the response
            weapons = []
            
            # --- Helper function to process a single item ---
            def process_item(item: Dict[str, Any], location_prefix: str) -> Optional[Weapon]:
                if "itemHash" not in item:
                    return None

                item_hash = item["itemHash"]
                item_instance_id = item.get("itemInstanceId")

                # Get item definition from manifest
                item_def = self.manifest.get_definition("DestinyInventoryItemDefinition", item_hash)

                # Check if it's a weapon (itemType=3)
                if not item_def or item_def.get('itemType') != ITEM_TYPE_WEAPON:
                    return None

                # Extract base weapon data
                display_props = item_def.get('displayProperties', {})
                name = display_props.get('name', f"Unknown Weapon {item_hash}")
                description = display_props.get('description', '')
                icon_url = "https://www.bungie.net" + display_props.get('icon', '') if display_props.get('icon') else ''
                tier_type = item_def.get('inventory', {}).get('tierTypeName', 'Unknown')
                item_type = item_def.get('itemTypeDisplayName', 'Unknown Weapon Type')
                item_sub_type = item_def.get('itemSubTypeDisplayName', '')
                damage_type_int = item_def.get("defaultDamageType", 0) # Get default damage type from definition
                damage_type_str = DAMAGE_TYPE_MAP.get(damage_type_int, "Unknown")

                # Extract perks
                perk_names = []
                if item_instance_id and item_instance_id in item_sockets_data:
                    sockets = item_sockets_data[item_instance_id].get("sockets", [])
                    for socket in sockets:
                        plug_hash = socket.get("plugHash")
                        if plug_hash and socket.get("isEnabled", True): # Check if socket/plug is enabled
                            plug_def = self.manifest.get_definition("DestinyInventoryItemDefinition", plug_hash)
                            if plug_def:
                                # Basic filtering: Example - Check plug category identifier or name patterns
                                # This needs refinement based on inspecting plug definitions
                                plug_category_id = plug_def.get("plug", {}).get("plugCategoryIdentifier", "")
                                plug_display_name = plug_def.get("displayProperties", {}).get("name", "")

                                # --- >>> TEMPORARY DEBUG LOGGING << --- 
                                # logger.info(f"      [Plug Found] Name: '{plug_display_name}', CategoryID: '{plug_category_id}'")
                                # --- >>> END DEBUG LOGGING << --- 

                                # --- Corrected Filtering Logic --- 
                                
                                # Define categories we definitely *want* to include
                                wanted_categories = [
                                    "intrinsics",
                                    "barrels",
                                    "tubes", # Launchers
                                    "magazines",
                                    "batteries", # Fusion rifles
                                    "magazines_gl", # Grenade launchers
                                    "arrows", # Bows
                                    "stocks",
                                    "grips",
                                    "guards", # Swords
                                    "blades", # Swords
                                    "origins",
                                    "frames", # Includes intrinsic frame AND selectable perks!
                                    # Add other relevant ones? e.g., specific exotic enhancements
                                ]

                                # Define categories/names we definitely *want* to exclude
                                excluded_substrings = [
                                    "shader",
                                    "masterworks",
                                    "tracker",
                                    "memento",
                                    "crafting",
                                    "empty",
                                    "default",
                                    "v400.weapon.mod" # Exclude weapon mods (unless desired later)
                                ]

                                is_wanted = plug_category_id in wanted_categories
                                
                                is_excluded = False
                                if not plug_display_name: # Exclude plugs with no name
                                     is_excluded = True
                                else:
                                     for sub in excluded_substrings:
                                          if sub in plug_category_id or sub in plug_display_name.lower():
                                               is_excluded = True
                                               break
                                
                                # Keep if it has a name, is in a wanted category, and is not explicitly excluded
                                if is_wanted and not is_excluded:
                                # General indicators of perks/frames/intrinsics
                                # is_likely_perk = (
                                #     "weapon.perk" in plug_category_id or
                                #     "frame." in plug_category_id or
                                #     "intrinsic" in plug_category_id or
                                #     "enhancements." in plug_category_id
                                # )

                                # Skip empty names or known junk categories explicitly
                                # is_junk = (
                                #     plug_display_name == "" or
                                #     "shader" in plug_category_id or
                                #     "masterworks" in plug_category_id or
                                #     "tracker" in plug_category_id or
                                #     "memento" in plug_category_id or
                                #     "empty" in plug_display_name.lower() or
                                #     "default" in plug_display_name.lower()
                                # )

                                # Add if it has a name, looks like a perk, and isn't explicitly junk
                                # if is_likely_perk and not is_junk:
                                # Check if the plug category starts with any allowed prefix or matches exactly
                                # is_allowed_category = False
                                # for cat in allowed_categories:
                                #     if plug_category_id == cat or plug_category_id.startswith(cat):
                                #         is_allowed_category = True
                                #         break

                                # Skip empty names or known junk categories explicitly (redundant but safe)
                                # is_junk = ("shader" in plug_category_id or
                                #            "masterworks" in plug_category_id or
                                #            "tracker" in plug_category_id or
                                #            "memento" in plug_category_id or
                                #            "empty" in plug_display_name.lower() or
                                #            "default" in plug_display_name.lower()) # Avoid "Default Shader/Ornament"

                                # Add if it has a name, is in an allowed category, and isn't explicitly junk
                                # if plug_display_name and is_allowed_category and not is_junk:
                                # TEMP: Loosen filtering - Add *any* plug with a name to see what we get
                                # if plug_display_name:
                                # if (is_weapon_perk or plug_category_id == "intrinsic") and not is_shader and not is_tracker and not is_masterwork:
                                #      if plug_display_name: # Ensure name exists
                                     perk_names.append(plug_display_name)
                                else:
                                     # Log skipped plugs only if they weren't explicitly excluded junk
                                     if not is_excluded:
                                         logger.debug(f"Skipping plug '{plug_display_name}' (Hash: {plug_hash}) with category '{plug_category_id}' for weapon {name}")


                # Create raw weapon dict
                location = location_prefix
                if location_prefix != "vault": # Handle character locations
                     location = f"equipped_{location_prefix}" if item.get("isEquipped") else f"inventory_{location_prefix}"
                
                raw_weapon = {
                    "item_hash": str(item_hash),
                    "instance_id": item_instance_id,
                    "location": location,
                    "is_equipped": item.get("isEquipped", False) if location_prefix != "vault" else False,
                    "damage_type": damage_type_str,
                    "name": name,
                    "description": description,
                    "icon_url": icon_url,
                    "tier_type": tier_type,
                    "item_type": item_type,
                    "item_sub_type": item_sub_type,
                    "perks": perk_names # Add extracted perks
                }

                # Validate and return
                try:
                    weapon = Weapon.model_validate(raw_weapon)
                    return weapon
                except Exception as val_err:
                    logger.warning(f"Pydantic validation failed for weapon {name} ({item_hash}): {val_err}")
                    return None
            # --- End Helper function ---


            # Process character inventories
            if "characterInventories" in profile_components_data.get("Response", {}):
                char_inventories_data = profile_components_data["Response"]["characterInventories"].get("data", {})
                if char_inventories_data: # Check if data exists
                     for character_id, inventory in char_inventories_data.items():
                          for item in inventory.get("items", []):
                              processed_weapon = process_item(item, character_id)
                              if processed_weapon:
                                   weapons.append(processed_weapon)
                else:
                     logger.warning("Character inventories data is present but empty or null.")


            # Process profile inventory (vault)
            if "profileInventory" in profile_components_data.get("Response", {}):
                profile_inventory_data = profile_components_data["Response"]["profileInventory"].get("data", {})
                if profile_inventory_data: # Check if data exists
                     for item in profile_inventory_data.get("items", []):
                          processed_weapon = process_item(item, "vault")
                          if processed_weapon:
                               weapons.append(processed_weapon)
                else:
                     logger.warning("Profile inventory data is present but empty or null.")


            logger.info(f"Found {len(weapons)} weapons with perk processing attempt")
            end_time = time.time() # End timing
            logger.info(f"get_all_weapons for user {destiny_membership_id} took {end_time - start_time:.4f} seconds") # Log duration
            return weapons
                
        except Exception as e:
            logger.error(f"Error getting all weapons: {e}", exc_info=True)
            return []

    def _get_profile_components(self, access_token: str, membership_type: int, destiny_membership_id: str, components: List[int]) -> Optional[dict]:
        """
        Get profile components data from the Destiny 2 API.
        
        Args:
            access_token: The user's access token.
            membership_type: The user's membership type.
            destiny_membership_id: The user's Destiny membership ID.
            components: The components to request from the API.
            
        Returns:
            The profile components data as a dictionary, or None if the request failed.
        """
        headers = self._get_authenticated_headers(access_token)
        components_str = ",".join(str(c) for c in components)
        url = f"{self.base_url}/Destiny2/{membership_type}/Profile/{destiny_membership_id}/?components={components_str}"
        
        try:
            logger.info(f"Fetching profile data with components {components_str}")
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            if data.get("ErrorCode") != 1:
                error_message = data.get("Message", "Unknown error")
                logger.error(f"Bungie API error: {error_message}")
                return None
                
            return data
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching profile components: {e}", exc_info=True)
            return None

# Example usage (for testing standalone if needed)
if __name__ == '__main__':
    # This part would require setting up a dummy OAuthManager or actual credentials
    # and is primarily for demonstrating the structure.
    print("WeaponAPI module loaded. Run within the FastAPI app context.") 