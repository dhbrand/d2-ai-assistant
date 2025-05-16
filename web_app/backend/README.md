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

## API Performance Profiling & Optimization

The backend implements comprehensive performance profiling and optimization for all major API endpoints and external calls (Bungie, Supabase, LLM, etc.).

### Instrumentation & Logging
- All key backend operations are instrumented to log timing and profiling data to the `api_performance_logs` table in Supabase.
- The async helper function `log_api_performance` (see `performance_logging.py`) is used throughout the backend to record:
  - Endpoint and operation name
  - Duration (ms)
  - User, conversation, and message context (where available)
  - Extra data for debugging/alerting

### Granular Profiling
- The main chat endpoint and agent service (`run_chat`) log timing for each major sub-operation:
  - Weapon fetch
  - Catalyst fetch
  - Manifest lookups
  - LLM call
  - Total request duration
- All Bungie and Supabase API call sites are instrumented for latency tracking.

### Slow Request Alerting
- Any sub-operation or total request exceeding 10 seconds is logged as a `slow_request_alert` in Supabase, including full timing context for diagnosis.

### Caching & Optimization
- The backend uses in-memory and persistent (Supabase) caching for user, weapon, and catalyst data to minimize redundant API calls and improve response times.
- Refactoring and analysis of performance logs have eliminated unnecessary Bungie API calls and optimized request patterns.

### How to Use/Extend
- To add profiling to new endpoints or operations, import and call `log_api_performance` with the relevant context.
- Performance data can be queried in Supabase for ongoing monitoring and further optimization.

---

For questions or contributions, see the main project documentation or open an issue in the repository. 