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

### Web Application

1. Start the backend server:
```bash
cd web-app/backend
source venv/bin/activate  # On Windows: .\venv\Scripts\activate
uvicorn main:app --reload
```

2. Start the frontend development server:
```bash
cd web-app/frontend
npm run dev
```

The web application will be available at `http://localhost:3000`

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