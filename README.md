# Finance Assistant - Xero API Integration

A FastAPI application that provides OAuth2 authentication flow for Xero API integration, including authorization code generation, access token management, and refresh token handling with **SQLite database persistence**.

## Features

- 🔐 **OAuth2 Authentication Flow**: Complete implementation of Xero's OAuth2 authorization code flow
- 🔑 **Token Management**: Automatic access token and refresh token handling
- 🛡️ **PKCE Support**: Enhanced security with Proof Key for Code Exchange
- ⚡ **Rate Limiting**: Built-in rate limiting using SlowAPI
- 📊 **Database Persistence**: SQLite database for storing tokens, connections, and audit logs
- 🔄 **Token Refresh**: Automatic token refresh when needed
- 📝 **API Documentation**: Auto-generated OpenAPI documentation
- 📈 **Audit Trail**: Complete token history and API call logging
- 🗄️ **Connection Management**: Store and manage multiple Xero organization connections

## Quick Start

### 1. Install Dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure Environment Variables

Copy the example environment file and configure your Xero API credentials:

```bash
cp env.example .env
```

Edit `.env` with your Xero App credentials:

```env
XERO_CLIENT_ID=your_client_id_here
XERO_CLIENT_SECRET=your_client_secret_here
XERO_REDIRECT_URI=http://localhost:8000/api/v1/auth/callback
```

### 3. Initialize Database

```bash
python init_database.py
```

This will create the SQLite database and all necessary tables.

### 4. Run the Application

Using uvicorn (recommended):

```bash
# Development with auto-reload
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production
uvicorn app.main:app --host 0.0.0.0 --port 8000

# With specific workers
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

Or using Python directly:

```bash
python -m app.main
```

The API will be available at `http://localhost:8000`

## Complete OAuth2 Flow Example

### Step 1: Generate Authorization URL

```bash
# Get authorization URL
curl -X GET "http://localhost:8000/api/v1/auth/login"

# Response:
{
  "authorization_url": "https://login.xero.com/identity/connect/authorize?response_type=code&client_id=YOUR_CLIENT_ID&redirect_uri=http%3A//localhost%3A8000/api/v1/auth/callback&scope=offline_access%20accounting.transactions%20accounting.contacts&state=abc123...&code_challenge=xyz789...&code_challenge_method=S256",
  "state": "abc123...",
  "message": "Redirect to this URL to authenticate with Xero"
}
```

### Step 2: User Authentication

Redirect the user to the authorization URL. They will:
1. Log in to Xero
2. Grant permissions to your app
3. Be redirected back to your callback URL

### Step 3: Exchange Authorization Code for Tokens

When Xero redirects back, you'll receive a code and state:

```bash
# Xero redirects to: http://localhost:8000/api/v1/auth/callback?code=AUTH_CODE&state=abc123...

# Exchange code for tokens
curl -X GET "http://localhost:8000/api/v1/auth/callback?code=AUTH_CODE&state=abc123..."

# Response:
{
  "success": true,
  "message": "Successfully authenticated with Xero",
  "tenant": {
    "id": "YOUR_TENANT_ID",
    "name": "Your Organization Name"
  },
  "token_info": {
    "expires_at": "2024-01-15T10:30:00",
    "scope": "offline_access accounting.transactions accounting.contacts"
  }
}
```

### Step 4: Refresh Access Token

When the access token expires (usually 30 minutes), refresh it:

```bash
# Refresh token for a specific tenant
curl -X POST "http://localhost:8000/api/v1/auth/refresh/YOUR_TENANT_ID"

# Response:
{
  "message": "Token refreshed successfully",
  "tenant": {
    "id": "YOUR_TENANT_ID",
    "name": "Your Organization Name"
  },
  "token_info": {
    "expires_at": "2024-01-15T11:00:00",
    "scope": "offline_access accounting.transactions accounting.contacts"
  }
}
```

## Python Code Examples

### Complete OAuth2 Flow

```python
import httpx
import asyncio

async def complete_xero_auth_flow():
    """Complete OAuth2 flow with Xero"""
    
    async with httpx.AsyncClient() as client:
        # Step 1: Get authorization URL
        response = await client.get("http://localhost:8000/api/v1/auth/login")
        auth_data = response.json()
        
        print(f"Authorization URL: {auth_data['authorization_url']}")
        print(f"State: {auth_data['state']}")
        
        # Step 2: User should visit the authorization URL and authenticate
        # After authentication, Xero will redirect to your callback with code and state
        
        # Step 3: Exchange code for tokens (this happens in the callback)
        # The callback endpoint handles this automatically
        
        # Step 4: Check connections
        connections_response = await client.get("http://localhost:8000/api/v1/auth/connections")
        connections = connections_response.json()
        
        print(f"Active connections: {connections['count']}")
        
        # Step 5: Refresh token when needed
        if connections['connections']:
            tenant_id = connections['connections'][0]['tenant_id']
            
            refresh_response = await client.post(
                f"http://localhost:8000/api/v1/auth/refresh/{tenant_id}"
            )
            refresh_data = refresh_response.json()
            
            print(f"Token refreshed: {refresh_data['message']}")
            
            # Step 6: Get token history
            history_response = await client.get(
                f"http://localhost:8000/api/v1/auth/connections/{tenant_id}/history"
            )
            history = history_response.json()
            
            print(f"Token refresh history: {history['count']} records")

# Run the example
asyncio.run(complete_xero_auth_flow())
```

### JavaScript/HTML Example

```html
<!DOCTYPE html>
<html>
<head>
    <title>Xero Integration</title>
</head>
<body>
    <h1>Connect to Xero</h1>
    <button onclick="connectToXero()">Connect</button>
    <div id="status"></div>
    
    <script>
        async function connectToXero() {
            try {
                const response = await fetch('/api/v1/auth/login');
                const data = await response.json();
                
                document.getElementById('status').innerHTML = 
                    `<p>Redirecting to Xero...</p><p>State: ${data.state}</p>`;
                
                // Redirect to Xero
                window.location.href = data.authorization_url;
            } catch (error) {
                document.getElementById('status').innerHTML = 
                    `<p style="color: red;">Error: ${error.message}</p>`;
            }
        }
        
        // Check if we're returning from Xero
        const urlParams = new URLSearchParams(window.location.search);
        const code = urlParams.get('code');
        const state = urlParams.get('state');
        
        if (code && state) {
            // We're back from Xero, exchange code for tokens
            exchangeCodeForTokens(code, state);
        }
        
        async function exchangeCodeForTokens(code, state) {
            try {
                const response = await fetch(`/api/v1/auth/callback?code=${code}&state=${state}`);
                const data = await response.json();
                
                if (data.success) {
                    document.getElementById('status').innerHTML = 
                        `<p style="color: green;">✅ Connected to ${data.tenant.name}</p>
                         <p>Tenant ID: ${data.tenant.id}</p>
                         <p>Token expires: ${data.token_info.expires_at}</p>`;
                } else {
                    document.getElementById('status').innerHTML = 
                        `<p style="color: red;">❌ Authentication failed</p>`;
                }
            } catch (error) {
                document.getElementById('status').innerHTML = 
                    `<p style="color: red;">Error: ${error.message}</p>`;
            }
        }
    </script>
</body>
</html>
```

### Using the API with curl

```bash
# 1. Generate authorization URL
curl -X GET "http://localhost:8000/api/v1/auth/login"

# 2. List all connections
curl -X GET "http://localhost:8000/api/v1/auth/connections"

# 3. Get specific connection details
curl -X GET "http://localhost:8000/api/v1/auth/connections/YOUR_TENANT_ID"

# 4. Refresh token
curl -X POST "http://localhost:8000/api/v1/auth/refresh/YOUR_TENANT_ID"

# 5. Get token history
curl -X GET "http://localhost:8000/api/v1/auth/connections/YOUR_TENANT_ID/history?limit=5"

# 6. Get API logs
curl -X GET "http://localhost:8000/api/v1/auth/logs?limit=10"

# 7. Get connection statistics
curl -X GET "http://localhost:8000/api/v1/auth/stats"

# 8. Cleanup expired states
curl -X POST "http://localhost:8000/api/v1/auth/cleanup"
```

## Database Schema

The application uses SQLite with the following tables:

### `xero_auth_states`
- Stores OAuth2 state parameters for security
- Includes PKCE code verifiers
- Automatic expiration and cleanup

### `xero_connections`
- Stores Xero organization connections
- Access tokens, refresh tokens, and expiration times
- Soft delete support with `is_active` flag

### `xero_token_history`
- Audit trail of all token refreshes
- Stores token hashes (not actual tokens) for security
- Tracks refresh types: 'initial', 'refresh', 'renewal'

### `xero_api_logs`
- Logs all API calls to Xero
- Response times, status codes, and error messages
- Useful for monitoring and debugging

## Xero App Setup

1. Go to [Xero Developer Portal](https://developer.xero.com/)
2. Create a new app
3. Configure the redirect URI: `http://localhost:8000/api/v1/auth/callback`
4. Note down your Client ID and Client Secret

## API Endpoints

### Authentication Flow

#### 1. Generate Authorization URL
```http
GET /api/v1/auth/login
```

Returns an authorization URL that you can redirect users to for Xero authentication.

#### 2. Direct Redirect to Xero
```http
GET /api/v1/auth/login/redirect
```

Immediately redirects to Xero's login page.

#### 3. OAuth2 Callback
```http
GET /api/v1/auth/callback?code={auth_code}&state={state}
```

Handles the OAuth2 callback from Xero and exchanges the authorization code for tokens.

#### 4. HTML Callback (User-friendly)
```http
GET /api/v1/auth/callback/html?code={auth_code}&state={state}
```

Same as above but returns an HTML page for better user experience.

### Token Management

#### Refresh Access Token
```http
POST /api/v1/auth/refresh/{tenant_id}
```

Refreshes the access token for a specific tenant.

#### List Connections
```http
GET /api/v1/auth/connections
```

Lists all stored Xero connections from database.

#### Get Connection Details
```http
GET /api/v1/auth/connections/{tenant_id}
```

Get details for a specific connection.

#### Delete Connection
```http
DELETE /api/v1/auth/connections/{tenant_id}
```

Delete a stored connection.

#### Deactivate Connection (Soft Delete)
```http
POST /api/v1/auth/connections/{tenant_id}/deactivate
```

Deactivate a connection without deleting it.

### Audit and Monitoring

#### Get Token History
```http
GET /api/v1/auth/connections/{tenant_id}/history?limit=10
```

Get token refresh history for a connection.

#### Get API Logs
```http
GET /api/v1/auth/logs?tenant_id={tenant_id}&limit=50
```

Get API call logs with optional filtering by tenant.

#### Get Connection Statistics
```http
GET /api/v1/auth/stats
```

Get connection and API statistics.

#### Cleanup Expired States
```http
POST /api/v1/auth/cleanup
```

Clean up expired auth states from database.

## OAuth2 Flow Explanation

### Authorization Code Flow

1. **Generate Auth URL**: Create a secure authorization URL with state parameter and PKCE challenge
2. **User Authentication**: Redirect user to Xero login page
3. **Authorization Code**: Xero redirects back with an authorization code
4. **Token Exchange**: Exchange the authorization code for access and refresh tokens
5. **Store Connection**: Save the tokens and tenant information to database

### Important Notes

- **Authorization codes can only be used once** and expire quickly (usually 10 minutes)
- **State parameter** prevents CSRF attacks
- **PKCE (Proof Key for Code Exchange)** provides additional security
- **Refresh tokens** are long-lived and can be used to get new access tokens
- **Access tokens** expire after 30 minutes and need to be refreshed
- **Database persistence** ensures tokens survive application restarts

## Security Features

- **Rate Limiting**: Prevents abuse with configurable limits
- **State Validation**: Ensures OAuth2 state parameter integrity
- **PKCE Support**: Enhanced security for public clients
- **Token Expiration**: Automatic handling of token expiration
- **Database Storage**: Secure token storage with audit trail
- **Token Hashing**: History logs store token hashes, not actual tokens
- **Soft Delete**: Connections can be deactivated without data loss

## Development

### Project Structure

```
finance-assistant/
├── app/
│   ├── __init__.py
│   ├── main.py                 # FastAPI application
│   ├── config.py              # Configuration settings
│   ├── models/
│   │   ├── __init__.py
│   │   └── xero_auth.py       # Pydantic models
│   ├── services/
│   │   ├── __init__.py
│   │   └── xero_auth.py       # OAuth2 service logic
│   ├── database/
│   │   ├── __init__.py
│   │   ├── database.py        # Database connection
│   │   ├── models.py          # SQLAlchemy models
│   │   └── repository.py      # Database operations
│   └── api/
│       └── v1/
│           ├── __init__.py
│           └── endpoints/
│               ├── __init__.py
│               └── xero_auth.py # API endpoints
├── database/
│   └── finance_assistant.db   # SQLite database
├── requirements.txt
├── env.example
├── init_database.py           # Database initialization script
└── README.md
```

### Database Operations

The application uses a repository pattern for database operations:

```python
from app.database.repository import XeroAuthRepository
from app.database.database import get_db

# Get repository
db = next(get_db())
repo = XeroAuthRepository(db)

# Create connection
connection = repo.create_connection(
    tenant_id="your_tenant_id",
    tenant_name="Your Organization",
    access_token="access_token",
    refresh_token="refresh_token",
    expires_at=datetime.utcnow() + timedelta(hours=1),
    scope="offline_access accounting.transactions"
)

# Get connection
connection = repo.get_connection("your_tenant_id")

# Update tokens
repo.update_connection_tokens(
    tenant_id="your_tenant_id",
    access_token="new_access_token",
    refresh_token="new_refresh_token",
    expires_at=datetime.utcnow() + timedelta(hours=1),
    scope="offline_access accounting.transactions"
)
```

### Running Tests

```bash
# Install test dependencies
pip install pytest pytest-asyncio

# Run tests
pytest
```

### API Documentation

Once the application is running, visit:
- **Swagger UI**: `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

## Production Considerations

1. **Database**: Consider using PostgreSQL or MySQL for production
2. **Token Encryption**: Encrypt tokens in the database for additional security
3. **Environment Variables**: Use secure environment variable management
4. **HTTPS**: Always use HTTPS in production
5. **CORS**: Configure CORS properly for your domain
6. **Rate Limiting**: Adjust rate limits based on your needs
7. **Logging**: Add proper logging and monitoring
8. **Error Handling**: Implement comprehensive error handling
9. **Database Backups**: Regular database backups
10. **Connection Pooling**: Use connection pooling for database connections

## Troubleshooting

### Common Issues

1. **Invalid redirect URI**: Ensure the redirect URI in your Xero app matches exactly
2. **State parameter errors**: Check that state parameters are being handled correctly
3. **Token expiration**: Implement proper token refresh logic
4. **CORS issues**: Configure CORS settings for your frontend domain
5. **Database errors**: Ensure database is initialized with `python init_database.py`

### Debug Mode

Enable debug mode in your `.env` file:

```env
DEBUG=true
```

This will provide more detailed error messages and enable auto-reload during development.

### Database Inspection

You can inspect the SQLite database directly:

```bash
sqlite3 database/finance_assistant.db

# List tables
.tables

# View connections
SELECT tenant_id, tenant_name, expires_at FROM xero_connections;

# View recent API logs
SELECT endpoint, method, status_code, created_at FROM xero_api_logs ORDER BY created_at DESC LIMIT 10;
```

## License

This project is licensed under the MIT License. 