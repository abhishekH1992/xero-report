# Multi-App Xero Integration - Quick Reference

## Environment Setup

### 1. Update .env File
Add the following to your `.env` file:

```env
# Xero App 1 Configuration
XERO_APP1_CLIENT_ID=your_app1_client_id
XERO_APP1_CLIENT_SECRET=your_app1_client_secret

# Xero App 2 Configuration
XERO_APP2_CLIENT_ID=your_app2_client_id
XERO_APP2_CLIENT_SECRET=your_app2_client_secret

# Xero App 3 Configuration
XERO_APP3_CLIENT_ID=your_app3_client_id
XERO_APP3_CLIENT_SECRET=your_app3_client_secret

# Xero App 4 Configuration
XERO_APP4_CLIENT_ID=your_app4_client_id
XERO_APP4_CLIENT_SECRET=your_app4_client_secret

# App Distribution Strategy
XERO_APP_DISTRIBUTION_MODE=round_robin
XERO_TENANT_APP_MAPPING=
```

### 2. Run Database Migration
```bash
python scripts/migrate_to_multi_app.py
```

## API Endpoints

### Authentication

#### Start OAuth2 Flow for Specific App
```http
GET /api/v1/auth/login/{app_id}
```
- `app_id`: 1-4 (Xero app ID)
- Returns authorization URL for the specified app

#### Handle OAuth2 Callback
```http
GET /api/v1/auth/callback?code={code}&state={state}&app_id={app_id}
```
- `app_id`: 1-4 (Xero app ID)
- Exchanges authorization code for tokens using the specified app

#### Refresh Token
```http
POST /api/v1/auth/refresh/{tenant_id}?app_id={app_id}
```
- `app_id`: Optional (1-4)
- Refreshes token for the specified tenant and app

### Connection Management

#### List Connections
```http
GET /api/v1/auth/connections?app_id={app_id}
```
- `app_id`: Optional (1-4) - Filter by app
- Returns all connections, optionally filtered by app

#### Get Connection Details
```http
GET /api/v1/auth/connections/{tenant_id}?app_id={app_id}
```
- `app_id`: Optional (1-4)
- Returns connection details for specific tenant and app

#### Delete Connection
```http
DELETE /api/v1/auth/connections/{tenant_id}?app_id={app_id}
```
- `app_id`: Optional (1-4)
- Deletes connection for specific tenant and app

### Reports

#### Aged Receivables Report
```http
GET /api/v1/reports/aged-receivables?app_id={app_id}
```
- `app_id`: Optional (1-4) - Filter by app
- Generates aged receivables report for connections in the specified app

### Statistics

#### App Statistics
```http
GET /api/v1/auth/app-stats
```
- Returns connection count per app
- Shows distribution mode and total connections

## Code Examples

### Using XeroAuthService

```python
from app.services.xero_auth import XeroAuthService
from app.database.repository import XeroAuthRepository

# Initialize service
repo = XeroAuthRepository(db_session)
auth_service = XeroAuthService(repo)

# Generate auth URL for app 2
auth_url, auth_state = auth_service.generate_auth_url(app_id=2)

# Exchange code for tokens using app 2
token_response = await auth_service.exchange_code_for_tokens(code, state, app_id=2)

# Save connection with app_id
connection = auth_service.save_connection(
    tenant_id="tenant123",
    tenant_name="My Company",
    token_response=token_response,
    app_id=2
)

# Get connection by tenant and app
connection = auth_service.get_connection("tenant123", app_id=2)

# Get all connections for app 3
connections = auth_service.get_connections_by_app(3)
```

### Using XeroAppManager

```python
from app.services.xero_app_manager import XeroAppManager

# Initialize app manager
app_manager = XeroAppManager()

# Get app configuration
config = app_manager.get_app_config(2)
client_id = config["client_id"]
client_secret = config["client_secret"]

# Get app ID for tenant (with distribution logic)
app_id = app_manager.get_app_id_for_tenant("tenant123", existing_connections)

# Get app statistics
stats = app_manager.get_app_stats(connections)
# Returns: {1: 5, 2: 3, 3: 4, 4: 2}
```

## Database Schema

### XeroConnection Table
```sql
CREATE TABLE xero_connections (
    id INTEGER PRIMARY KEY,
    tenant_id VARCHAR(255) NOT NULL,
    app_id INTEGER NOT NULL DEFAULT 1,
    tenant_name VARCHAR(255) NOT NULL,
    access_token TEXT NOT NULL,
    refresh_token TEXT NOT NULL,
    expires_at DATETIME NOT NULL,
    scope VARCHAR(500) NOT NULL,
    business_type VARCHAR(255) DEFAULT 'Commercial Properties',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    is_active BOOLEAN DEFAULT TRUE,
    UNIQUE(tenant_id, app_id)
);

-- Indexes
CREATE INDEX idx_xero_connections_app_id ON xero_connections(app_id);
CREATE INDEX idx_xero_connections_tenant_app ON xero_connections(tenant_id, app_id);
```

## Distribution Strategies

### Round Robin (Default)
- Distributes tenants evenly across apps
- Automatically balances load

### Load Balanced
- Considers active connections only
- Distributes based on current usage

### Manual Mapping
- Use `XERO_TENANT_APP_MAPPING` environment variable
- Format: `tenant_id:app_id,tenant_id:app_id`
- Example: `tenant1:2,tenant2:3,tenant3:1`

## Monitoring

### Key Metrics
- Connection count per app
- Token refresh success rate per app
- API call success rate per app
- App-specific error rates

### Health Checks
- Monitor app credential validity
- Check app usage limits (25 orgs per app)
- Alert on app-specific issues

## Troubleshooting

### Common Issues

1. **Invalid app_id error**
   - Ensure app_id is between 1-4
   - Check that app credentials are configured in .env

2. **Connection not found**
   - Verify tenant_id and app_id combination exists
   - Check if connection is active

3. **Token refresh fails**
   - Verify app credentials are correct
   - Check if refresh token is valid

4. **Database migration issues**
   - Run migration script: `python scripts/migrate_to_multi_app.py`
   - Check database permissions

### Debug Commands

```bash
# Check app statistics
curl "http://localhost:8000/api/v1/auth/app-stats"

# List connections for app 2
curl "http://localhost:8000/api/v1/auth/connections?app_id=2"

# Test OAuth2 flow for app 3
curl "http://localhost:8000/api/v1/auth/login/3"
```

## Migration Checklist

- [ ] Create 4 Xero apps in Developer Portal
- [ ] Update .env with all app credentials
- [ ] Run database migration script
- [ ] Test OAuth2 flow for each app
- [ ] Verify token management per app
- [ ] Test API calls with correct credentials
- [ ] Monitor app usage and distribution
- [ ] Update documentation

## Support

For issues or questions:
1. Check the logs for app-specific errors
2. Verify app credentials in .env
3. Test individual app OAuth2 flows
4. Monitor app statistics endpoint 