import asyncio
import logging
import os
import sys
import json
from pprint import pprint
from dotenv import load_dotenv
from datetime import datetime
from supabase import create_client

# --- Debug: Print current working directory ---
# print(f"Current Working Directory: {os.getcwd()}")
# --- End Debug ---

# Adjust sys.path to include the project root
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))

if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT) # Ensure it's at the beginning

# --- Debug: Print sys.path to see what Python is using ---
# print("--- sys.path after modification ---")
# for p in sys.path:
#     print(p)
# print("-----------------------------------")
# --- End Debug ---

from web_app.backend.weapon_api import WeaponAPI 
from web_app.backend.manifest import SupabaseManifestService 
from web_app.backend.bungie_oauth import OAuthManager # IMPORT OAuthManager

# Configure logging
logging.basicConfig(level=logging.WARNING, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv()

BUNGIE_API_KEY = os.getenv("BUNGIE_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
# Use SUPABASE_SERVICE_ROLE_KEY as per user's .env content
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") 
BUNGIE_ACCESS_TOKEN = os.getenv("BUNGIE_ACCESS_TOKEN")

async def main():
    if not all([BUNGIE_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, BUNGIE_ACCESS_TOKEN]):
        logger.error("Missing one or more critical environment variables. Check BUNGIE_API_KEY, SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY, BUNGIE_ACCESS_TOKEN.")
        return

    # Create Supabase client and pass to manifest service
    sb_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    manifest_service = SupabaseManifestService(sb_client=sb_client)
    oauth_manager = OAuthManager() 
    weapon_api = WeaponAPI( 
        oauth_manager=oauth_manager, 
        manifest_service=manifest_service
    )

    # Dynamically fetch membership info
    membership_info = weapon_api.get_membership_info()
    if not membership_info:
        logger.error("Could not fetch membership info from Bungie API. Make sure your OAuth token is valid.")
        return
    membership_type = membership_info["type"]
    destiny_membership_id = membership_info["id"]
    logger.info(f"Fetched membership_type={membership_type}, destiny_membership_id={destiny_membership_id}")

    # Fetch two separate responses
    components_reusable = [102, 201, 205, 310]
    components_other = [102, 201, 205, 300, 301, 302, 304, 306, 307, 308, 309, 310]
    profile_response_reusable = weapon_api.get_profile_response(
        membership_type=membership_type,
        destiny_membership_id=destiny_membership_id,
        components=components_reusable
    )
    profile_response_other = weapon_api.get_profile_response(
        membership_type=membership_type,
        destiny_membership_id=destiny_membership_id,
        components=components_other
    )
    if not profile_response_reusable or not profile_response_other:
        logger.error("Failed to get profile response data from WeaponAPI.")
        return

    # Flatten all items (from the 'other' response, which has all items)
    character_equipment_data = profile_response_other.get("Response", {}).get("characterEquipment", {})
    character_inventories_data = profile_response_other.get("Response", {}).get("characterInventories", {})
    profile_inventory_data = profile_response_other.get("Response", {}).get("profileInventory", {})

    all_items_from_profile = []
    if character_equipment_data.get("data"):
        for equip_data in character_equipment_data["data"].values():
            all_items_from_profile.extend(equip_data.get('items', []))
    if character_inventories_data.get("data"):
        for inv_data in character_inventories_data["data"].values():
            all_items_from_profile.extend(inv_data.get('items', []))
    if profile_inventory_data.get("data"): 
        all_items_from_profile.extend(profile_inventory_data["data"].get('items', []))
    
    if not all_items_from_profile:
        logger.error("No items found in profile character equipment, inventories, or profile inventory.")
        return
    logger.info(f"Found {len(all_items_from_profile)} items in total from profile.")

    # --- Step 1: Build a mapping of instance_id -> {socket_index: [plug_hash, ...]} ---
    reusable_plugs_data = profile_response_reusable.get("Response", {}).get("itemComponents", {}).get("reusablePlugs", {}).get("data", {})
    # print(f"[DEBUG] reusable_plugs_data keys: {list(reusable_plugs_data.keys())} (count: {len(reusable_plugs_data)})")
    # if len(reusable_plugs_data) > 0:
    #     first_key = next(iter(reusable_plugs_data))
    #     print(f"[DEBUG] Sample reusable_plugs_data[{first_key}]: {json.dumps(reusable_plugs_data[first_key], indent=2)}")
    instance_socket_plug_hashes = {}
    all_plug_hashes = set()
    for item in all_items_from_profile:
        instance_id = item.get('itemInstanceId')
        if not instance_id:
            continue
        
        instance_component_data = reusable_plugs_data.get(instance_id, {}) # This is the value for the instance_id key from reusablePlugs.data
        instance_sockets_dict = instance_component_data.get('plugs', {})  # Get the nested 'plugs' dictionary
        # print(f"[DEBUG] Processing instance_id: {instance_id} - Found actual sockets dict: {bool(instance_sockets_dict)}")
        
        socket_plug_hashes = {}
        # Now iterate over the actual sockets dictionary
        for socket_index_str, plug_object_list in instance_sockets_dict.items():
            # plug_object_list is a list of dictionaries, each representing a plug
            plug_hashes = [p.get("plugItemHash") for p in plug_object_list if p and p.get("plugItemHash")]
            socket_plug_hashes[int(socket_index_str)] = plug_hashes
            all_plug_hashes.update(plug_hashes)
        instance_socket_plug_hashes[instance_id] = socket_plug_hashes

    # --- Step 2: Batch fetch all plug definitions ---
    plug_definitions = manifest_service.get_definitions_batch(
        'DestinyInventoryItemDefinition',
        list(all_plug_hashes)
    )

    # --- Step 3: For each weapon, classify plugs and build output ---
    PCI_COL1 = {"barrels", "tubes", "bowstrings", "blades", "hafts", "scopes"}
    PCI_COL2 = {"magazines", "batteries", "guards", "arrows"}
    TRAIT_PCI = {"frames", "grips", "traits"}
    ORIGIN_PCI = {"origin"}

    def get_plug_category(plug_def):
        pci = plug_def.get('plug', {}).get('plugCategoryIdentifier', '').lower()
        name = plug_def.get('displayProperties', {}).get('name', '')
        item_type_display_name = plug_def.get('itemTypeDisplayName', '').lower()
        if any(key in pci for key in PCI_COL1):
            return "col1_barrel"
        elif any(key in pci for key in PCI_COL2):
            return "col2_magazine"
        elif any(key in pci for key in TRAIT_PCI) or plug_def.get('itemTypeDisplayName') in ("Trait", "Enhanced Trait", "Grip"):
            return "trait"
        elif any(key in pci for key in ORIGIN_PCI) or plug_def.get('itemTypeDisplayName') == "Origin Trait":
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

    max_weapons = 10
    processed_count = 0
    for item in all_items_from_profile:
        if processed_count >= max_weapons:
            break
        item_hash = item.get('itemHash')
        instance_id = item.get('itemInstanceId')
        if not instance_id or not item_hash:
            continue
        # Only process weapons
        static_def_item = manifest_service.get_definition('DestinyInventoryItemDefinition', item_hash)
        if not static_def_item or static_def_item.get('itemType') != 3:
            continue

        socket_plug_hashes = instance_socket_plug_hashes.get(instance_id, {})
        socket_plug_defs = {socket_index: [plug_definitions.get(plug_hash) for plug_hash in plug_hashes if plug_definitions.get(plug_hash)] for socket_index, plug_hashes in socket_plug_hashes.items()}

        # Identify trait sockets
        trait_socket_indexes = [idx for idx, plug_defs in socket_plug_defs.items() if any(get_plug_category(plug_def) == "trait" for plug_def in plug_defs if plug_def)]
        trait_socket_indexes = sorted(trait_socket_indexes)

        col1_plugs, col2_plugs, col3_trait1, col4_trait2, origin_trait, masterwork, weapon_mods, shaders = set(), set(), set(), set(), set(), set(), set(), set()
        for socket_index, plug_defs in socket_plug_defs.items():
            for plug_def in plug_defs:
                if not plug_def:
                    continue
                name = plug_def['displayProperties']['name']
                category = get_plug_category(plug_def)
                if category == "col1_barrel":
                    col1_plugs.add(name)
                elif category == "col2_magazine":
                    col2_plugs.add(name)
                elif category == "trait":
                    if trait_socket_indexes and socket_index == trait_socket_indexes[0]:
                        col3_trait1.add(name)
                    elif len(trait_socket_indexes) > 1 and socket_index == trait_socket_indexes[1]:
                        col4_trait2.add(name)
                elif category == "origin_trait":
                    origin_trait.add(name)
                elif category == "masterwork":
                    masterwork.add(name)
                elif category == "weapon_mod":
                    weapon_mods.add(name)
                elif category == "shader":
                    shaders.add(name)
        simplified = {
            "weapon_hash": static_def_item.get("hash"),
            "weapon_name": static_def_item.get("displayProperties", {}).get("name"),
            "weapon_type": static_def_item.get("itemTypeDisplayName"),
            "col1_plugs": sorted(col1_plugs),
            "col2_plugs": sorted(col2_plugs),
            "col3_trait1": sorted(col3_trait1),
            "col4_trait2": sorted(col4_trait2),
            "origin_trait": sorted(origin_trait),
            "masterwork": sorted(masterwork),
            "weapon_mods": sorted(weapon_mods),
            "shaders": sorted(shaders)
        }
        print("\n==== SIMPLIFIED WEAPON JSON ====")
        print(json.dumps(simplified, indent=2, ensure_ascii=False))
        processed_count += 1

if __name__ == "__main__":
    asyncio.run(main())
