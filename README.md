# Destiny 2 Catalyst Tracker & AI Assistant

A modern web and desktop tool for tracking Destiny 2 catalysts, featuring an AI assistant with Destiny character personas, emoji-rich responses, and deep integration with Bungie.net and community Google Sheets.

---

## Features
- **AI Chat Assistant**: Ask questions about catalysts, weapons, and Destiny 2 using natural language.
- **Persona System**: Choose from Destiny characters (Saint-14, Cayde-6, Ikora, etc.) for unique, emoji-filled responses.
- **Google Sheets Integration**: Pulls curated weapon and endgame data from public and private Google Sheets (service account support).
- **Session Longevity**: JWT refresh endpoint keeps you logged in for 24h+ without repeated Bungie logins.
- **Frontend Persona Dropdown**: Instantly switch the agent's personality in the chat UI.
- **Secure Token Handling**: Refresh tokens and sensitive credentials are never exposed to the frontend or committed to git.
- **Dark/Light Theme**: Modern, responsive UI for desktop and mobile.
- **Cross-Platform**: Web (React + FastAPI) and legacy desktop (Python CLI) versions.

---

## Repository Structure
- `web-app/` — Modern web application (React frontend, FastAPI backend)
- `desktop-app/` — Legacy terminal-based Python app
- `common/` — Shared resources (data, manifest, etc.)

---

## Quick Start (Web App)

### 1. Clone & Setup
```bash
git clone https://github.com/yourusername/destiny2-catalyst-tracker.git
cd destiny2-catalyst-tracker
cd web-app
```

### 2. Install Dependencies
- **Backend:**
  ```bash
  python3 -m venv venv
  source venv/bin/activate
  pip install -r requirements.txt
  ```
- **Frontend:**
  ```bash
  cd frontend
  npm install
  ```

### 3. Google Sheets API Setup (for Endgame Analysis)
- Create a Google Cloud project and enable the Sheets API.
- Download your `service_account.json` and place it in `web_app/backend/`.
- **Share** the relevant Google Sheets with your service account email.
- **Never commit** `service_account.json` (it's in `.gitignore`).

### 4. SSL Certificates (for HTTPS)
- Install [mkcert](https://github.com/FiloSottile/mkcert#installation) and run:
  ```bash
  mkcert -cert-file web_app/cert.pem -key-file web_app/key.pem localhost 127.0.0.1 ::1
  ```

### 5. Run Backend
```bash
source venv/bin/activate
PYTHONPATH=. uvicorn web_app.backend.main:app --reload --ssl-keyfile=web_app/key.pem --ssl-certfile=web_app/cert.pem --port 8000
```

### 6. Run Frontend
```bash
cd web_app/frontend
npm start
```

---

## Persona System
- Select your favorite Destiny character in the chat UI dropdown (Saint-14, Cayde-6, Ikora, Saladin, Zavala, Eris Morn, Shaxx, Drifter, Mara Sov).
- The AI assistant will respond in that character's style, using relevant Destiny-themed emojis liberally (e.g., 🛡️, 🐔, ✨, 🪖).
- Persona selection is sent with each chat request and dynamically changes the agent's system prompt.

---

## Google Sheets Integration
- The backend uses a Google service account to access public and shared Destiny 2 spreadsheets.
- Sheets are used for:
  - **Endgame Analysis**: Dynamic sheet discovery, fuzzy sheet name matching, and caching.
  - **PvE BiS Lists**: Community-curated weapon recommendations by type and activity.
- Sheet data is cached for performance and freshness.
- **Sensitive files** (`service_account.json`, `credentials.json`) are never committed and are listed in `.gitignore`.

---

## Session & Authentication Flow
- **OAuth2 with Bungie.net**: Secure login, access token (1h), refresh token (90d, backend only).
- **JWT (24h)**: Issued to frontend for API calls. When expired, the frontend calls `/auth/refresh` to get a new JWT (no Bungie login required if refresh token is valid).
- **No more repeated logins**: As long as your refresh token is valid, you stay logged in for days.
- **Sensitive tokens** are never sent to the frontend or stored in git.

---

## Security & Sensitive Files
- **Never commit** `service_account.json`, `credentials.json`, or any private keys. These are in `.gitignore` by default.
- If you see these files in `git status`, remove them from staging with `git reset` or `git rm --cached`.
- Share your Google Sheet with the service account email, not your personal account.

---

## Development & Testing
- **Backend tests:**
  ```bash
  cd web_app/backend
  source venv/bin/activate
  pytest
  ```
- **Frontend tests:**
  ```bash
  cd web_app/frontend
  npm test
  ```

---

## Legacy Desktop App
- See `desktop-app/README.md` for CLI usage.

---

## License
MIT — see [LICENSE](LICENSE)

---

## Troubleshooting
- **Bungie login loop?** Make sure your backend is running with HTTPS and your JWT/refresh logic is up to date.
- **Google Sheets errors?** Ensure your service account is shared on the sheet and the file is not committed.
- **Persona not working?** Make sure you're selecting a persona in the chat UI and the backend is restarted after updates.

---

## Contributors
- [Your Name Here]
- [Contributors...]

# Destiny 2 Catalysts & Weapon Inventory Sync

This project syncs your Destiny 2 catalyst progress and detailed weapon inventory (including perks) to a Supabase database using the Bungie API and a manifest service.

## Key Features
- **Catalyst Sync:** Tracks catalyst completion and objectives for your account.
- **Weapon Inventory Sync:** Extracts all perks, mods, shaders, and intrinsic frames for each weapon instance, using up-to-date manifest data.
- **Supabase Integration:** Data is upserted into normalized tables for easy querying and analysis.
- **Async API Calls:** Both catalyst and weapon sync now use robust async patterns for reliability and performance.
- **Dynamic Membership Info:** No more hardcoded membership IDs—your membership is fetched dynamically from Bungie.
- **Improved Error Handling:** All API calls use retry logic and handle Bungie API instability gracefully.

## Requirements
- Python 3.11+
- [Supabase Python Client](https://github.com/supabase-community/supabase-py)
- Bungie API Key (set in `.env` as `BUNGIE_API_KEY`)
- Supabase project and service role key (set in `.env`)
- Valid Bungie OAuth token (see `token.json`)

## Setup
1. **Clone the repo and install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```
2. **Configure your `.env` file:**
   - `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `BUNGIE_API_KEY`
3. **Authenticate with Bungie:**
   - Use the provided OAuth flow to generate a valid `token.json`.
4. **Run the sync script:**
   ```bash
   python scripts/sync_user_data.py
   ```
   - This will update both catalyst and weapon tables in Supabase.

## Database Schema
- See `supabase/migrations/user_weapon_inventory_schema.json` for the latest weapon inventory schema.
- If you change the schema, create and apply a new SQL migration in `supabase/migrations/`.

## Recent Changes
- **2024-05:**
  - Refactored `WeaponAPI` to be fully async and match `CatalystAPI` patterns.
  - Removed hardcoded membership info; now fetched dynamically.
  - Improved error handling and retry logic for all Bungie API calls.
  - Fixed manifest service calls to use `asyncio.to_thread` for async compatibility.
  - Removed component 300 from weapon profile fetch for improved API stability.

## Troubleshooting
- If you see repeated 500 errors from Bungie, try again later—API instability is common.
- Ensure your OAuth token is valid and not expired.
- Check Supabase table structure matches the latest schema.

## Contributing
PRs and issues welcome!

## Unified Development Workflow

To start both the backend (FastAPI, with SSL for Bungie API compatibility) and the frontend (React) in development mode, use the new root-level script:

```bash
npm run dev
```

- Run this command from the project root (`/Users/davehiltbrand/Documents/destiny2_catalysts`).
- This will start both servers in parallel, with output in the same terminal.
- The backend will use SSL certificates from `web_app/cert.pem` and `web_app/key.pem`.
- The old `dev` script in `web_app/frontend/package.json` has been removed to avoid confusion.

**Tip:** If you see errors about missing dependencies (e.g., `remark-gfm`, `rehype-raw`), run `npm install` in `web_app/frontend` to install them.

# Python Environment & Dependency Management

This project now uses [uv](https://github.com/astral-sh/uv) as the official Python dependency and environment manager. All developers should use uv for creating virtual environments and managing dependencies.

### Getting Started

1. **Install uv (recommended via pipx):**
   ```bash
   pipx install uv
   ```
   If you don't have pipx:
   ```bash
   brew install pipx
   pipx ensurepath
   # Restart your terminal or run: source ~/.zshrc
   pipx install uv
   ```

2. **Create a virtual environment:**
   ```bash
   uv venv .venv
   source .venv/bin/activate
   ```

3. **Install dependencies:**
   ```bash
   uv pip install
   ```
   This will install all dependencies listed in `pyproject.toml` and lock them in `uv.lock`.

4. **Add new dependencies:**
   ```bash
   uv pip install <package>
   ```
   This will update both `pyproject.toml` and `uv.lock`.

5. **Run your app/scripts as usual.**

---

**Note:**
- Do not use `pip`, `pipenv`, or `venv` directly for this project.
- All dependency and environment management should be done with uv.
- If you are migrating from pip, ensure your dependencies are listed in `pyproject.toml` under `[project] dependencies`.

---

## Supabase Auth Migration & User Management

**All user, session, and token management is now handled via Supabase Auth and user metadata.**

- Bungie OAuth tokens and Bungie ID are stored in the `raw_user_meta_data` field of the Supabase `auth.users` table.
- The backend no longer uses SQLite or SQLAlchemy for user/session/token management.
- All authentication, session, and token operations are performed using Supabase Auth and the Supabase Python client.

### Migrating Existing Data

If you have existing user/token data in the old SQLite database (`catalysts.db`), use the migration script:

```bash
python scripts/migrate_sqlite_users_to_supabase.py
```

This script reads from `users_for_supabase_migration.csv` (exported from SQLite) and updates Supabase user metadata for each user.

### Deleting the Old SQLite Database

Once you have confirmed that all user/token data has been migrated and the application is running correctly with Supabase Auth:

1. **Delete the old SQLite database file:**
   ```bash
   rm catalysts.db
   ```
2. **Remove any obsolete code or references to SQLite/SQLAlchemy user management.**
   - The backend codebase has already been refactored to remove these dependencies.

### Troubleshooting
- If you encounter issues with authentication or token refresh, ensure that the Supabase environment variables are set correctly and that user metadata is being updated as expected.
- All user management, authentication, and token refresh logic is now handled via Supabase Auth and user metadata.

---

## Prompt Management (YAML-based)

All agent and persona prompt strings are now managed in a single YAML file:

```
web_app/backend/prompts.yaml
```

### How it works
- **System prompts, persona instructions, and agent guidance** are defined in this YAML file.
- The backend loads all prompts from YAML at startup (see `agent_service.py`).
- To **add or edit a persona or system prompt**, simply update `prompts.yaml`.
- No code changes are required for prompt tweaks—just edit the YAML and restart the backend if needed.

### Example structure
```yaml
default:
  identity: "..."
  core_abilities: "..."
  supabase_access: "..."
  emoji_encouragement: "..."
personas:
  Saint-14: "..."
  Cayde-6: "..."
  Ikora: "..."
```

### Adding a new persona
1. Add a new entry under `personas:` in `prompts.yaml`.
2. Use the persona name as the key and provide the prompt string as the value.
3. Restart the backend to pick up the new persona.

### Why YAML?
- Centralizes all prompt text for easy editing and versioning.
- Enables non-developers to update prompts without touching code.
- Prepares the project for future integration with prompt management tools like LangSmith. 