import os
import json
from typing import List, Dict, Optional
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import requests

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

class CatalystAPI:
    def __init__(self, api_key: str, auth_token: str):
        """Initialize the Catalyst API with API key and auth token"""
        self.base_url = "https://www.bungie.net/Platform"
        self.api_key = api_key
        self.auth_token = auth_token
        self.session = self._create_session()
        
    def _create_session(self) -> requests.Session:
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
        
    def _get_headers(self) -> Dict[str, str]:
        """Get headers with API key and auth token"""
        return {
            'X-API-Key': self.api_key,
            'Authorization': f'Bearer {self.auth_token}'
        }
        
    def get_membership_info(self) -> Optional[Dict[str, str]]:
        """Get the current user's membership info"""
        url = f"{self.base_url}/User/GetMembershipsForCurrentUser/"
        
        try:
            response = self.session.get(url, headers=self._get_headers())
            if response.status_code != 200:
                print(f"API Error getting membership info: {response.status_code}")
                print(f"Response: {response.text}")
                return None
                
            data = response.json()
            if 'Response' not in data or not data['Response'].get('destinyMemberships'):
                print("No Destiny memberships found")
                return None
                
            # Get the first membership (usually the primary one)
            membership = data['Response']['destinyMemberships'][0]
            return {
                'type': membership['membershipType'],
                'id': membership['membershipId']
            }
        except Exception as e:
            print(f"Error getting membership info: {e}")
            return None
            
    def get_profile(self, membership_type: int, membership_id: str) -> Optional[Dict]:
        """Get the user's profile with records"""
        url = f"{self.base_url}/Destiny2/{membership_type}/Profile/{membership_id}/"
        params = {
            "components": "900,202"  # Profile records and character records
        }
        
        try:
            response = self.session.get(url, headers=self._get_headers(), params=params)
            if response.status_code != 200:
                print(f"API Error getting profile: {response.status_code}")
                print(f"Response: {response.text}")
                return None
                
            return response.json()
        except Exception as e:
            print(f"Error getting profile: {e}")
            return None
            
    def get_definition(self, table: str, hash_id: int) -> Optional[Dict]:
        """Get a definition from the Destiny 2 manifest"""
        url = f"{self.base_url}/Destiny2/Manifest/{table}/{hash_id}/"
        try:
            response = self.session.get(url, headers=self._get_headers())
            if response.status_code != 200:
                return None
            return response.json()['Response']
        except Exception as e:
            print(f"Error getting definition for {table} {hash_id}: {e}")
            return None
            
    def get_catalysts(self) -> List[Dict]:
        """Get all catalysts and their completion status"""
        # First get membership info
        membership = self.get_membership_info()
        if not membership:
            return []
            
        # Get profile data
        profile = self.get_profile(membership['type'], membership['id'])
        if not profile or 'Response' not in profile:
            return []
            
        catalysts = []
        
        # Get profile records
        profile_records = profile['Response'].get('profileRecords', {}).get('data', {}).get('records', {})
        
        # Check each catalyst record
        for record_hash_str, record in profile_records.items():
            record_hash = int(record_hash_str)
            if record_hash in CATALYST_RECORD_HASHES:
                catalyst_info = self._get_catalyst_info(record_hash, record)
                if catalyst_info:
                    catalysts.append(catalyst_info)
        
        return catalysts
        
    def _get_catalyst_info(self, record_hash: int, record: Dict) -> Optional[Dict]:
        """Get detailed information about a catalyst"""
        # Check if record is complete
        state = record.get('state', 0)
        
        # 4 = ObjectiveNotCompleted
        complete = not (state & 4)
        if complete:
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
            'objectives': objectives,
            'icon': record_def.get('displayProperties', {}).get('icon', ''),
            'description': record_def.get('displayProperties', {}).get('description', '')
        } 