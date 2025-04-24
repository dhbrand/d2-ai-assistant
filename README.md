# Destiny 2 Catalyst Tracker Web Application

A modern web application for tracking Destiny 2 catalyst progress, built with React and FastAPI.

## Project Structure

```
web-app/
├── frontend/         # React frontend
└── backend/          # FastAPI backend
```

## Development Setup

### Backend Setup

1. Navigate to the backend directory:
   ```bash
   cd web-app/backend
   ```

2. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```

4. Create a `.env` file with your Bungie API credentials:
   ```
   BUNGIE_API_KEY=your_api_key
   BUNGIE_CLIENT_ID=your_client_id
   BUNGIE_CLIENT_SECRET=your_client_secret
   ```

5. Run the backend server:
   ```bash
   uvicorn main:app --reload
   ```

### Frontend Setup

1. Navigate to the frontend directory:
   ```bash
   cd web-app/frontend
   ```

2. Install dependencies:
   ```bash
   npm install
   ```

3. Start the development server:
   ```bash
   npm start
   ```

## Features

- Modern, responsive UI
- Real-time catalyst progress tracking
- Authentication with Bungie.net
- Progress visualization
- Search and filter functionality
- Cross-platform support

## Technology Stack

- Frontend:
  - React
  - Material-UI
  - Recharts
  - Axios

- Backend:
  - FastAPI
  - SQLAlchemy
  - Bungie API Integration

## Development Status

This is a work in progress. Current focus:
- [ ] Complete backend API implementation
- [ ] Implement frontend components
- [ ] Add authentication flow
- [ ] Implement data persistence
- [ ] Add progress visualization
- [ ] Implement search and filter functionality 