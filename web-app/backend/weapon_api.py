import requests
import logging
from bungie_oauth import OAuthManager
from typing import List, Dict, Any, Optional

logger = logging.getLogger(__name__)

class WeaponAPI:
    def __init__(self, oauth_manager: OAuthManager):
        self.oauth_manager = oauth_manager
        self.base_url = "https://www.bungie.net/Platform"

    def _get_authenticated_headers(self) -> Dict[str, str]:
        """Gets the necessary headers for authenticated Bungie API requests."""
        token = self.oauth_manager.get_access_token() # Assuming OAuthManager handles token refresh
        if not token:
            raise Exception("User not authenticated or token expired")
        
        return {
            "Authorization": f"Bearer {token}",
            "X-API-Key": self.oauth_manager.client_secret # Assuming client_secret holds the API key
        }

    def get_membership_info(self) -> Optional[Dict[str, Any]]:
        """Gets the user's primary Destiny membership ID and type."""
        headers = self._get_authenticated_headers()
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

    def get_all_weapons(self, membership_type: int, membership_id: str) -> List[Dict[str, Any]]:
        """
        Fetches all item instances for a given user across characters and vault.
        Currently returns basic info, processing for weapon specifics is pending.
        """
        headers = self._get_authenticated_headers()
        # Components: 
        # 102=ProfileInventories (Vault), 201=CharacterInventories, 205=CharacterEquipment
        # 300=ItemInstances
        # Reduced components for now, add sockets/perks/stats later
        components = "102,201,205,300" 
        url = f"{self.base_url}/Destiny2/{membership_type}/Profile/{membership_id}/?components={components}"
        
        processed_items = []
        
        try:
            logger.info(f"Fetching profile data for {membership_type}/{membership_id} with components {components}")
            response = requests.get(url, headers=headers)
            response.raise_for_status()
            profile_data = response.json()

            if profile_data['ErrorCode'] != 1:
                logger.error(f"Bungie API Error fetching profile: {profile_data.get('Message', 'Unknown error')}")
                raise Exception(f"Bungie API Error: {profile_data.get('Message', 'Failed to fetch profile')}")

            profile = profile_data['Response']
            item_components_instances = profile.get('itemComponents', {}).get('instances', {}).get('data', {})
            logger.info(f"Successfully fetched profile data. Found {len(item_components_instances)} item instances.")

            # 1. Process Vault Items
            vault_items = profile.get('profileInventory', {}).get('data', {}).get('items', [])
            logger.info(f"Processing {len(vault_items)} vault items...")
            for item in vault_items:
                instance_id = item.get('itemInstanceId')
                if instance_id:
                    instance_data = item_components_instances.get(instance_id, {})
                    processed_item = {
                        "item_hash": item.get('itemHash'),
                        "instance_id": instance_id,
                        "location": "vault",
                        "is_equipped": False,
                        "damage_type": instance_data.get('damageType'),
                        # Add more fields as needed later
                    }
                    processed_items.append(processed_item)

            # 2. Process Character Inventories
            character_inventories = profile.get('characterInventories', {}).get('data', {})
            logger.info(f"Processing inventories for {len(character_inventories)} characters...")
            for char_id, inventory in character_inventories.items():
                for item in inventory.get('items', []):
                    instance_id = item.get('itemInstanceId')
                    if instance_id:
                        instance_data = item_components_instances.get(instance_id, {})
                        processed_item = {
                            "item_hash": item.get('itemHash'),
                            "instance_id": instance_id,
                            "location": f"inventory_{char_id}",
                            "is_equipped": False,
                            "damage_type": instance_data.get('damageType'),
                        }
                        processed_items.append(processed_item)

            # 3. Process Character Equipment
            character_equipment = profile.get('characterEquipment', {}).get('data', {})
            logger.info(f"Processing equipment for {len(character_equipment)} characters...")
            for char_id, equipment in character_equipment.items():
                for item in equipment.get('items', []):
                    instance_id = item.get('itemInstanceId')
                    if instance_id:
                        instance_data = item_components_instances.get(instance_id, {})
                        processed_item = {
                            "item_hash": item.get('itemHash'),
                            "instance_id": instance_id,
                            "location": f"equipped_{char_id}",
                            "is_equipped": True,
                            "damage_type": instance_data.get('damageType'),
                        }
                        processed_items.append(processed_item)
            
            logger.info(f"Finished processing. Found {len(processed_items)} items with instance IDs.")
            
            # TODO: Filter for weapons using Manifest lookups
            # TODO: Add static data (name, icon, type) using Manifest lookups
            # TODO: Add sockets, perks, stats using more components and Manifest lookups
            
            return processed_items # Return the list of processed items

        except requests.exceptions.RequestException as e:
            logger.error(f"HTTP Error fetching profile data: {e}", exc_info=True)
            raise Exception("Failed to fetch profile data from Bungie API") from e
        except Exception as e:
            logger.error(f"Error processing profile data: {e}", exc_info=True)
            raise Exception("An error occurred while processing profile data") from e

# Example usage (for testing standalone if needed)
if __name__ == '__main__':
    # This part would require setting up a dummy OAuthManager or actual credentials
    # and is primarily for demonstrating the structure.
    print("WeaponAPI module loaded. Run within the FastAPI app context.") 