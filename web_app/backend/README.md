# Destiny 2 Catalyst Tracker — Backend

This directory contains the FastAPI backend for the Destiny 2 Catalyst Tracker web application. It provides API endpoints, handles authentication, manages data with Supabase, and implements core logic for catalyst and weapon tracking.

## Key Files and Their Roles

- **main.py**: Entry point for the FastAPI app. Wires together all backend services, models, and endpoints.
- **agent_service.py**: Implements the main agent logic, including tool integrations (Google Sheets, Supabase sync, etc.) and orchestrates calls to weapon and catalyst APIs.
- **weapon_api.py**: Handles weapon-related API logic, including fetching weapon data from Bungie and Supabase.
- **catalyst.py**: Core logic for catalyst tracking and processing. Uses constants from `catalyst_hashes.py` to filter and process catalyst records.
- **catalyst_hashes.py**: Defines `CATALYST_RECORD_HASHES`, a dictionary of all known Destiny 2 catalyst record hashes (sourced from DIM and D2Checklist). This is used throughout `catalyst.py` to identify and process catalyst records.
- **manifest.py**: Provides services for accessing Destiny 2 manifest data, both from Supabase and (optionally) from a local SQLite manifest for data population scripts.
- **models.py**: Contains Pydantic models for weapons, catalysts, users, and related data structures.
- **bungie_oauth.py**: Manages OAuth2 authentication with Bungie.net, including token storage and refresh logic.

## Data Flow and Relationships

- `main.py` imports and initializes all major services and models.
- `agent_service.py` acts as the central orchestrator, calling into `weapon_api.py` and `catalyst.py` as needed.
- `catalyst.py` relies on `CATALYST_RECORD_HASHES` from `catalyst_hashes.py` to filter and process catalyst records.
- Manifest data is accessed via `manifest.py` (using Supabase as the primary backend).
- All persistent data (users, weapons, catalysts) is managed via Supabase tables.

## Constants and Data Files

- **CATALYST_RECORD_HASHES** (in `catalyst_hashes.py`):
  - A dictionary mapping Destiny 2 catalyst record hashes to weapon names.
  - Used in `catalyst.py` for filtering, validation, and processing of catalyst records.
  - Sourced from community tools (DIM, D2Checklist) and updated as new catalysts are released.

## Adding or Updating Catalyst Hashes

- To add new catalysts, update the `CATALYST_RECORD_HASHES` dictionary in `catalyst_hashes.py`.
- Ensure any new logic in `catalyst.py` references this constant for consistency.

## Developer Notes

- All backend dependencies are managed at the project root (`requirements.txt`).
- Virtual environments should be created at the root level.
- For OAuth and Supabase credentials, use the `.env` file at the project root.
- See the main project README for setup and environment instructions.

---

For questions or contributions, see the main project documentation or open an issue in the repository. 