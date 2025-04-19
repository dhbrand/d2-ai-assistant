import unittest
from unittest.mock import patch, MagicMock
import os
from dotenv import load_dotenv
from catalyst import CatalystAPI

class TestCatalystAPI(unittest.TestCase):
    def setUp(self):
        """Set up test fixtures"""
        load_dotenv()
        self.api_key = os.getenv('BUNGIE_API_KEY')
        with open('auth_token.txt', 'r') as f:
            self.auth_token = f.read().strip()
        self.api = CatalystAPI(self.api_key, self.auth_token)
        
    def test_get_membership_info_success(self):
        """Test successful retrieval of membership info"""
        with patch.object(self.api.session, 'get') as mock_get:
            # Mock successful response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'Response': {
                    'destinyMemberships': [{
                        'membershipType': 3,
                        'membershipId': '4611686018517808552'
                    }]
                }
            }
            mock_get.return_value = mock_response
            
            result = self.api.get_membership_info()
            
            self.assertIsNotNone(result)
            self.assertEqual(result['type'], 3)
            self.assertEqual(result['id'], '4611686018517808552')
            
    def test_get_membership_info_failure(self):
        """Test failed retrieval of membership info"""
        with patch.object(self.api.session, 'get') as mock_get:
            # Mock failed response
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_get.return_value = mock_response
            
            result = self.api.get_membership_info()
            
            self.assertIsNone(result)
            
    def test_get_profile_success(self):
        """Test successful retrieval of profile data"""
        with patch.object(self.api.session, 'get') as mock_get:
            # Mock successful response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'Response': {
                    'profileRecords': {
                        'data': {
                            'records': {
                                '2524364954': {
                                    'state': 12,
                                    'objectives': [
                                        {
                                            'objectiveHash': 3499974533,
                                            'progress': 0,
                                            'completionValue': 2,
                                            'complete': False,
                                            'visible': True
                                        }
                                    ]
                                }
                            }
                        }
                    }
                }
            }
            mock_get.return_value = mock_response
            
            result = self.api.get_profile(3, '4611686018517808552')
            
            self.assertIsNotNone(result)
            self.assertIn('Response', result)
            self.assertIn('profileRecords', result['Response'])
            
    def test_get_definition_success(self):
        """Test successful retrieval of definition"""
        with patch.object(self.api.session, 'get') as mock_get:
            # Mock successful response
            mock_response = MagicMock()
            mock_response.status_code = 200
            mock_response.json.return_value = {
                'Response': {
                    'displayProperties': {
                        'name': 'Test Catalyst',
                        'description': 'Test Description',
                        'icon': 'test_icon.png'
                    }
                }
            }
            mock_get.return_value = mock_response
            
            result = self.api.get_definition('DestinyRecordDefinition', 2524364954)
            
            self.assertIsNotNone(result)
            self.assertEqual(result['displayProperties']['name'], 'Test Catalyst')
            
    def test_get_catalysts_success(self):
        """Test successful retrieval of catalysts"""
        with patch.object(self.api, 'get_membership_info') as mock_membership, \
             patch.object(self.api, 'get_profile') as mock_profile, \
             patch.object(self.api, 'get_definition') as mock_definition:
            
            # Mock membership info
            mock_membership.return_value = {
                'type': 3,
                'id': '4611686018517808552'
            }
            
            # Mock profile data
            mock_profile.return_value = {
                'Response': {
                    'profileRecords': {
                        'data': {
                            'records': {
                                '2524364954': {  # Vigilance Wing catalyst
                                    'state': 12,
                                    'objectives': [
                                        {
                                            'objectiveHash': 3499974533,
                                            'progress': 0,
                                            'completionValue': 2,
                                            'complete': False,
                                            'visible': True
                                        }
                                    ]
                                }
                            }
                        }
                    }
                }
            }
            
            # Mock definition data
            mock_definition.return_value = {
                'displayProperties': {
                    'name': 'Vigilance Wing Catalyst',
                    'description': 'Test Description',
                    'icon': 'test_icon.png'
                }
            }
            
            catalysts = self.api.get_catalysts()
            
            self.assertIsNotNone(catalysts)
            self.assertGreater(len(catalysts), 0)
            self.assertEqual(catalysts[0]['name'], 'Vigilance Wing Catalyst')
            
    def test_get_catalyst_info_complete(self):
        """Test handling of complete catalyst"""
        record = {
            'state': 67,  # Complete state
            'objectives': []
        }
        
        result = self.api._get_catalyst_info(2524364954, record)
        
        self.assertIsNone(result)  # Should return None for complete catalysts
        
    def test_get_catalyst_info_incomplete(self):
        """Test handling of incomplete catalyst"""
        with patch.object(self.api, 'get_definition') as mock_definition:
            # Mock record definition
            mock_definition.return_value = {
                'displayProperties': {
                    'name': 'Test Catalyst',
                    'description': 'Test Description',
                    'icon': 'test_icon.png'
                }
            }
            
            record = {
                'state': 12,  # Incomplete state
                'objectives': [
                    {
                        'objectiveHash': 3499974533,
                        'progress': 0,
                        'completionValue': 2,
                        'complete': False,
                        'visible': True
                    }
                ]
            }
            
            result = self.api._get_catalyst_info(2524364954, record)
            
            self.assertIsNotNone(result)
            self.assertEqual(result['name'], 'Test Catalyst')
            self.assertEqual(len(result['objectives']), 1)

if __name__ == '__main__':
    unittest.main() 