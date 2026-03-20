#!/bin/bash
set -e

echo "Installing dependencies..."
npm ci --only=production --ignore-scripts

echo "Starting application..."
exec node src/index.js
