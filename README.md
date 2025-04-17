# Destiny 2 Catalyst Tracker

A desktop application to track your Destiny 2 exotic weapon catalysts progress.

## Features

- OAuth2 authentication with Bungie.net
- Real-time catalyst progress tracking
- Visual progress bars for each catalyst
- Secure HTTPS communication

## Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/destiny2-catalyst-tracker.git
cd destiny2-catalyst-tracker
```

2. Create a virtual environment and install dependencies:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
```

3. Set up your Bungie.net API credentials:
   - Go to https://www.bungie.net/en/Application
   - Create a new application
   - Set OAuth Client Type to "Public"
   - Set Redirect URL to `https://localhost:4200/auth`
   - Copy your API Key and Client ID

4. Create a `.env` file in the project root:
```bash
BUNGIE_CLIENT_ID=your_client_id
BUNGIE_API_KEY=your_api_key
REDIRECT_URI=https://localhost:4200/auth
```

5. Generate SSL certificates for local HTTPS:
```bash
mkdir dev-certs
cd dev-certs
openssl req -x509 -newkey rsa:4096 -nodes -out server.crt -keyout server.key -days 365 -subj "/CN=localhost"
```

## Running the Application

```bash
python desktop_app.py
```

## Development

This project uses:
- PyQt6 for the desktop interface
- Python's built-in SSL and HTTP server for OAuth handling
- Bungie.net API for Destiny 2 data

## Security Notes

- The application uses HTTPS for OAuth callback handling
- State parameter is used to prevent CSRF attacks
- API keys are stored in environment variables
- SSL certificates are required for local HTTPS

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the LICENSE file for details. 