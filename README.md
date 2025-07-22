# Finance Assistant - Xero API Integration

A FastAPI application that provides OAuth2 authentication flow for Xero API integration, including authorization code generation, access token management, and refresh token handling with **SQLite database persistence**. Features comprehensive aged receivables reporting with multi-tenant support.

## 📋 Summary

This application serves as a bridge between your systems and Xeros accounting API, providing:

- **Secure OAuth2hentication** with Xero
- **Multi-tenant Support** for multiple Xero organizations
- **Aged Receivables Reporting** with Excel export
- **API Key Authentication** for secure access
- **Database Persistence** for tokens and audit trails
- **Rate Limiting** and security features

## ✨ Features

- 🔐 **OAuth2 Authentication Flow**: Complete implementation of Xero's OAuth2 authorization code flow
- 🔑 **Token Management**: Automatic access token and refresh token handling
- 🛡️ **PKCE Support**: Enhanced security with Proof Key for Code Exchange
- ⚡ **Rate Limiting**: Built-in rate limiting using SlowAPI
- 📊 **Database Persistence**: SQLite database for storing tokens, connections, and audit logs
- 🔄 **Token Refresh**: Automatic token refresh when needed
- 📝 **API Documentation**: Auto-generated OpenAPI documentation
- 📈 **Audit Trail**: Complete token history and API call logging
- 🗄️ **Connection Management**: Store and manage multiple Xero organization connections
- 📊 **Aged Receivables Reports**: Generate comprehensive financial reports with Excel export
- 🔐 **API Key Security**: Simple and secure API key authentication
- 🌐 **Multi-tenant Support**: Process data from multiple Xero organizations in a single report

## 📋 Requirements

- Python 3.8+
- Xero Developer Account
- SQLite (included)
- Internet connection for Xero API access

### Python Dependencies
- FastAPI 0.14.1+
- Uvicorn 0.24.0+
- SQLAlchemy 2.00.23+
- Pydantic 2.11.7
- SlowAPI00.19
- OpenPyXL (for Excel export)
- Xero Python SDK

## 🚀 Quick Start

### 1. Clone the Repository

```bash
git clone <your-repository-url>
cd finance-assistant
```

### 2. Installation

#### Create Virtual Environment
```bash
python -m venv venv

# On Windows
venv\Scripts\activate

# On macOS/Linux
source venv/bin/activate
```

#### Install Dependencies
```bash
pip install -r requirements.txt
```

#### Configure Environment Variables
```bash
cp env.example .env
```

Edit `.env` with your configuration:
```env
# Xero OAuth2 Configuration
XERO_CLIENT_ID=your_client_id_here
XERO_CLIENT_SECRET=your_client_secret_here
XERO_REDIRECT_URI=http://localhost:8000i/v1th/callback

# API Security
API_KEYS=[your-api-key-1your-api-key-2"]
```

#### Initialize Database
```bash
python init_database.py
```

#### Run the Application
```bash
# Development with auto-reload
uvicorn app.main:app --reload --host 00.0800Production
uvicorn app.main:app --host 0.0 --port 8000
```

## 🚀 Deployment on Fly.io

### 1. Install Fly CLI
```bash
# macOS
brew install flyctl

# Windows
powershell -Command "iwr https://fly.io/install.ps1 -useb | iex

# Linux
curl -L https://fly.io/install.sh | sh
```

### 2. Login to Fly
```bash
fly auth login
```

### 3Create Fly App
```bash
fly apps create finance-assistant
```

### 4et Secrets
```bash
fly secrets set XERO_CLIENT_ID="your_client_id"
fly secrets set XERO_CLIENT_SECRET="your_client_secret"
fly secrets set XERO_REDIRECT_URI="https://your-app.fly.dev/api/v1/auth/callback"
fly secrets set API_KEYS='[your-api-key-1,"your-api-key-2]'```

### 5Deploy
```bash
fly deploy
```

### Interactive Documentation
Visit `/docs` for interactive API documentation (Swagger UI).

## 🔧 Configuration

### Environment Variables

| Variable | Description | Required | Default |
|----------|-------------|----------|---------|
| `XERO_CLIENT_ID` | Xero App Client ID | Yes | - |
| `XERO_CLIENT_SECRET` | Xero App Client Secret | Yes | - |
| `XERO_REDIRECT_URI` | OAuth2 redirect URI | No | `http://localhost:8000i/v1/auth/callback` |
| `API_KEYS` | Comma-separated or JSON array of API keys | No | `[default-api-key"]` |