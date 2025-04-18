import os
from dotenv import load_dotenv
import requests
import logging
from datetime import datetime
from typing import List, Dict
from enum import Enum
from colorama import init, Fore, Back, Style
import time
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Initialize colorama for cross-platform color support
init()

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

BUNGIE_API_ROOT = "https://www.bungie.net/Platform"
BUNGIE_API_KEY = os.getenv("BUNGIE_API_KEY")

class SortBy(Enum):
    NAME = "name"
    PROGRESS = "progress"
    OBJECTIVE = "objective"

def format_progress_bar(progress: int, total: int, width: int = 30) -> str:
    """Create a colored progress bar"""
    percentage = progress / total
    filled_length = int(width * percentage)
    empty_length = width - filled_length
    
    # Choose color based on progress
    if percentage >= 0.7:
        color = Fore.GREEN
    elif percentage >= 0.4:
        color = Fore.YELLOW
    else:
        color = Fore.RED
    
    bar = (
        f"{color}{'█' * filled_length}"
        f"{Fore.WHITE}{'░' * empty_length}"
        f"{Fore.RESET}"
    )
    return bar

def create_session():
    """Create a requests session with retry logic"""
    session = requests.Session()
    retry_strategy = Retry(
        total=3,
        backoff_factor=1,
        status_forcelist=[429, 500, 502, 503, 504],
    )
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("http://", adapter)
    session.mount("https://", adapter)
    return session

def make_api_request(url: str, headers: dict, params: dict = None) -> dict:
    """Make an API request with retry logic"""
    session = create_session()
    try:
        response = session.get(url, headers=headers, params=params)
        response.raise_for_status()
        return response.json()['Response']
    except requests.exceptions.RequestException as e:
        logging.error(f"API request failed: {str(e)}")
        if hasattr(e.response, 'text'):
            logging.error(f"Response text: {e.response.text}")
        raise
    finally:
        session.close()

def get_profile_data(membership_type, membership_id, headers):
    """Retrieve profile data from Bungie API."""
    components = [
        '102',  # ProfileInventories
        '201',  # CharacterInventories
        '300',  # ItemInstances
        '301',  # ItemObjectives
        '307'   # ItemCommonData
    ]
    
    profile_url = f"{BUNGIE_API_ROOT}/Destiny2/{membership_type}/Profile/{membership_id}/"
    params = {'components': ','.join(components)}
    
    logging.info("Fetching profile data...")
    return make_api_request(profile_url, headers, params)

def get_manifest_data(headers):
    """Retrieve manifest data for item definitions."""
    manifest_url = f"{BUNGIE_API_ROOT}/Destiny2/Manifest/"
    
    logging.info("Fetching manifest data...")
    manifest = make_api_request(manifest_url, headers)
    
    # Get the path to the item definitions
    item_defs_url = f"https://www.bungie.net{manifest['jsonWorldComponentContentPaths']['en']['DestinyInventoryItemDefinition']}"
    
    logging.info("Fetching item definitions...")
    session = create_session()
    try:
        response = session.get(item_defs_url)
        response.raise_for_status()
        return {'DestinyInventoryItemDefinition': response.json()}
    finally:
        session.close()

def get_incomplete_catalysts():
    logging.debug("Starting catalyst search...")
    
    # Load environment variables
    load_dotenv()
    access_token = os.getenv('BUNGIE_ACCESS_TOKEN')
    api_key = os.getenv('BUNGIE_API_KEY')

    if not access_token or not api_key:
        logging.error("Missing required environment variables")
        return []

    headers = {
        'X-API-Key': api_key,
        'Authorization': f'Bearer {access_token}'
    }

    # Get membership data
    membership_response = requests.get(
        'https://www.bungie.net/Platform/User/GetMembershipsForCurrentUser/',
        headers=headers
    )
    membership_data = membership_response.json()

    if 'Response' not in membership_data:
        logging.error("Failed to get membership data")
        return []

    # Get the first membership (assuming primary)
    membership = membership_data['Response']['destinyMemberships'][0]
    membership_type = membership['membershipType']
    membership_id = membership['membershipId']

    # Get profile data
    profile_data = get_profile_data(membership_type, membership_id, headers)
    if not profile_data:
        return []

    # Get manifest for item definitions
    item_hashes = set()
    
    # Profile inventory
    for item in profile_data.get('profileInventory', {}).get('data', {}).get('items', []):
        item_hashes.add(item.get('itemHash'))
        
    # Character inventories
    for inventory in profile_data.get('characterInventories', {}).get('data', {}).values():
        for item in inventory.get('items', []):
            item_hashes.add(item.get('itemHash'))
            
    logging.debug(f"Found {len(item_hashes)} unique items")
    
    # Get manifest data for all items
    manifest_data = get_manifest_data(headers)
    logging.debug(f"Retrieved manifest data for {len(manifest_data)} items")
    
    def process_incomplete_catalysts(profile_data, manifest_data):
        logging.debug("Processing items for incomplete catalysts...")
        incomplete_catalysts = []
        
        # Get item instances data which contains objective progress
        item_instances = profile_data.get('itemComponents', {}).get('objectives', {}).get('data', {})
        logging.debug(f"Found {len(item_instances)} items with objectives")
        
        # Process profile inventory items
        profile_items = profile_data.get('profileInventory', {}).get('data', {}).get('items', [])
        character_inventories = profile_data.get('characterInventories', {}).get('data', {})
        
        # Combine all items from profile and character inventories
        all_items = profile_items.copy()
        for inventory in character_inventories.values():
            all_items.extend(inventory.get('items', []))
        
        logging.debug(f"Processing {len(all_items)} total items")
        
        for item in all_items:
            item_hash = str(item.get('itemHash'))
            item_instance_id = str(item.get('itemInstanceId'))
            
            # Get item definition from manifest
            item_def = manifest_data.get(item_hash)
            if not item_def:
                continue
            
            # Check if item is exotic
            item_type = item_def.get('itemTypeAndTierDisplayName', '')
            if 'Exotic' not in item_type:
                continue
            
            logging.debug(f"Found exotic item: {item_def.get('displayProperties', {}).get('name')} ({item_type})")
            
            # Get item objectives
            item_objectives = item_instances.get(item_instance_id, {}).get('objectives', [])
            if not item_objectives:
                continue
            
            # Check if any objectives are incomplete
            has_incomplete = False
            objectives_data = []
            
            for objective in item_objectives:
                progress = objective.get('progress', 0)
                completion_value = objective.get('completionValue', 100)
                complete = objective.get('complete', False)
                
                if not complete:
                    has_incomplete = True
                    
                percent_complete = (progress / completion_value * 100) if completion_value > 0 else 0
                objectives_data.append({
                    'progress': progress,
                    'completion_value': completion_value,
                    'complete': complete,
                    'percent_complete': percent_complete
                })
                
                logging.debug(f"Objective progress: {progress}/{completion_value} ({percent_complete:.1f}%)")
            
            if has_incomplete:
                catalyst_info = {
                    'name': item_def.get('displayProperties', {}).get('name', 'Unknown'),
                    'type': item_type,
                    'objectives': objectives_data
                }
                incomplete_catalysts.append(catalyst_info)
                logging.debug(f"Added incomplete catalyst: {catalyst_info['name']}")
        
        logging.debug(f"Found {len(incomplete_catalysts)} incomplete catalysts")
        return incomplete_catalysts

    incomplete_catalysts = process_incomplete_catalysts(profile_data, manifest_data)
    
    if not incomplete_catalysts:
        print("No incomplete catalysts found.")
    else:
        print("\nIncomplete Catalysts:")
        for catalyst in incomplete_catalysts:
            print(f"\n{catalyst['name']} ({catalyst['type']})")
            for i, obj in enumerate(catalyst['objectives'], 1):
                print(f"  Objective {i}: {obj['progress']}/{obj['completion_value']} ({obj['percent_complete']:.1f}%)")

    return incomplete_catalysts

def print_usage():
    print(f"\n{Style.BRIGHT}Usage:{Style.RESET_ALL}")
    print("python test_catalysts.py [sort_by] [order]")
    print("\nSort options:")
    print("  --sort-name     Sort by catalyst name")
    print("  --sort-progress Sort by completion progress (default)")
    print("  --sort-objective Sort by objective description")
    print("\nOrder options:")
    print("  --asc          Ascending order")
    print("  --desc         Descending order (default)")

def test_get_incomplete_catalysts():
    """Test function to retrieve and display incomplete catalysts."""
    # Load environment variables
    load_dotenv()
    api_key = os.getenv('BUNGIE_API_KEY')
    access_token = os.getenv('BUNGIE_ACCESS_TOKEN')

    if not api_key or not access_token:
        logging.error("Missing required environment variables")
        print("\nError: Missing API key or access token. Please ensure you have logged in first.")
        return

    headers = {
        'X-API-Key': api_key,
        'Authorization': f'Bearer {access_token}'
    }

    try:
        # Get membership data
        membership_url = f"{BUNGIE_API_ROOT}/User/GetMembershipsForCurrentUser/"
        membership_data = make_api_request(membership_url, headers)
        
        if not membership_data.get('destinyMemberships'):
            logging.error("No Destiny memberships found")
            print("\nError: No Destiny 2 accounts found for this user.")
            return
            
        membership = membership_data['destinyMemberships'][0]
        membership_type = membership['membershipType']
        membership_id = membership['membershipId']
        
        logging.info(f"Found membership - Type: {membership_type}, ID: {membership_id}")

        # Get profile and manifest data
        profile_data = get_profile_data(membership_type, membership_id, headers)
        manifest_data = get_manifest_data(headers)

        # Process catalysts
        incomplete_catalysts = []
        
        # Check profile inventory
        if 'profileInventory' not in profile_data or 'data' not in profile_data['profileInventory']:
            logging.error("Profile inventory data not found")
            print("\nError: Could not retrieve inventory data.")
            return

        items = profile_data['profileInventory']['data'].get('items', [])
        logging.info(f"Found {len(items)} items in profile inventory")

        for item in items:
            try:
                item_instance_id = str(item.get('itemInstanceId', ''))
                if not item_instance_id:
                    continue

                # Safely get item components data
                item_instances = profile_data.get('itemComponents', {}).get('instances', {}).get('data', {})
                item_objectives = profile_data.get('itemComponents', {}).get('objectives', {}).get('data', {})

                item_instance = item_instances.get(item_instance_id)
                objectives = item_objectives.get(item_instance_id)

                if not item_instance or not objectives:
                    continue

                # Get item details from manifest
                item_hash = str(item['itemHash'])
                manifest_items = manifest_data.get('DestinyInventoryItemDefinition', {})
                
                if item_hash not in manifest_items:
                    logging.debug(f"Item hash {item_hash} not found in manifest")
                    continue

                item_def = manifest_items[item_hash]
                
                # Check if it's a catalyst (itemType 19)
                if item_def.get('itemType') == 19:
                    incomplete = False
                    for objective in objectives.get('objectives', []):
                        if not objective.get('complete', True):
                            incomplete = True
                            break
                    
                    if incomplete:
                        name = item_def.get('displayProperties', {}).get('name', 'Unknown Catalyst')
                        item_type = item_def.get('itemTypeDisplayName', 'Unknown Type')
                        
                        logging.info(f"Found incomplete catalyst: {name}")
                        incomplete_catalysts.append({
                            'name': name,
                            'type': item_type,
                            'objectives': objectives['objectives']
                        })

            except Exception as e:
                logging.debug(f"Error processing item: {str(e)}")
                continue

        # Display results
        print("\n" + "="*50)
        print("INCOMPLETE CATALYSTS")
        print("="*50 + "\n")

        if not incomplete_catalysts:
            print("No incomplete catalysts found!")
            return

        # Sort catalysts by name
        incomplete_catalysts.sort(key=lambda x: x['name'])

        for catalyst in incomplete_catalysts:
            print(f"🔸 {catalyst['name']} ({catalyst['type']})")
            print("-" * 40)
            
            for obj in catalyst['objectives']:
                progress = obj.get('progress', 0)
                completion_value = obj.get('completionValue', 100)
                percentage = (progress / completion_value) * 100 if completion_value > 0 else 0
                
                # Create a progress bar with color
                bar_length = 20
                filled_length = int(bar_length * percentage / 100)
                
                if percentage >= 75:
                    color = Fore.GREEN
                elif percentage >= 50:
                    color = Fore.YELLOW
                elif percentage >= 25:
                    color = Fore.MAGENTA
                else:
                    color = Fore.RED
                    
                bar = (
                    f"{color}{'█' * filled_length}"
                    f"{Fore.WHITE}{'░' * (bar_length - filled_length)}"
                    f"{Style.RESET_ALL}"
                )
                
                status = f"{Fore.GREEN}✓{Style.RESET_ALL}" if obj.get('complete', False) else " "
                print(f"  [{bar}] {percentage:.1f}% [{progress}/{completion_value}] {status}")
            print()

    except requests.exceptions.RequestException as e:
        logging.error(f"API request failed: {str(e)}")
        print("\nError: Failed to connect to Bungie servers. Please check your internet connection.")
    except KeyError as e:
        logging.error(f"Failed to parse API response: {str(e)}")
        print("\nError: Received unexpected data from Bungie servers.")
    except Exception as e:
        logging.error(f"An error occurred: {str(e)}")
        logging.debug("Full error:", exc_info=True)
        print("\nError: An unexpected error occurred. Please check the logs for details.")

if __name__ == '__main__':
    test_get_incomplete_catalysts()