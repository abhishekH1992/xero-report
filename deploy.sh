#!/bin/bash

# Finance Assistant API - Fly.io Deployment Script

set -e  # Exit on any error

echo "🚀 Starting deployment to Fly.io..."

# Check if flyctl is installed
if ! command -v flyctl &> /dev/null; then
    echo "❌ flyctl is not installed. Please install it first:"
    echo "   brew install flyctl"
    exit 1
fi

# Check if user is authenticated
if ! flyctl auth whoami &> /dev/null; then
    echo "❌ Not authenticated with Fly.io. Please run:"
    echo "   flyctl auth login"
    exit 1
fi

# Check if app exists
if ! flyctl apps list | grep -q "finance-assistant"; then
    echo "📝 Creating new Fly.io app..."
    flyctl apps create finance-assistant --org personal
fi

# Check if volume exists
if ! flyctl volumes list | grep -q "finance_assistant_data"; then
    echo "📦 Creating persistent volume..."
    flyctl volumes create finance_assistant_data --size 1 --region iad
fi

echo "🔧 Setting up environment variables..."
echo "Please make sure you have set the following secrets:"
echo "   - XERO_CLIENT_ID"
echo "   - XERO_CLIENT_SECRET"
echo "   - XERO_REDIRECT_URI"
echo "   - API_KEYS"
echo "   - DEBUG=false"
echo "   - APP_NAME=Finance Assistant"
echo ""
echo "You can set them using:"
echo "   flyctl secrets set VARIABLE_NAME=value"

# Deploy the application
echo "🚀 Deploying application..."
flyctl deploy

echo "✅ Deployment completed!"
echo ""
echo "🔗 Your app is available at: https://finance-assistant.fly.dev"
echo "📊 Check status with: flyctl status"
echo "📝 View logs with: flyctl logs"
echo "🌐 Open in browser with: flyctl open" 