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