import os
import sys
import requests
from dotenv import load_dotenv
import json
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

# Load environment variables
load_dotenv()

# Known catalyst record hashes from DIM
CATALYST_RECORD_HASHES = {
    2744330560,  # Sturm
    2599526136,  # MIDA Multi-Tool
    2478247171,  # Sunshot
    2524364954,  # Vigilance Wing
    3567687058,  # Ratking
    1497347070,  # Merciless
    3250123168,  # Crimson
    1815425870,  # Prometheus Lens
    1182982189,  # The Colony
    2761319400,  # Skyburner's Oath
    2940589008,  # Polaris Lance
    3413074534,  # Worldline Zero
    3549153978,  # Fighting Lion
    3549153979,  # Sweet Business
    3549153980,  # Graviton Lance
    3549153981,  # Telesto
    3549153982,  # SUROS Regime
    3549153983,  # Jade Rabbit
    3549153984,  # Riskrunner
    3549153985,  # Borealis
    3549153986,  # Legend of Acrius
    3549153988,  # Hard Light
    3549153989,  # Tractor Cannon
    3549153990,  # D.A.R.C.I.
    3549153991,  # Coldheart
    2856496392,  # The Prospector
    2856496395,  # Lord of Wolves
    2856496394,  # Trinity Ghoul
    2856496393,  # Two-Tailed Fox
    2856496391,  # Black Talon
    2856496390,  # The Chaperone
    2856496389,  # Ace of Spades
    2856496388,  # Cerberus+1
    2856496387,  # Malfeasance
    2856496386,  # The Last Word
    2856496385,  # Izanagi's Burden
    2856496384,  # Le Monarque
    2856496398,  # Jotunn
    2856496397,  # Lumina
    2856496396,  # Truth
    2856496399,  # Bad Juju
    3862768196,  # Eriana's Vow
    3862768197,  # Symmetry
    3862768198,  # Devil's Ruin
    3862768199,  # Tommy's Matchbook
    3862768192,  # The Fourth Horseman
    3862768193,  # Heir Apparent
    3862768194,  # Witherhoard
    3862768195,  # Ruinous Effigy
    3862768188,  # Traveler's Chosen
    3862768189,  # No Time to Explain
    3862768190,  # Duality
    3862768191,  # Cloudstrike
    3862768184,  # Hawkmoon
    3862768185,  # Dead Man's Tale
    3862768186,  # Ticuu's Divination
    3862768187,  # Cryosthesia 77K
    3862768180,  # Lorentz Driver
    3862768181,  # Ager's Scepter
    3862768182,  # Forerunner
    3862768183,  # Grand Overture
    3862768176,  # Osteo Striga
    3862768177,  # Dead Messenger
    3862768178,  # Trespasser
    3862768179,  # Quicksilver Storm
    3862768172,  # Touch of Malice
    3862768173,  # Revision Zero
    3862768174,  # Vexcalibur
    3862768175,  # Verglas Curve
    3862768168,  # Final Warning
    3862768169,  # Deterministic Chaos
    3862768170,  # Conditional Finality
    3862768171,  # Centrifuse
}

def create_session():
    """Create a requests session with retry logic"""
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=0.5,
        status_forcelist=[500, 502, 503, 504]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

class Destiny2API:
    def __init__(self):
        self.base_url = "https://www.bungie.net/Platform"
        self.api_key = os.getenv('BUNGIE_API_KEY')
        self.membership_type = None
        self.membership_id = None
        self.session = create_session()
        
    def get_headers(self):
        """Get headers with API key and auth token"""
        with open('auth_token.txt', 'r') as f:
            auth_token = f.read().strip()
            
        return {
            'X-API-Key': self.api_key,
            'Authorization': f'Bearer {auth_token}'
        }
        
    def get_membership_info(self):
        """Get the current user's membership info"""
        url = f"{self.base_url}/User/GetMembershipsForCurrentUser/"
        
        try:
            response = self.session.get(url, headers=self.get_headers())
            if response.status_code != 200:
                print(f"API Error getting membership info: {response.status_code}")
                print(f"Response: {response.text}")
                response.raise_for_status()
                
            data = response.json()
            if 'Response' not in data or not data['Response'].get('destinyMemberships'):
                print("No Destiny memberships found")
                return False
                
            # Get the first membership (usually the primary one)
            membership = data['Response']['destinyMemberships'][0]
            self.membership_type = membership['membershipType']
            self.membership_id = membership['membershipId']
            
            print(f"Found membership - Type: {self.membership_type}, ID: {self.membership_id}")
            return True
        except Exception as e:
            print(f"Error getting membership info: {e}")
            return False
        
    def get_profile(self):
        """Get the current user's profile with records"""
        if not self.membership_type or not self.membership_id:
            if not self.get_membership_info():
                return None
                
        url = f"{self.base_url}/Destiny2/{self.membership_type}/Profile/{self.membership_id}/"
        params = {
            "components": "900,202"  # Profile records and character records
        }
        
        try:
            response = self.session.get(url, headers=self.get_headers(), params=params)
            if response.status_code != 200:
                print(f"API Error getting profile: {response.status_code}")
                print(f"Response: {response.text}")
                response.raise_for_status()
                
            return response.json()
        except Exception as e:
            print(f"Error getting profile: {e}")
            return None
            
    def get_definition(self, table, hash_id):
        """Get a definition from the Destiny 2 manifest"""
        url = f"{self.base_url}/Destiny2/Manifest/{table}/{hash_id}/"
        try:
            response = self.session.get(url, headers=self.get_headers())
            if response.status_code != 200:
                return None
            return response.json()['Response']
        except Exception as e:
            print(f"Error getting definition for {table} {hash_id}: {e}")
            return None
            
    def get_catalysts(self):
        """Get all catalysts and their completion status"""
        # First get profile to find characters
        profile = self.get_profile()
        if not profile or 'Response' not in profile:
            print("Failed to get profile data")
            return []
            
        catalysts = []
        
        # Get profile records
        profile_records = profile['Response'].get('profileRecords', {}).get('data', {}).get('records', {})
        print(f"Found {len(profile_records)} profile records")
        
        # Get character records
        character_records = {}
        if 'characterRecords' in profile['Response']:
            for char_id, records in profile['Response']['characterRecords']['data'].items():
                character_records[char_id] = records.get('records', {})
            print(f"Found {len(character_records)} character records")
        
        # Check each catalyst record
        for record_hash_str, record in profile_records.items():
            record_hash = int(record_hash_str)
            if record_hash in CATALYST_RECORD_HASHES:
                print(f"\nChecking catalyst record {record_hash}:")
                print(json.dumps(record, indent=2))
                
                catalyst_info = self._get_catalyst_info(record_hash, record)
                if catalyst_info:
                    catalysts.append(catalyst_info)
        
        return catalysts
        
    def _get_catalyst_info(self, record_hash, record):
        """Get detailed information about a catalyst"""
        # Check if record is complete
        state = record.get('state', 0)
        print(f"Record state: {state}")
        
        # 4 = ObjectiveNotCompleted
        complete = not (state & 4)
        if complete:
            print("Record is complete, skipping")
            return None
            
        # Get record definition for name and objectives
        record_def = self.get_definition('DestinyRecordDefinition', record_hash)
        if not record_def:
            return None
            
        # Get objective definitions
        objectives = []
        for obj in record.get('objectives', []):
            obj_def = self.get_definition('DestinyObjectiveDefinition', obj['objectiveHash'])
            if obj_def:
                objectives.append({
                    'description': obj_def.get('progressDescription', 'Unknown'),
                    'progress': obj.get('progress', 0),
                    'completion': obj.get('completionValue', 100),
                    'complete': obj.get('complete', False)
                })
            
        return {
            'name': record_def.get('displayProperties', {}).get('name', 'Unknown Catalyst'),
            'objectives': objectives
        }

def main():
    try:
        # Check if we have an auth token
        if not os.path.exists('auth_token.txt'):
            print("No auth token found. Please run test_oauth.py first to get an auth token.")
            sys.exit(1)
            
        # Create API instance
        api = Destiny2API()
        
        # Get catalysts
        print("Fetching catalyst information...")
        catalysts = api.get_catalysts()
        
        # Print results
        print("\nFound catalysts:")
        for catalyst in catalysts:
            print(f"\n{catalyst['name']}")
            print("-" * len(catalyst['name']))
            for obj in catalyst['objectives']:
                progress = obj['progress']
                total = obj['completion']
                percentage = (progress / total) * 100
                print(f"Progress: {progress}/{total} ({percentage:.1f}%)")
                print(f"Objective: {obj['description']}")
            
    except Exception as e:
        print(f"Error: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main() 