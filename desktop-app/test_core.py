import os
import webbrowser
import http.server
import socketserver
import urllib.parse
import requests
import json
from dotenv import load_dotenv
import logging
from datetime import datetime, timedelta

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Load environment variables
load_dotenv()

# Configuration
BUNGIE_API_ROOT = "https://www.bungie.net/Platform"
BUNGIE_AUTH_URL = "https://www.bungie.net/en/OAuth/Authorize"
BUNGIE_TOKEN_URL = "https://www.bungie.net/platform/app/oauth/token/"
BUNGIE_CLIENT_ID = os.getenv("BUNGIE_CLIENT_ID")
BUNGIE_API_KEY = os.getenv("BUNGIE_API_KEY")
REDIRECT_URI = os.getenv("REDIRECT_URI")

class SimpleCallbackHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        """Handle the OAuth callback"""
        self.send_response(200)
        self.send_header('Content-type', 'text/html')
        self.end_headers()
        
        # Parse the callback URL
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        
        if "code" in query:
            self.server.oauth_code = query["code"][0]
            self.wfile.write(b"Authentication successful! You can close this window.")
        else:
            self.wfile.write(b"Authentication failed! Please check the console.")
    
    def log_message(self, format, *args):
        """Suppress logging"""
        pass

def get_auth_code():
    """Get authorization code through simple callback server"""
    # Parse redirect URI for port
    parsed_uri = urllib.parse.urlparse(REDIRECT_URI)
    port = parsed_uri.port or 4200
    
    # Start callback server
    with socketserver.TCPServer(("localhost", port), SimpleCallbackHandler) as httpd:
        httpd.oauth_code = None
        
        # Open browser for auth
        params = {
            "client_id": BUNGIE_CLIENT_ID,
            "response_type": "code",
            "redirect_uri": REDIRECT_URI
        }
        auth_url = f"{BUNGIE_AUTH_URL}?{urllib.parse.urlencode(params)}"
        print(f"\nOpening browser for authentication...")
        
        # Check if Safari is running and use existing window if available
        os.system('osascript -e \'tell application "Safari" to activate\' -e \'tell application "Safari" to open location "%s"\'' % auth_url)
        
        # Wait for callback
        print(f"Waiting for callback on port {port}...")
        httpd.handle_request()
        
        return httpd.oauth_code

def get_access_token(auth_code):
    """Exchange authorization code for access token"""
    token_data = {
        "grant_type": "authorization_code",
        "code": auth_code,
        "client_id": BUNGIE_CLIENT_ID,
        "redirect_uri": REDIRECT_URI
    }
    
    headers = {
        "X-API-Key": BUNGIE_API_KEY,
        "Content-Type": "application/x-www-form-urlencoded"
    }
    
    response = requests.post(BUNGIE_TOKEN_URL, data=token_data, headers=headers)
    return response.json()

def get_destiny_profile(access_token):
    """Get user's Destiny profile"""
    headers = {
        "X-API-Key": BUNGIE_API_KEY,
        "Authorization": f"Bearer {access_token}"
    }
    
    # Get membership data
    response = requests.get(
        f"{BUNGIE_API_ROOT}/User/GetMembershipsForCurrentUser/",
        headers=headers
    )
    
    if response.status_code != 200:
        print(f"Error getting profile: {response.json()}")
        return None
        
    return response.json()["Response"]

def get_catalysts(access_token, membership_type, membership_id):
    """Get catalyst data"""
    headers = {
        "X-API-Key": BUNGIE_API_KEY,
        "Authorization": f"Bearer {access_token}"
    }
    
    # Get profile inventory
    response = requests.get(
        f"{BUNGIE_API_ROOT}/Destiny2/{membership_type}/Profile/{membership_id}/",
        headers=headers,
        params={"components": "102,300,301,307"}  # Inventory and objectives
    )
    
    if response.status_code != 200:
        print(f"Error getting inventory: {response.json()}")
        return []
    
    profile_data = response.json()["Response"]
    catalysts = []
    
    if "profileInventory" in profile_data:
        items = profile_data["profileInventory"]["data"]["items"]
        total = len(items)
        print(f"\nScanning {total} items for catalysts...")
        
        for idx, item in enumerate(items, 1):
            print(f"\rProgress: {idx}/{total}", end="")
            
            try:
                # Get item definition
                item_response = requests.get(
                    f"{BUNGIE_API_ROOT}/Destiny2/Manifest/DestinyInventoryItemDefinition/{item['itemHash']}/",
                    headers=headers
                )
                
                if item_response.status_code != 200:
                    continue
                    
                item_def = item_response.json()["Response"]
                
                # Check if it's a catalyst
                if "catalyst" not in item_def.get("displayProperties", {}).get("name", "").lower():
                    continue
                
                # Get item instance details if available
                if "itemInstanceId" in item:
                    instance_response = requests.get(
                        f"{BUNGIE_API_ROOT}/Destiny2/{membership_type}/Profile/{membership_id}/Item/{item['itemInstanceId']}/",
                        headers=headers,
                        params={"components": "300,307"}
                    )
                    
                    if instance_response.status_code == 200:
                        instance_data = instance_response.json()["Response"]
                        
                        if "objectives" in instance_data and instance_data["objectives"]["data"]:
                            objectives = instance_data["objectives"]["data"]["objectives"]
                            
                            # Only include incomplete catalysts
                            if any(not obj.get("complete", False) for obj in objectives):
                                catalyst_info = {
                                    "name": item_def["displayProperties"]["name"],
                                    "description": item_def["displayProperties"].get("description", ""),
                                    "objectives": [
                                        {
                                            "description": obj.get("progressDescription", "Unknown"),
                                            "progress": obj.get("progress", 0),
                                            "completion": obj.get("completionValue", 100),
                                            "complete": obj.get("complete", False)
                                        }
                                        for obj in objectives
                                    ]
                                }
                                catalysts.append(catalyst_info)
            
            except Exception as e:
                logger.debug(f"Error processing item {item.get('itemHash')}: {e}")
                continue
    
    print("\nDone scanning items.")
    return catalysts

def main():
    print("\nTesting Destiny 2 Catalyst API Integration")
    print("=========================================")
    
    # Step 1: Get authorization code
    print("\nStep 1: Getting authorization code...")
    auth_code = get_auth_code()
    
    if not auth_code:
        print("Failed to get authorization code!")
        return
    
    # Step 2: Exchange code for token
    print("\nStep 2: Exchanging code for access token...")
    token_info = get_access_token(auth_code)
    
    if "access_token" not in token_info:
        print(f"Failed to get access token: {token_info}")
        return
    
    access_token = token_info["access_token"]
    print("Successfully obtained access token!")
    
    # Step 3: Get Destiny profile
    print("\nStep 3: Getting Destiny profile...")
    profile = get_destiny_profile(access_token)
    
    if not profile:
        print("Failed to get Destiny profile!")
        return
    
    # Get first membership (we can enhance this later)
    destiny_membership = profile["destinyMemberships"][0]
    membership_type = destiny_membership["membershipType"]
    membership_id = destiny_membership["membershipId"]
    
    print(f"Found profile: {destiny_membership.get('displayName', 'Unknown Guardian')}")
    
    # Step 4: Get catalysts
    print("\nStep 4: Getting catalyst data...")
    catalysts = get_catalysts(access_token, membership_type, membership_id)
    
    # Display results
    print(f"\nFound {len(catalysts)} incomplete catalysts:")
    print("----------------------------------------")
    
    for catalyst in catalysts:
        print(f"\n{catalyst['name']}")
        print("-" * len(catalyst['name']))
        
        for obj in catalyst["objectives"]:
            progress = obj["progress"]
            total = obj["completion"]
            percentage = (progress / total) * 100
            print(f"Progress: {progress}/{total} ({percentage:.1f}%)")
            print(f"Objective: {obj['description']}")
    
    # Save results to file
    with open("catalyst_data.json", "w") as f:
        json.dump(catalysts, f, indent=2)
    print("\nResults saved to catalyst_data.json")

if __name__ == "__main__":
    main() 