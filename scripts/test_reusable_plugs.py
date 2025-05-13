print("[DEBUG] Script started")

import os
import sys
import json
from dotenv import load_dotenv
from supabase import create_client

# Adjust sys.path to include the project root
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(SCRIPT_DIR, os.pardir))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from web_app.backend.weapon_api import WeaponAPI 
from web_app.backend.manifest import SupabaseManifestService 
from web_app.backend.bungie_oauth import OAuthManager

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY") 

sb_client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
manifest_service = SupabaseManifestService(sb_client=sb_client)
oauth_manager = OAuthManager()
weapon_api = WeaponAPI(oauth_manager=oauth_manager, manifest_service=manifest_service)

print("[DEBUG] Entered main logic")

try:
    membership_info = weapon_api.get_membership_info()
    print(f"[DEBUG] membership_info: {membership_info}")
    membership_type = membership_info["type"]
    destiny_membership_id = membership_info["id"]

    # Only fetch minimal components for reusablePlugs
    components = [102, 201, 205, 310]
    profile_response = weapon_api.get_profile_response(
        membership_type=membership_type,
        destiny_membership_id=destiny_membership_id,
        components=components
    )
    # Define your PCI/category mappings
    PCI_COL1 = {"barrels", "tubes", "bowstrings", "blades", "hafts", "scopes"}
    PCI_COL2 = {"magazines", "batteries", "guards", "arrows"}
    TRAIT_PCI = {"frames", "grips", "traits"}
    ORIGIN_PCI = {"origin"}
    MASTERWORK_PCI = {"masterworks"}

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
        elif 'masterworks' in pci and name.startswith('Masterworked:'):
            return "masterwork"
        elif "shader" in pci:
            return "shader"
        elif "weapon.mod_guns" in pci or "weapon mod" in item_type_display_name:
            return "weapon_mod"
        else:
            return "other"
    # print(f"[DEBUG] ErrorCode: {profile_response.get('ErrorCode')}, ErrorStatus: {profile_response.get('ErrorStatus')}, Message: {profile_response.get('Message')}")
    # print(f"[DEBUG] profile_response keys: {list(profile_response.keys())}")

    reusable_plugs_data = profile_response.get("Response", {}).get("itemComponents", {}).get("reusablePlugs", {}).get("data", {})
    # reusable_plugs_data.keys() are the instance_ids
    # print(json.dumps(reusable_plugs_data, indent=2))
    # print(f"[DEBUG] reusable_plugs_data keys: {list(reusable_plugs_data.keys())} (count: {len(reusable_plugs_data)})")
    if len(reusable_plugs_data) > 0:
        print(f"found {len(reusable_plugs_data)} instances")
        # first_key = next(iter(reusable_plugs_data))
        # print(f"[DEBUG] Sample reusable_plugs_data[{first_key}]: {json.dumps(reusable_plugs_data[first_key], indent=2)}")

    # For each instance, print the plug hashes for each socket
    N = 5  # or whatever number you want
    for instance_id in list(reusable_plugs_data.keys())[:N]:
        print(f"\nInstance {instance_id}:")
        instance_reusable_plugs = reusable_plugs_data.get(instance_id, {}).get('plugs', {}  )
        socket_plug_hashes = {}
        for plug in instance_reusable_plugs:
            # print(plug)
            plug_hashes = instance_reusable_plugs.get(plug, [])
            # print(plug_hashes)
            # iplug = instance_reusable_plugs.get(plug, [])
            plug_item_hashes = [plug_hash['plugItemHash'] for plug_hash in plug_hashes]
            # print(plug_item_hashes)
            socket_plug_hashes[plug] = plug_item_hashes

            all_plug_hashes = set()
            for plug_list in socket_plug_hashes.values():
                all_plug_hashes.update(plug_list)

            # 2. Batch fetch all plug definitions
            plug_definitions = manifest_service.get_definitions_batch(
                'DestinyInventoryItemDefinition',
                list(all_plug_hashes)
            )

            socket_plug_defs = {}
            for socket_index, plug_hashes in socket_plug_hashes.items():
                socket_plug_defs[socket_index] = [
                    plug_definitions.get(plug_hash) for plug_hash in plug_hashes if plug_definitions.get(plug_hash)
                ]

            # Assuming socket_plug_defs is already built as described earlier
            for socket_index, plug_defs in socket_plug_defs.items():
                plug_names = [plug_def['displayProperties']['name'] for plug_def in plug_defs if plug_def]
                print(f"Socket {socket_index}: {plug_names}")
            
            # 1. Identify all trait sockets (by your PCI logic or however you already do it)
            trait_socket_indexes = []
            for socket_index, plug_defs in socket_plug_defs.items():
                # If any plug in this socket is a trait, consider this a trait socket
                if any(get_plug_category(plug_def) == "trait" for plug_def in plug_defs if plug_def):
                    trait_socket_indexes.append(socket_index)

            # 2. Sort trait sockets for consistent ordering
            trait_socket_indexes = sorted(trait_socket_indexes)

            # 3. Print with col3_trait1/col4_trait2 labels
            for socket_index, plug_defs in socket_plug_defs.items():
                for plug_def in plug_defs:
                    if not plug_def:
                        continue
                    name = plug_def['displayProperties']['name']
                    category = get_plug_category(plug_def)
                    item_hash = plug_def.get('hash')
                    # Determine trait column label if this is a trait
                    if category == "trait":
                        if socket_index == trait_socket_indexes[0]:
                            trait_label = "col3_trait1"
                        elif len(trait_socket_indexes) > 1 and socket_index == trait_socket_indexes[1]:
                            trait_label = "col4_trait2"
                        else:
                            trait_label = "trait"
                        print(f"Socket {socket_index}: {name} (hash: {item_hash}) -> {trait_label}")
                    else:
                        print(f"Socket {socket_index}: {name} (hash: {item_hash}) -> {category}")
    # Optionally, batch fetch and print plug names for a specific instance/socket
    # (Uncomment below to test for a specific instance)
    # all_plug_hashes = set()
    # for sockets in reusable_plugs_data.values():
    #     for plugs in sockets.values():
    #         for plug in plugs:
    #             if plug.get("plugItemHash"):
    #                 all_plug_hashes.add(plug["plugItemHash"])
    # plug_defs = manifest_service.get_definitions_batch('DestinyInventoryItemDefinition', list(all_plug_hashes))
    # for plug_hash in all_plug_hashes:
    #     plug_def = plug_defs.get(plug_hash)
    #     if plug_def:
    #         print(f"{plug_hash}: {plug_def['displayProperties']['name']}")
except Exception as e:
    print(f"[ERROR] Exception occurred: {e}")