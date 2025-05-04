import requests
import logging
from typing import List, Dict, Any, Optional
from .models import Weapon # Use explicit relative import
# Assuming a manifest manager class exists, e.g., in manifest.py
# from manifest import ManifestManager 

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
        
        try:
            # Get profile data
            profile_components_data = self._get_profile_components(
                access_token,
                membership_type,
                destiny_membership_id,
                # We need character inventories, vault, and item instances
                [102, 201, 300]  # 102=ProfileInventories, 201=CharacterInventories, 300=ItemInstances
            )
            
            if not profile_components_data:
                logger.error("Failed to get profile components data")
                return []
                
            # Process the weapons from the response
            weapons = []
            
            # TODO: Extract actual weapon data from profile_components_data
            # For now, just return the raw data with some minimal processing
            
            # Process character inventories
            if "characterInventories" in profile_components_data.get("Response", {}):
                char_inventories = profile_components_data["Response"]["characterInventories"]["data"]
                
                for character_id, inventory in char_inventories.items():
                    for item in inventory.get("items", []):
                        # Check if it's a weapon (itemType=3)
                        # In a real implementation, you would check the item definition
                        # Here we're just assuming items with certain properties are weapons
                        
                        if "itemHash" in item:
                            # Get item definition from manifest
                            # This is where you'd use self.manifest.get_definition("DestinyInventoryItemDefinition", item["itemHash"])
                            # For now, we'll just create a dummy weapon with the hash
                            
                            # Create a basic weapon object with available data
                            raw_weapon = {
                                "item_hash": item.get("itemHash"),
                                "instance_id": item.get("itemInstanceId"),
                                "location": f"equipped_{character_id}" if item.get("isEquipped") else f"inventory_{character_id}",
                                "is_equipped": item.get("isEquipped", False),
                                "damage_type": item.get("damageType", 0),
                                # These would come from the manifest in a real implementation
                                "name": f"Weapon {item.get('itemHash')}",
                                "description": f"A weapon with hash {item.get('itemHash')}",
                                "icon_url": "https://www.bungie.net/common/destiny2_content/icons/e4a1a5aaeb9f65cc5276fd4d86799103.jpg",
                                "tier_type": "Legendary",
                                "item_type": "Auto Rifle",
                                "item_sub_type": "Precision Frame"
                            }
                            
                            # Use the from_dict method to create a valid Weapon object
                            weapon = Weapon.from_dict(raw_weapon)
                            weapons.append(weapon)
            
            # Process profile inventory (vault)
            if "profileInventory" in profile_components_data.get("Response", {}):
                profile_inventory = profile_components_data["Response"]["profileInventory"]["data"]
                
                for item in profile_inventory.get("items", []):
                    if "itemHash" in item:
                        raw_weapon = {
                            "item_hash": item.get("itemHash"),
                            "instance_id": item.get("itemInstanceId"),
                            "location": "vault",
                            "is_equipped": False,
                            "damage_type": item.get("damageType", 0),
                            # These would come from the manifest in a real implementation
                            "name": f"Vault Weapon {item.get('itemHash')}",
                            "description": f"A weapon in the vault with hash {item.get('itemHash')}",
                            "icon_url": "https://www.bungie.net/common/destiny2_content/icons/e4a1a5aaeb9f65cc5276fd4d86799103.jpg",
                            "tier_type": "Legendary",
                            "item_type": "Hand Cannon",
                            "item_sub_type": "Adaptive Frame"
                        }
                        
                        # Use the from_dict method to create a valid Weapon object
                        weapon = Weapon.from_dict(raw_weapon)
                        weapons.append(weapon)
                        
            logger.info(f"Found {len(weapons)} weapons")
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