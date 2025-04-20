# Destiny 2 Catalyst Tracker

A desktop application to track incomplete catalysts in Destiny 2.

## Features

- Track incomplete catalysts across all characters
- View detailed progress and requirements for each catalyst
- Individual objective tracking with progress bars
- Modern neon-themed UI with dark/light mode support
- Automatic authentication with Bungie.net
- Secure HTTPS OAuth implementation
- Search, sort, and filter catalysts
- Group catalysts by weapon type
- Progress summary statistics

## UI Features

### Modern Design
- Neon-themed interface with cyberpunk aesthetic
- Dark and light mode support
- Responsive layout that adapts to window size
- Custom fonts and animations

### Catalyst Display
- Collapsible weapon type groups
- Individual progress bars for each objective
- Overall progress calculation
- Detailed objective descriptions
- Search by catalyst name
- Sort by name, progress, or weapon type
- Filter by completion status (All, Completed, In Progress, Not Started)

### Progress Tracking
- Overall completion percentage
- Individual objective progress bars
- Detailed progress statistics (e.g., "5/10 kills")
- Progress summary showing total, completed, and in-progress catalysts

## Development Process

### Branching Strategy

```
main (production)
  └── dev (staging/development)
      ├── feature/oauth-implementation
      ├── feature/catalyst-tracking
      ├── feature/ui-improvements
      └── feature/other-features
```

#### Branches
- `main`: Production-ready code, tagged with version numbers
- `dev`: Integration branch for testing features
- `feature/*`: Individual feature branches

#### Workflow
1. Create feature branch from `dev`
2. Develop and test feature
3. Create PR to merge into `dev`
4. Test in `dev` environment
5. When stable, create PR to merge into `main`
6. Tag releases in `main`

### Current Features in Development

- OAuth Implementation (`feature/oauth-implementation`)
  - Secure HTTPS authentication
  - Token management
  - Self-signed certificates

- Catalyst Tracking (`feature/catalyst-tracking`)
  - Progress tracking
  - Requirements display
  - Character inventory scanning

## Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/destiny2_catalysts.git
cd destiny2_catalysts
```

2. Create a virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Set up environment variables:
Create a `.env` file in the project root with:
```
BUNGIE_CLIENT_ID=your_client_id
BUNGIE_API_KEY=your_api_key
REDIRECT_URI=https://localhost:4200/auth
```

4. Generate SSL certificates:
The application will automatically generate self-signed SSL certificates for local development in the `dev-certs` directory.

## Authentication

The application uses OAuth 2.0 for secure authentication with Bungie.net. The authentication flow:

1. User initiates authentication
2. Browser opens to Bungie.net authorization page
3. User authorizes the application
4. OAuth callback is handled by local HTTPS server
5. Access token is obtained and stored securely

The OAuth implementation includes:
- HTTPS support with self-signed certificates
- Token refresh handling
- Error handling and logging
- Secure state parameter verification

## Development

### Testing Authentication

To test the authentication flow:
```bash
python test_oauth.py
```

This will:
1. Start a local HTTPS server
2. Open the browser for authentication
3. Handle the OAuth callback
4. Test token refresh
5. Make a test API call

### Project Structure

- `bungie_oauth.py`: OAuth implementation
- `generate_cert.py`: SSL certificate generation
- `test_oauth.py`: Authentication testing
- `catalyst_tracker.py`: Catalyst tracking functionality
- `desktop_app.py`: Main application GUI

### Test Scripts

The project contains two types of test scripts:

1. **API Test Scripts** (prefixed with `test_` and suffixed with `_api.py`)
   - `test_oauth_api.py`: Independent script for testing the OAuth authentication flow
   - `test_catalyst_api.py`: Independent script for testing the Destiny 2 API for catalyst information
   - These scripts are used for manual testing and development of API integration
   - They are standalone scripts that can be run independently

2. **Unit Tests** (suffixed with `_test.py`)
   - `bungie_oauth_test.py`: Unit tests for the OAuth implementation module
   - `catalyst_test.py`: Unit tests for the catalyst tracking module
   - These scripts contain automated tests for production code
   - They test the functionality of our production modules

Naming Convention:
- API test scripts: `test_[feature]_api.py`
- Unit tests: `[module]_test.py`

Example Usage:
```bash
# Run API test scripts (manual testing)
python test_oauth_api.py
python test_catalyst_api.py

# Run unit tests
python -m unittest bungie_oauth_test.py
python -m unittest catalyst_test.py
```

## Contributing

1. Fork the repository
2. Create a feature branch from `dev`
3. Make your changes
4. Submit a pull request to `dev`

## License

This project is licensed under the MIT License - see the LICENSE file for details. 