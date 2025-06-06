#!/bin/sh

rm instance/bcpea.db

# Create virtual environment
python -m venv venv

# Activate virtual environment
. venv/bin/activate

# Install required packages
pip install --upgrade pip
pip install flask requests beautifulsoup4 lxml #python-dotemail

# Create necessary directories
mkdir -p instance templates static/css static/js

echo "Setup complete. Activate virtual environment with: source venv/bin/activate"

