import os
import sys
import logging
import json
from itertools import chain

from dotenv import load_dotenv
from supabase import create_client, Client
from supabase.lib.client_options import ClientOptions

# --- Ensure project root is on path ----------------------------------------------------
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

# Local imports AFTER path tweak ---------------------------------------------------------
from web_app.backend.manifest import SupabaseManifestService
from web_app.backend.bungie_oauth import OAuthManager
from web_app.backend.weapon_api import WeaponAPI, ITEM_TYPE_WEAPON, DAMAGE_TYPE_MAP
from web_app.backend.models import Weapon, WeaponPerkDetail
# TODO: Ensure classify_weapon_roll.py exists in web_app/backend/ and uncomment
# from web_app.backend.classify_weapon_roll import classify_weapon_roll 
from web_app.backend.dim_socket_hashes import (
    COL1_CATEGORIES,          # barrels / scopes / bowstrings
    COL2_CATEGORIES,          # magazines / batteries / guards
    COL3_TRAIT_CATEGORIES,    # first perk column (used for both col3 and col4 for now)
    # COL4_TRAIT_CATEGORIES,    # Usually same as COL3_TRAIT_CATEGORIES
    ORIGIN_TRAIT_CATEGORIES,
    # INTRINSIC_TRAIT_CATEGORIES, # Not directly used in Supabase weapon structure aTM
    PlugCategoryHashes       # For any direct PCI checks if needed
) # Import necessary category hashes
from datetime import datetime, timezone # For last_updated timestamp

# ---------------------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------
# Environment & Supabase client helpers
# ---------------------------------------------------------------------------------------
def main():
    env_path = os.path.join(project_root, ".env")
    logger.info(f"Attempting to load .env from: {env_path}")
    loaded = load_dotenv(dotenv_path=env_path)
    if not loaded:
        logger.warning(f".env file NOT loaded successfully from {env_path}. Check path and permissions.")

    SUPABASE_URL = os.getenv("SUPABASE_URL")
    SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    if not SUPABASE_URL or not SUPABASE_KEY:
        logger.error(f"Missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY in environment. Please check your .env file at {env_path}.")
        sys.exit(1)
    
    sb_client = create_client(SUPABASE_URL, SUPABASE_KEY, options=ClientOptions(schema="public"))
    manifest_service = SupabaseManifestService(sb_client=sb_client)
    oauth_manager = OAuthManager()
    weapon_api = WeaponAPI(oauth_manager, manifest_service)
    
    membership_info = weapon_api.get_membership_info()
    if not membership_info:
        logger.error("Could not get membership info. Make sure you are authenticated.")
        sys.exit(1)
    membership_type = membership_info['type']
    destiny_membership_id = membership_info['id']

    logger.info(f"Fetching profile response for user {destiny_membership_id}...")
    # Fetch raw profile data
    # Components: 102=ProfileInventories, 201=CharacterInventories, 205=CharacterEquipment, 300=ItemSockets, 305=ItemPlugObjectives
    profile_data = weapon_api.get_profile_response(membership_type, destiny_membership_id, [102, 201, 205, 300, 305])

    if not profile_data or "Response" not in profile_data:
        logger.error("Failed to get profile data or Response key missing.")
        return
    
    response_data = profile_data["Response"]
    item_sockets_component_data = response_data.get("itemComponents", {}).get("sockets", {}).get("data", {})

    target_weapon_item_hash = None
    target_weapon_instance_id = None
    weapon_item_definition = None
    raw_instance_sockets_list = []
    first_weapon_api_item_data = None # To store the item_data for the first weapon
    location_string = "Unknown"
    is_equipped_bool = False
    
    found_weapon_count = 0
    character_data = response_data.get("characters", {}).get("data", {})

    # Construct a list of all items to scan: character equipment, character inventories, profile inventory
    # And determine location/equipped status when the target weapon is found
    items_to_scan_with_location = []
    if response_data.get("characterEquipment", {}).get("data"):
        for char_id, char_equip in response_data["characterEquipment"]["data"].items():
            char_name = character_data.get(char_id,{}).get("characterClassResolved","Character")
            for item_data in char_equip.get("items", []):
                items_to_scan_with_location.append((item_data, f"Equipped ({char_name})", True))
    
    if response_data.get("characterInventories", {}).get("data"):
        for char_id, char_inv in response_data["characterInventories"]["data"].items():
            char_name = character_data.get(char_id,{}).get("characterClassResolved","Character")
            for item_data in char_inv.get("items", []):
                items_to_scan_with_location.append((item_data, f"Inventory ({char_name})", False))

    if response_data.get("profileInventory", {}).get("data"): # Vault
        for item_data in response_data["profileInventory"]["data"].get("items", []):
            items_to_scan_with_location.append((item_data, "Vault", False))

    logger.info(f"Scanning {len(items_to_scan_with_location)} total items from profile for the first weapon...")

    for item_data, loc_str, is_eqp in items_to_scan_with_location:
        current_item_hash = item_data.get("itemHash")
        if not current_item_hash:
            continue

        item_def = manifest_service.get_definition("DestinyInventoryItemDefinition", current_item_hash)

        if item_def and item_def.get('itemType') == ITEM_TYPE_WEAPON:
            target_weapon_item_hash = current_item_hash
            target_weapon_instance_id = item_data.get("itemInstanceId")
            weapon_item_definition = item_def 
            first_weapon_api_item_data = item_data # Store the raw item_data for power level etc.
            location_string = loc_str
            is_equipped_bool = is_eqp
            
            weapon_name = weapon_item_definition.get('displayProperties', {}).get('name', 'Unknown Weapon')
            logger.info(f"Found first weapon: {weapon_name} (Hash: {target_weapon_item_hash}, Instance ID: {target_weapon_instance_id}, Location: {location_string})")

            if target_weapon_instance_id:
                instance_sockets_data = item_sockets_component_data.get(str(target_weapon_instance_id))
                if instance_sockets_data:
                    raw_instance_sockets_list = instance_sockets_data.get("sockets", [])
                else:
                    logger.warning(f"No instance socket data in itemComponents.sockets for instance ID {target_weapon_instance_id}")
            else:
                logger.warning(f"Weapon {weapon_name} (Hash: {target_weapon_item_hash}) does not have an instance ID. This might be a non-instanced weapon or an issue.")
            
            found_weapon_count += 1
            break 
    
    if not target_weapon_item_hash or not weapon_item_definition or not first_weapon_api_item_data:
        logger.error("No weapon found in the scanned inventories, or missing critical data for it.")
        return

    # --- Gather ALL relevant plug hashes for THIS FIRST WEAPON\'S potential rolls ---
    all_relevant_plug_hashes = set()

    # 1. From the weapon\'s static definition\'s socketEntries (singleInitialItemHash, reusablePlugItems)
    for se_def in weapon_item_definition.get("sockets", {}).get("socketEntries", []):
        if se_def.get("singleInitialItemHash"):
            all_relevant_plug_hashes.add(se_def["singleInitialItemHash"])
        for reusable_item in se_def.get("reusablePlugItems", []):
            if reusable_item.get("plugItemHash"):
                all_relevant_plug_hashes.add(reusable_item["plugItemHash"])
    
    # 2. From Plug Sets referenced in the weapon\'s static definition
    plug_set_hashes_to_fetch = set()
    for se_def in weapon_item_definition.get("sockets", {}).get("socketEntries", []):
        if se_def.get("randomizedPlugSetHash"):
            plug_set_hashes_to_fetch.add(se_def["randomizedPlugSetHash"])
        if se_def.get("reusablePlugSetHash"): # Though typically randomizedPlugSetHash is used for rolls
            plug_set_hashes_to_fetch.add(se_def["reusablePlugSetHash"]) 
    
    plug_set_definitions = {}
    valid_plug_set_hashes = [psh for psh in plug_set_hashes_to_fetch if psh] # Filter out None or 0 if any

    if valid_plug_set_hashes:
        logger.info(f"Fetching {len(valid_plug_set_hashes)} plug set definitions for this weapon...")
        plug_set_definitions = manifest_service.get_definitions_batch("DestinyPlugSetDefinition", valid_plug_set_hashes)
        for plug_set_hash, plug_set_def_data in plug_set_definitions.items():
            if plug_set_def_data and 'reusablePlugItems' in plug_set_def_data:
                for plug_item in plug_set_def_data['reusablePlugItems']:
                    if plug_item.get('plugItemHash'):
                        all_relevant_plug_hashes.add(plug_item['plugItemHash'])
            elif plug_set_def_data is None: # Explicitly check for None if get_definitions_batch can return that for failed lookups
                logger.warning(f"Plug set definition for hash {plug_set_hash} was not found (returned None).")
            else: # Exists but malformed or missing reusablePlugItems
                logger.warning(f"Plug set definition for hash {plug_set_hash} was empty or missing reusablePlugItems: {plug_set_def_data}")
    else:
        logger.info("No valid plug set hashes found to fetch for this weapon.")


    # 3. From the equipped plugs on the specific weapon instance (already in raw_instance_sockets_list)
    # This is important for ensuring currently equipped (but perhaps not in static/plug-set lists) are included
    for socket_data in raw_instance_sockets_list:
        if socket_data.get("plugHash"):
            all_relevant_plug_hashes.add(socket_data["plugHash"])
    
    logger.info(f"Collected {len(all_relevant_plug_hashes)} unique plug hashes for potential rolls of the first weapon.")

    # --- Fetch definitions for ALL these relevant plug items ---
    all_plug_definitions = {}
    valid_plug_hashes_list = [ph for ph in all_relevant_plug_hashes if ph] # Filter out None or 0

    if valid_plug_hashes_list:
        logger.info(f"Fetching definitions for {len(valid_plug_hashes_list)} relevant plug items...")
        all_plug_definitions = manifest_service.get_definitions_batch("DestinyInventoryItemDefinition", valid_plug_hashes_list)
        logger.info(f"Successfully fetched {len(all_plug_definitions)} plug item definitions.")
        # Log if some definitions were not found
        if len(all_plug_definitions) < len(valid_plug_hashes_list):
            missing_hashes = set(valid_plug_hashes_list) - set(all_plug_definitions.keys())
            logger.warning(f"Could not fetch definitions for {len(missing_hashes)} plug hashes: {missing_hashes}")
    else:
        logger.warning("No relevant plug hashes found to fetch definitions for the first weapon.")

    # --- Classify the roll using all collected data for the first weapon ---
    weapon_display_name = weapon_item_definition.get('displayProperties', {}).get('name', f"Weapon Hash {target_weapon_item_hash}")
    logger.info(f"Classifying roll for: {weapon_display_name}")
    
    # TODO: Uncomment when classify_weapon_roll is available
    # classified_roll = classify_weapon_roll(
    #     weapon_hash=target_weapon_item_hash,
    #     manifest_defs=all_plug_definitions, 
    #     instance_sockets_list=raw_instance_sockets_list, 
    #     weapon_definition=weapon_item_definition, 
    #     plug_set_definitions=plug_set_definitions 
    # )
    
    # --- Prepare data for Supabase-like JSON output ---
    equipped_barrel_perks = []
    equipped_magazine_perks = []
    equipped_trait_perk_col1 = []
    equipped_trait_perk_col2 = []
    equipped_origin_trait = None
    # processed_equipped_trait_socket_indexes = set() # No longer needed for this simplified equipped perk logic

    # Lists to store the hashes of plugs found in categorized sockets (for debugging)
    categorized_barrel_socket_plug_hashes = []
    categorized_magazine_socket_plug_hashes = []
    categorized_trait_col1_socket_plug_hashes = [] # Based on socket category
    categorized_trait_col2_socket_plug_hashes = [] # Based on socket category
    categorized_origin_trait_socket_plug_hashes = []
    processed_categorized_trait_socket_indexes = set()

    # First, populate the _hashes_list based on socket categories from weapon_definition
    # This helps see what plug is in a socket that *should* be a barrel, mag, etc.
    if raw_instance_sockets_list and weapon_item_definition:
        socket_categories_from_def = weapon_item_definition.get("sockets", {}).get("socketCategories", [])
        equipped_plugs_map_by_index = { 
            idx: s.get("plugHash") for idx, s in enumerate(raw_instance_sockets_list) 
            if s.get("plugHash") and s.get("isEnabled", False)
        }
        for category_def in socket_categories_from_def:
            category_hash = category_def.get("socketCategoryHash")
            socket_indexes_in_category = category_def.get("socketIndexes", [])
            for socket_idx in socket_indexes_in_category:
                plug_hash = equipped_plugs_map_by_index.get(socket_idx)
                if not plug_hash: continue

                if category_hash in COL1_CATEGORIES:
                    categorized_barrel_socket_plug_hashes.append(plug_hash)
                elif category_hash in COL2_CATEGORIES:
                    categorized_magazine_socket_plug_hashes.append(plug_hash)
                elif category_hash in ORIGIN_TRAIT_CATEGORIES:
                    categorized_origin_trait_socket_plug_hashes.append(plug_hash)
                elif category_hash in COL3_TRAIT_CATEGORIES: # Covers both trait columns
                    if socket_idx not in processed_categorized_trait_socket_indexes:
                        if not categorized_trait_col1_socket_plug_hashes: 
                            categorized_trait_col1_socket_plug_hashes.append(plug_hash)
                            processed_categorized_trait_socket_indexes.add(socket_idx)
                        elif not categorized_trait_col2_socket_plug_hashes:
                            categorized_trait_col2_socket_plug_hashes.append(plug_hash)
                            processed_categorized_trait_socket_indexes.add(socket_idx)
    
    # Now, iterate through equipped plugs and classify them using their own itemTypeDisplayName
    temp_trait_list_for_sorting = []

    for socket_data in raw_instance_sockets_list:
        plug_hash = socket_data.get("plugHash")
        if not plug_hash or not socket_data.get("isEnabled", False):
            continue

        plug_def = all_plug_definitions.get(plug_hash)
        if not plug_def:
            logger.warning(f"Definition missing for actively equipped plugHash {plug_hash}. Skipping for Supabase output.")
            continue

        plug_display_props = plug_def.get("displayProperties", {})
        perk_name = plug_display_props.get("name")
        perk_description = plug_display_props.get("description", "")
        perk_icon_path = plug_display_props.get("icon", "")
        perk_icon_url = f"https://www.bungie.net{perk_icon_path}" if perk_icon_path else "https://www.bungie.net/common/destiny2_content/icons/broken_icon.png"
        item_type_display_name_from_plug = plug_def.get("itemTypeDisplayName", "")

        # Filter out shaders, empty sockets, etc., by name or PCI if needed more robustly
        # For now, primarily relying on itemTypeDisplayName for sorting equipped perks
        if not perk_name or "shader" in plug_def.get("plug",{}).get("plugCategoryIdentifier"," ").lower() or "empty" in perk_name.lower() or "default" in perk_name.lower():
            if perk_name and "Empty Mod Socket" not in perk_name and "Default Shader" not in perk_name: # Log if it's not a common filtered item
                 logger.info(f"Filtered out plug by name/pci: {perk_name} (Hash: {plug_hash})")
            continue
        
        perk_detail_dict = {
            "perk_hash": plug_hash,
            "name": perk_name,
            "description": perk_description,
            "icon_url": perk_icon_url
        }

        if item_type_display_name_from_plug == "Barrel":
            equipped_barrel_perks.append(perk_detail_dict)
        elif item_type_display_name_from_plug == "Magazine":
            equipped_magazine_perks.append(perk_detail_dict)
        elif item_type_display_name_from_plug == "Origin Trait":
            if not equipped_origin_trait: # Take the first one
                equipped_origin_trait = perk_detail_dict
        elif item_type_display_name_from_plug == "Trait":
            temp_trait_list_for_sorting.append(perk_detail_dict)
        # else: 
            # logger.info(f"Plug {perk_name} (Hash: {plug_hash}) with itemTypeDisplayName '{item_type_display_name_from_plug}' not categorized for equipped perks.")

    # Sort traits into col1 and col2 based on encounter order
    if temp_trait_list_for_sorting:
        equipped_trait_perk_col1.append(temp_trait_list_for_sorting[0])
        if len(temp_trait_list_for_sorting) > 1:
            equipped_trait_perk_col2.append(temp_trait_list_for_sorting[1])
        # If more than 2 traits, others are ignored for this simplified equipped view
        if len(temp_trait_list_for_sorting) > 2:
            logger.warning(f"Weapon instance has {len(temp_trait_list_for_sorting)} equipped plugs with itemTypeDisplayName 'Trait'. Storing first two.")

    supabase_weapon_data = {
        "user_id": str(destiny_membership_id),
        "item_instance_id": str(target_weapon_instance_id) if target_weapon_instance_id else None,
        "item_hash": target_weapon_item_hash,
        "name": weapon_item_definition.get('displayProperties', {}).get('name', 'Unknown Weapon'),
        "icon_url": "https://www.bungie.net" + weapon_item_definition.get('displayProperties', {}).get('icon', '') if weapon_item_definition.get('displayProperties', {}).get('icon') else None,
        "tier_type": weapon_item_definition.get('inventory', {}).get('tierTypeName', 'Unknown'),
        "item_type_display_name": weapon_item_definition.get('itemTypeDisplayName', 'Unknown Weapon Type'),
        "damage_type": DAMAGE_TYPE_MAP.get(weapon_item_definition.get("defaultDamageType", 0), "Unknown"),
        "power_level": first_weapon_api_item_data.get("primaryStat", {}).get("value") if first_weapon_api_item_data else None,
        "location": location_string,
        "is_equipped": is_equipped_bool,
        "barrel_perks": equipped_barrel_perks,
        "magazine_perks": equipped_magazine_perks,
        "trait_perk_col1": equipped_trait_perk_col1,
        "trait_perk_col2": equipped_trait_perk_col2,
        "origin_trait": equipped_origin_trait,
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "categorized_barrel_socket_plug_hashes": categorized_barrel_socket_plug_hashes,
        "categorized_magazine_socket_plug_hashes": categorized_magazine_socket_plug_hashes,
        "categorized_trait_col1_socket_plug_hashes": categorized_trait_col1_socket_plug_hashes,
        "categorized_trait_col2_socket_plug_hashes": categorized_trait_col2_socket_plug_hashes,
        "categorized_origin_trait_socket_plug_hashes": categorized_origin_trait_socket_plug_hashes
    }

    print("\n==== SUPABASE-LIKE WEAPON DATA FOR FIRST WEAPON ====")
    try:
        print(json.dumps(supabase_weapon_data, indent=2))
    except TypeError as e:
        logger.error(f"Could not serialize supabase_weapon_data to JSON: {e}. Printing as dict.")
        print(supabase_weapon_data)

    # TODO: Uncomment when classify_weapon_roll is available and provides classified_roll
    # print("\n==== STRUCTURED ROLL OUTPUT FOR FIRST WEAPON ====")

    # --- Write instance-specific data to a debug file ---
    if target_weapon_item_hash and first_weapon_api_item_data and weapon_item_definition.get('displayProperties', {}).get('name', 'Unknown Weapon') == "Adamantite":
        # Ensure the debug file is saved in the same directory as the script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        debug_output_filename = os.path.join(script_dir, "adamantite_instance_debug_data.json")
        
        instance_debug_data = {
            "instance_item_data": first_weapon_api_item_data,
            "instance_sockets_list": raw_instance_sockets_list
        }
        try:
            with open(debug_output_filename, 'w') as f:
                json.dump(instance_debug_data, f, indent=2)
            logger.info(f"Wrote instance debug data for Adamantite to {debug_output_filename}")
        except Exception as e:
            logger.error(f"Failed to write Adamantite instance debug data: {e}")

    logger.info("Script finished processing the first weapon.")

if __name__ == "__main__":
    main()
