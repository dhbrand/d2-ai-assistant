# Destiny 2 Catalyst Tracker - Web Application

This directory contains the web application version of the Destiny 2 Catalyst Tracker.

## Architecture

- **Backend**: FastAPI (Python) server with SQLite database
- **Frontend**: React.js with Material UI components
- **Authentication**: OAuth with Bungie.net

## Setup

1. Set up the development environment:
   ```bash
   ./setup_dev.sh
   ```

2. Configure the backend:
   ```bash
   cd backend
   cp env_template.txt .env
   # Edit .env with your Bungie API credentials
   ```

3. Start the backend server:
   ```bash
   cd backend
   source venv/bin/activate
   uvicorn main:app --reload --ssl-keyfile=../../dev-certs/key.pem --ssl-certfile=../../dev-certs/cert.pem
   ```

4. Start the frontend server:
   ```bash
   cd frontend
   HTTPS=true SSL_CRT_FILE=../../dev-certs/cert.pem SSL_KEY_FILE=../../dev-certs/key.pem npm start
   ```

5. Access the application at https://localhost:3000 

# Running the Destiny 2 Catalyst Tracker Web App Locally

This document provides instructions for setting up and running the frontend and backend servers for local development.

## Prerequisites

-   Node.js and npm installed
-   Python and pip installed
-   A Python virtual environment set up (e.g., in the root directory as `venv`)
-   Required Python packages installed (`pip install -r requirements.txt` in `web-app/backend`)
-   Required Node modules installed (`npm install` in `web-app/frontend`)
-   Environment variables configured in `web-app/backend/.env` (including Bungie API keys)

## HTTPS Setup (Crucial for Local Development)

The Bungie.net OAuth flow requires HTTPS callbacks. Therefore, **both the frontend and backend servers must run over HTTPS** for local development to work correctly.

This project uses self-signed certificates for local HTTPS.

1.  **Certificate Files:** Ensure `cert.pem` and `key.pem` files are present in the `web-app` directory. You can generate these using tools like OpenSSL or the provided `generate_cert.py` script (run from the `web-app` directory):
    ```bash
    cd web-app
    python generate_cert.py
    cd ..
    ```
    Or, generate them directly with OpenSSL:
    ```bash
    openssl req -x509 -newkey rsa:4096 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=localhost"
    ```

2.  **Backend Configuration:** `web-app/backend/main.py` is configured to automatically use these certificates if they exist when running `python main.py`.

3.  **Frontend Configuration:** `web-app/frontend/package.json` has its `start` script configured to use these certificates:
    ```json
    "start": "HTTPS=true SSL_CRT_FILE=$(pwd)/../cert.pem SSL_KEY_FILE=$(pwd)/../key.pem react-scripts start"
    ```

4.  **!!! BROWSER TRUST REQUIRED !!!:** Because the certificates are self-signed, your browser will not trust them by default. You **MUST** manually tell your browser to trust the certificate for the backend *once* after starting the servers:
    *   Start both servers (see below).
    *   Open your browser and navigate directly to the backend URL: **`https://localhost:8000`**
    *   You will see a security warning (e.g., "Your connection is not private").
    *   Click "Advanced".
    *   Click "Proceed to localhost (unsafe)" or "Accept the Risk and Continue".
    *   You only need to do this once per browser/profile until the certificate changes.
    *   Now you can load the frontend at `https://localhost:3000`.

## Running the Servers

**IMPORTANT:** Run each command from the project's root directory.

1.  **Start the Backend Server:**
    ```bash
    cd web-app/backend && source ../../venv/bin/activate && python main.py &
    cd ../..
    ```
    *(This activates the virtual environment, starts the server in the background, and returns you to the root directory)*

2.  **Start the Frontend Server:**
    ```bash
    cd web-app/frontend && npm start &
    cd ../..
    ```
    *(This starts the React development server in the background and returns you to the root directory)*

Both servers will now be running:
*   Backend: `https://localhost:8000`
*   Frontend: `https://localhost:3000`

## Troubleshooting Common Issues

1.  **"Certificate Invalid" / SSL Errors / Connection Refused:**
    *   Ensure **both** servers are running.
    *   Ensure `cert.pem` and `key.pem` exist in the `web-app` directory.
    *   Make sure you have manually trusted the certificate for `https://localhost:8000` in your browser (see Step 4 in HTTPS Setup).
    *   Verify the API URL in the frontend code points to `https://localhost:8000`.

2.  **OAuth "State parameter mismatch":**
    *   This usually means an old OAuth state is stuck in your browser from a previous attempt.
    *   **Fix:** Clear Local Storage for `https://localhost:3000` in your browser's developer tools (Application tab -> Local Storage -> Right-click on `https://localhost:3000` -> Clear).
    *   Close extra tabs of the application and try logging in again.

3.  **`npm start` fails with ENOENT / Cannot find package.json:**
    *   Make sure you are running `npm start` from *within* the `web-app/frontend` directory.

4.  **Backend fails with "Address already in use":**
    *   Another process (likely a previous instance of the backend) is using port 8000.
    *   Stop the old process (e.g., `pkill -f "python main.py"`) and try starting the backend again.

5.  **Frontend asks "run the app on another port instead?":**
    *   Another process (likely a previous instance of the frontend) is using port 3000.
    *   Stop the old process (e.g., `pkill -f "react-scripts start"`) or choose 'Y' to use a different port (but remember to access it via that new port). 