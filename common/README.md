# Common Resources

This directory contains shared resources used by both the desktop and web applications.

## Contents

- **data/**: Shared data files like the SQLite database, manifest content, and Bungie tokens
- **cert/**: Shared certificate files for HTTPS connections

## Database

The `data/catalysts.db` file contains SQLite database tables used by both applications:

- Users table: Stores user information and Bungie membership IDs
- Catalysts table: Stores catalyst definitions and progress
- Settings table: Stores application settings

## Usage

Both the desktop and web applications should reference the common resources from this directory using relative paths.
