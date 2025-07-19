#!/usr/bin/env bash
# exit on error
set -o errexit

# Install dependencies
pip install -r requirements.txt

# Run database migrations
echo "Running database migrations..."
flask db upgrade

echo "Build completed successfully!"
