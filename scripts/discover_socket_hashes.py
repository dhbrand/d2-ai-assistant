import asyncio
import os
from dotenv import load_dotenv
from supabase import create_client, Client as AsyncClient
from typing import List, Dict, Any, Set
from datetime import datetime

# Load environment variables if you use a .env file for Supabase credentials
# Assuming .env is in the project root, one level up from 'scripts/'
dotenv_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), '.env')
print(f"[DEBUG] Script path: {__file__}")
print(f"[DEBUG] Calculated .env path: {dotenv_path}")

if os.path.exists(dotenv_path):
    print(f"[DEBUG] .env file found at: {dotenv_path}")
    loaded_successfully = load_dotenv(dotenv_path=dotenv_path, override=True) # Added override=True just in case
    print(f"[DEBUG] python-dotenv load_dotenv executed. Variables loaded: {loaded_successfully}")
else:
    print(f"[DEBUG] .env file NOT found at: {dotenv_path}. Environment variables should be set externally.")

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY") # Use service key for direct DB access

print(f"[DEBUG] SUPABASE_URL from os.environ: {SUPABASE_URL}")
print(f"[DEBUG] SUPABASE_KEY from os.environ (first 10 chars): {str(SUPABASE_KEY)[:10] if SUPABASE_KEY else None}")

# --- Configuration --
SAMPLE_WEAPON_ITEM_HASHES: List[int] = [
    860516888,  # Example: The Recluse (SMG) - Verify hash
    # Add other diverse weapon item hashes here (integers only)
    # e.g., 1324559504, # Example: IKELOS_SMG_v1.0.2
    #       362899650,  # Example: CALUS Mini-Tool
]

RANDOM_SAMPLE_COUNT = 20 # Number of random weapons to analyze if SAMPLE_WEAPON_ITEM_HASHES is empty
INITIAL_RANDOM_FETCH_LIMIT = 200 # Fetch a larger pool initially to pick random samples from

WEAPON_DEF_TABLE = "DestinyInventoryItemDefinition"
SOCKET_CATEGORY_DEF_TABLE = "DestinySocketCategoryDefinition"
SOCKET_TYPE_DEF_TABLE = "DestinySocketTypeDefinition" # Not used in current script but good to define
PLUG_DEF_TABLE = "DestinyInventoryItemDefinition"

REPORT_FILE_NAME = "socket_analysis_report.txt"

async def get_supabase_client() -> AsyncClient:
    if not SUPABASE_URL or not SUPABASE_KEY:
        print("Error: SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY environment variables must be set.")
        exit(1)
    # Use the new recommended way for supabase-py-async if applicable
    # For supabase_py_async, create_client is the correct way
    # For official supabase-py, create_client is synchronous.
    supabase: AsyncClient = create_client(SUPABASE_URL, SUPABASE_KEY)
    return supabase

async def fetch_definition(sb_client: AsyncClient, table_name: str, definition_hash: int) -> Dict[str, Any]:
    try:
        response = await sb_client.table(table_name).select("json").eq("id", definition_hash).single().execute()
        if response.data and isinstance(response.data, dict) and 'json' in response.data:
            return response.data['json']
        # print(f"No data or no json key for {definition_hash} in {table_name}. Response: {response.data}")
        return {}
    except Exception as e:
        print(f"Error fetching {definition_hash} from {table_name}: {e}")
        return {}

async def fetch_definitions_batch(sb_client: AsyncClient, table_name: str, hashes: List[int]) -> Dict[int, Dict[str, Any]]:
    definitions: Dict[int, Dict[str, Any]] = {}
    if not hashes:
        return definitions
    try:
        # Assuming 'id' column stores the integer hash.
        response = await sb_client.table(table_name).select("id, json").in_("id", hashes).execute()
        if response.data:
            for record in response.data:
                if isinstance(record, dict) and 'id' in record and 'json' in record:
                    definitions[record['id']] = record['json']
        return definitions
    except Exception as e:
        print(f"Error batch fetching from {table_name} for hashes {hashes}: {e}")
        return {}

async def get_weapon_definitions(sb_client: AsyncClient) -> List[Dict[str, Any]]:
    weapon_defs_to_return: List[Dict[str, Any]] = []
    
    # Prioritize manually specified hashes
    if SAMPLE_WEAPON_ITEM_HASHES:
        print(f"Fetching specific weapon definitions for hashes: {SAMPLE_WEAPON_ITEM_HASHES}")
        # Ensure all provided hashes are integers
        valid_sample_hashes = [h for h in SAMPLE_WEAPON_ITEM_HASHES if isinstance(h, int)]
        if not valid_sample_hashes:
            print("Warning: No valid integer hashes found in SAMPLE_WEAPON_ITEM_HASHES.")
            # Fall through to random sampling or return empty based on preference
            # For now, let's fall through if RANDOM_SAMPLE_COUNT > 0
        else:
            defs_map = await fetch_definitions_batch(sb_client, WEAPON_DEF_TABLE, valid_sample_hashes)
            for weapon_hash in valid_sample_hashes: # Iterate in defined order
                if weapon_hash in defs_map:
                    weapon_json = defs_map[weapon_hash]
                    # Ensure it's a dictionary and itemType is 3 (Weapon)
                    if isinstance(weapon_json, dict) and weapon_json.get('itemType') == 3:
                        weapon_defs_to_return.append(weapon_json)
                    else:
                        print(f"Warning: Hash {weapon_hash} from SAMPLE_WEAPON_ITEM_HASHES is not a weapon or definition is malformed.")
                else:
                    print(f"Warning: Could not fetch definition for weapon hash {weapon_hash} from SAMPLE_WEAPON_ITEM_HASHES.")
            if weapon_defs_to_return: # If we got results from specific hashes, return them
                return weapon_defs_to_return
    
    # If no specific hashes provided or they yielded no results, and random sampling is enabled
    if RANDOM_SAMPLE_COUNT > 0:
        print(f"Fetching up to {INITIAL_RANDOM_FETCH_LIMIT} weapon definitions to select {RANDOM_SAMPLE_COUNT} random samples...")
        try:
            response = await (
                sb_client.table(WEAPON_DEF_TABLE)
                .select("id, json") # Select id (hash) and the json blob
                # No direct .eq("json->>itemType", "3") here, we'll filter in Python after fetch
                # to ensure we get actual weapon items and avoid potential DB-specific JSON query issues.
                .limit(INITIAL_RANDOM_FETCH_LIMIT) 
                .execute()
            )

            if response.data:
                import random
                all_fetched_items = []
                for item_record in response.data:
                    if isinstance(item_record, dict) and 'json' in item_record and isinstance(item_record['json'], dict):
                        item_json = item_record['json']
                        # Robust check for itemType being 3 (Weapon)
                        if item_json.get('itemType') == 3:
                            all_fetched_items.append(item_json)
                
                if not all_fetched_items:
                    print("No weapon items (itemType 3) found in the initial random fetch.")
                    return []

                actual_sample_count = min(len(all_fetched_items), RANDOM_SAMPLE_COUNT)
                if actual_sample_count > 0:
                    print(f"Found {len(all_fetched_items)} total weapons in initial fetch. Taking {actual_sample_count} random samples.")
                    return random.sample(all_fetched_items, actual_sample_count)
                else:
                    print("No weapon items available to sample after filtering.")
                    return []
            else:
                print("No data returned when fetching weapon definitions for random sampling.")
                return []
        except Exception as e:
            print(f"Error fetching random weapon definitions: {e}")
            return []
            
    if not weapon_defs_to_return:
        print("No weapon definitions to analyze (neither specific nor random). Ensure SAMPLE_WEAPON_ITEM_HASHES or RANDOM_SAMPLE_COUNT are set.")
    return weapon_defs_to_return


async def analyze_weapon_sockets(sb_client: AsyncClient, weapon_def: Dict[str, Any], 
                                 socket_category_names: Dict[int, str], 
                                 all_encountered_categories: Dict[int, Dict[str, Any]],
                                 report_file_handle):
    weapon_hash = weapon_def.get('hash')
    weapon_name = weapon_def.get('displayProperties', {}).get('name', f"Unknown Weapon {weapon_hash}")
    
    output_lines = [f"\n--- Analyzing: {weapon_name} (Hash: {weapon_hash}) ---"]

    sockets_data = weapon_def.get('sockets', {})
    socket_entries = sockets_data.get('socketEntries', [])
    socket_categories = sockets_data.get('socketCategories', [])

    if not socket_categories:
        output_lines.append("  No socket categories found for this weapon.")
        report_file_handle.write("\n".join(output_lines) + "\n")
        print(f"Processed: {weapon_name} (No socket categories)") # Keep some terminal feedback
        return

    output_lines.append("  Socket Categories on this Weapon:")
    for category_on_weapon in socket_categories:
        cat_hash = category_on_weapon.get('socketCategoryHash')
        if cat_hash is None:
            continue
            
        cat_name = socket_category_names.get(cat_hash, f"Unknown Category {cat_hash}")
        socket_indexes = category_on_weapon.get('socketIndexes', [])
        output_lines.append(f'    Category: "{cat_name}" (Hash: {cat_hash})')
        output_lines.append(f"      Socket Indexes in this category on this weapon: {socket_indexes}")

        if cat_hash not in all_encountered_categories:
            all_encountered_categories[cat_hash] = {"name": cat_name, "count": 0, "example_plugs": set()}
        all_encountered_categories[cat_hash]["count"] += 1

        plug_hashes_in_category_sockets: Set[int] = set()
        for s_idx in socket_indexes:
            if 0 <= s_idx < len(socket_entries):
                socket_entry = socket_entries[s_idx]
                if not isinstance(socket_entry, dict): continue
                single_initial_item_hash = socket_entry.get('singleInitialItemHash')
                if single_initial_item_hash:
                    plug_hashes_in_category_sockets.add(single_initial_item_hash)
                reusable_plugs = socket_entry.get('reusablePlugItems', [])
                if isinstance(reusable_plugs, list):
                    for plug_item in reusable_plugs:
                        if isinstance(plug_item, dict):
                            plug_hash = plug_item.get('plugItemHash')
                            if plug_hash:
                                plug_hashes_in_category_sockets.add(plug_hash)
        
        if plug_hashes_in_category_sockets:
            output_lines.append(f"      Potential Perks/Plugs found in these sockets (Name & Hash):")
            plug_definitions = await fetch_definitions_batch(sb_client, PLUG_DEF_TABLE, list(plug_hashes_in_category_sockets))
            for plug_hash, plug_def_json in plug_definitions.items():
                if not isinstance(plug_def_json, dict): continue
                plug_name = plug_def_json.get('displayProperties', {}).get('name', f"Unknown Plug {plug_hash}")
                plug_cat_id = plug_def_json.get('plug', {}).get('plugCategoryIdentifier', 'N/A')
                output_lines.append(f'        - "{plug_name}" (PlugHash: {plug_hash}, PlugCatID: {plug_cat_id})')
                if len(all_encountered_categories[cat_hash]["example_plugs"]) < 5:
                     all_encountered_categories[cat_hash]["example_plugs"].add(plug_name)
        else:
            output_lines.append("        - No direct plug items found listed in these socket entries.")
    
    report_file_handle.write("\n".join(output_lines) + "\n")
    print(f"Processed and logged: {weapon_name}") # Terminal feedback


async def main():
    sb_client = await get_supabase_client()

    # Open report file
    with open(REPORT_FILE_NAME, 'w', encoding='utf-8') as report_file:
        report_file.write(f"Destiny 2 Weapon Socket Analysis Report - {datetime.now().strftime('%Y-%m-%d %H:%M:%S' )}\n")
        report_file.write("=".center(80, '=') + "\n")

        print(f"Starting analysis. Detailed report will be saved to: {REPORT_FILE_NAME}")

        print("Fetching all socket category definitions to get names...")
        report_file.write("\nFetching all socket category definitions...\n")
        response = await sb_client.table(SOCKET_CATEGORY_DEF_TABLE).select("id, json").execute()
        socket_category_names: Dict[int, str] = {}
        if response.data:
            for record in response.data:
                if not (isinstance(record, dict) and 'json' in record and isinstance(record['json'], dict)):
                    continue
                cat_json = record['json']
                cat_hash = cat_json.get('hash')
                cat_name = cat_json.get('displayProperties', {}).get('name', f"Unnamed Category {cat_hash}")
                if cat_hash is not None: 
                    socket_category_names[cat_hash] = cat_name
        report_file.write(f"Found {len(socket_category_names)} socket category definitions.\n")
        print(f"Found {len(socket_category_names)} socket category definitions.")

        weapon_definitions = await get_weapon_definitions(sb_client)

        if not weapon_definitions:
            no_defs_message = "No weapon definitions to analyze."
            print(no_defs_message)
            report_file.write(f"\n{no_defs_message}\n")
            return

        report_file.write(f"\nAnalyzing {len(weapon_definitions)} weapon(s)...\n")
        all_encountered_socket_categories: Dict[int, Dict[str, Any]] = {}

        for weapon_def in weapon_definitions:
            if isinstance(weapon_def, dict):
                # Pass the file handle to the analysis function
                await analyze_weapon_sockets(sb_client, weapon_def, socket_category_names, 
                                             all_encountered_socket_categories, report_file)
        
        summary_header = "\n\n--- Summary of All Unique Socket Category Hashes Encountered Across Analyzed Weapons ---"
        print(summary_header)
        report_file.write(summary_header + "\n")
        
        if all_encountered_socket_categories:
            sorted_categories = sorted(all_encountered_socket_categories.items(), key=lambda item: item[1]['count'], reverse=True)
            for cat_hash, details in sorted_categories:
                summary_lines = []
                summary_lines.append(f"  Category Hash: {cat_hash}")
                summary_lines.append(f"    Name: {details['name']}")
                summary_lines.append(f"    Encountered on: {details['count']} analyzed weapon(s)")
                if details['example_plugs']:
                    summary_lines.append(f"    Example Plugs seen in this category: { ', '.join(list(details['example_plugs']))}")
                summary_lines.append("-" * 20)
                report_file.write("\n".join(summary_lines) + "\n")
                # Optionally print summary to console too, or just a message that it's in the file
        else:
            no_cats_message = "  No socket categories were processed or encountered."
            print(no_cats_message)
            report_file.write(no_cats_message + "\n")

        report_file.write("\nEnd of Report.\n")
    print(f"Analysis complete. Report saved to: {REPORT_FILE_NAME}")

if __name__ == "__main__":
    asyncio.run(main()) 