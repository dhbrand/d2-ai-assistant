#!/bin/bash

# Exit on error
set -e

echo "Setting up development environment..."

# Backend setup
echo "Setting up backend..."
cd backend

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Install backend dependencies
echo "Installing backend dependencies..."
pip install -r requirements.txt

# Run backend tests
echo "Running backend tests..."
pytest

# Frontend setup
echo "Setting up frontend..."
cd ../frontend

# Install frontend dependencies
echo "Installing frontend dependencies..."
npm install

# Run frontend tests
echo "Running frontend tests..."
npm test

echo "Development environment setup complete!" 