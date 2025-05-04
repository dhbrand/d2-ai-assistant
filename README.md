# Destiny 2 Catalyst Tracker

A tool to track your Destiny 2 catalyst collection and progress.

## Repository Structure

This repository contains two versions of the Destiny 2 Catalyst Tracker:

- **desktop-app/**: Terminal-based Python application (original version)
- **web-app/**: Modern web application with React frontend and FastAPI backend
- **common/**: Shared resources used by both applications

## Web Application (Recommended)

The web application offers a modern, user-friendly interface for tracking your Destiny 2 catalysts.

### Setup

1. Navigate to the web-app directory:
   ```bash
   cd web-app
   ```

2. Follow the instructions in the [web-app README](web-app/README.md).

## Desktop Application (Legacy)

The desktop application is a command-line tool written in Python.

### Setup

1. Navigate to the desktop-app directory:
   ```bash
   cd desktop-app
   ```

2. Follow the instructions in the [desktop-app README](desktop-app/README.md).

## Common Resources

Both applications share resources in the `common/` directory, including:

- **Database**: SQLite database for storing catalyst data
- **API Data**: Cached API responses and manifest data

## Development

### Generate SSL Certificates

For local development with HTTPS:

```bash
python generate_cert.py
```

### Requirements

- Python 3.9+
- Node.js 16+
- Bungie.net API key (obtain from [Bungie Developer Portal](https://www.bungie.net/en/Application))

## Authentication Flow

The web application uses the standard OAuth 2.0 Authorization Code flow with PKCE (Proof Key for Code Exchange) disabled for interaction with the Bungie.net API. Here's a breakdown of how tokens are handled:

1.  **Initial Login:** The user clicks "Login with Bungie", gets redirected to Bungie.net to authorize the application, and is then redirected back to the application's callback URL (`/auth/callback` on the backend).
2.  **Token Exchange:** The backend exchanges the received authorization code for an **Access Token** and a **Refresh Token** directly with Bungie.
3.  **Token Storage:**
    *   **Access Token:** Short-lived (1 hour). Sent to the frontend and stored in `localStorage` along with its expiry time. It's used in the `Authorization: Bearer <token>` header for most authenticated API calls from the frontend to the backend.
    *   **Refresh Token:** Long-lived (90 days). Stored securely *only* on the backend (associated with the user in the database). It is *never* sent to the frontend.
4.  **Frontend Check on Startup:** When the frontend loads, it checks `localStorage`:
    *   If no access token exists, the user is considered logged out.
    *   If an access token exists, the frontend checks its expiry time locally. If it's expired, the token is removed from `localStorage` and the user is considered logged out locally. This is expected behavior, as the frontend cannot use an expired access token.
5.  **Backend Refresh on Demand:**
    *   When the frontend makes an authenticated API call to the backend, the backend validates the provided Access Token.
    *   If the Access Token is valid, the call proceeds.
    *   If the Access Token is *invalid* or *expired*, the backend automatically attempts to use the stored Refresh Token to get a *new* Access Token (and potentially a new Refresh Token) from Bungie.
    *   If the refresh is successful, the backend updates the tokens stored for the user and proceeds with the original API request using the new Access Token.
    *   If the refresh *fails* (e.g., the Refresh Token itself has expired after 90 days or been revoked), the backend returns an authentication error, and the user will typically need to log in again via the Bungie website.

**Why this approach?**

*   **Security:** Keeps the long-lived, powerful refresh token secure on the backend.
*   **Separation of Concerns:** Frontend manages the usable access token; backend manages the refresh process.
*   **Simplicity:** Avoids complex frontend logic to trigger refresh checks and securely identify the user to the backend without a valid access token.

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Features

- Track completion progress for all Destiny 2 exotic catalysts
- Automatic data synchronization with Bungie.net API
- Dark/Light theme support
- Cross-platform desktop application (Windows, macOS, Linux)
- Web interface for mobile access

## Prerequisites

- Python 3.8 or higher
- Node.js 16 or higher
- npm 8 or higher

## Development Setup

1. Clone the repository:
```bash
git clone https://github.com/yourusername/destiny2-catalyst-tracker.git
cd destiny2-catalyst-tracker
```

2. Run the development setup script:
```bash
cd web-app
chmod +x setup_dev.sh
./setup_dev.sh
```

The setup script will:
- Create and activate a Python virtual environment
- Install backend dependencies
- Run backend tests
- Install frontend dependencies
- Run frontend tests

## Running the Application

### Desktop Application

```bash
python desktop_app.py
```

### Web Application (Recommended)

**Important Note:** For local development, both the backend and frontend must run over **HTTPS** due to Bungie API requirements. The recommended way to handle local HTTPS is using `mkcert`.

**Python Version:** As of [Current Date], there appear to be package compatibility issues with Python 3.13 on some systems (e.g., macOS ARM) involving SQLAlchemy/Pydantic. **It is strongly recommended to use Python 3.11 or 3.12 for the backend virtual environment.**

1.  **Install `mkcert` (if not already done):**
    Follow the instructions for your OS at [https://github.com/FiloSottile/mkcert#installation](https://github.com/FiloSottile/mkcert#installation). For macOS with Homebrew:
    ```bash
    brew install mkcert
    # Then install the local CA (only needs to be done once per machine)
    mkcert -install
    ```

2.  **Generate Certificates:**
    From the project root directory:
    ```bash
    # This command creates web_app/cert.pem and web_app/key.pem trusted for localhost
    mkcert -cert-file web_app/cert.pem -key-file web_app/key.pem localhost 127.0.0.1 ::1
    ```

3.  **Start the Backend Server (using Uvicorn):**
    In a terminal, from the **project root** directory (`destiny2_catalysts/`):
    ```bash
    # Activate virtual environment
    source venv/bin/activate
    
    # Set PYTHONPATH and run Uvicorn with SSL (using mkcert-generated files)
    PYTHONPATH=. uvicorn web_app.backend.main:app --reload --ssl-keyfile=web_app/key.pem --ssl-certfile=web_app/cert.pem --port 8000
    ```
    Keep this terminal running.

4.  **Start the Frontend Development Server:**
    In a *separate* terminal, navigate to the frontend directory:
    ```bash
    cd web_app/frontend
    npm start
    ```
    *(The `start` script in `package.json` should be configured to use `web_app/cert.pem` and `web_app/key.pem` via `SSL_CRT_FILE` and `SSL_KEY_FILE` env vars)*

5.  **Access the Application:**
    *   Open your web browser and navigate directly to the frontend application: `https://localhost:3000`.
    *   You should **not** see a browser security warning if `mkcert` setup was successful.
    *   The first time you log in, you will be redirected to Bungie.net for authorization.

## Testing

### Backend Tests
```bash
cd web-app/backend
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
pytest
```

### Frontend Tests
```bash
cd web-app/frontend
npm test
```

## Contributing

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## Acknowledgments

- Bungie for providing the Destiny 2 API
- The Destiny 2 community for their support and feedback 