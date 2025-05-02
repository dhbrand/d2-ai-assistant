#!/bin/bash

# Exit on error
set -e

echo "Setting up Destiny 2 Catalyst Tracker desktop environment..."

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install dependencies
echo "Installing dependencies..."
pip install -r requirements.txt

# Run tests
echo "Running tests..."
python -m pytest tests/

echo "Desktop application setup complete!"
echo "To run the application: source venv/bin/activate && python desktop_app.py" 