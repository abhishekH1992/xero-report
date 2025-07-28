# Multi-App Xero Implementation Plan

## Overview
This plan outlines the implementation strategy for handling 76 Xero organizations across 4 Xero apps, as uncertified Xero apps have a limit of 25 organizations per app.

## Current State Analysis
- Single Xero app configuration with one client ID and secret
- Database schema with `xero_connections` table storing tenant connections
- OAuth2 flow handling with token management
- API calls using single app credentials

## Implementation Plan

### Phase 1: Environment Configuration

#### 1.1 Update Environment Variables
Add configuration for 4 Xero apps in `.env`:

```env
# Xero App 1 Configuration
XERO_APP1_CLIENT_ID=your_app1_client_id
XERO_APP1_CLIENT_SECRET=your_app1_client_secret

# Xero App 2 Configuration
XERO_APP2_CLIENT_ID=your_app2_client_id
XERO_APP2_CLIENT_SECRET=your_app2_client_secret



# App Distribution Strategy (optional)
# Format: tenant_id:app_id,tenant_id:app_id
XERO_TENANT_APP_MAPPING=
```

#### 1.2 Update Configuration Class
- Modify `app/config.py` to support multiple app configurations
- Add app selection logic based on tenant distribution

### Phase 2: Database Schema Updates

#### 2.1 Add App ID Column
Add `app_id` column to `xero_connections` table:

```sql
ALTER TABLE xero_connections ADD COLUMN app_id INTEGER NOT NULL DEFAULT 1;
CREATE INDEX idx_xero_connections_app_id ON xero_connections(app_id);
```

#### 2.2 Update Database Models
- Update `XeroConnection` model in `app/database/models.py`
- Add app_id field with proper indexing
- Update repository methods to handle app_id

### Phase 3: Multi-App Service Architecture

#### 3.1 Create App Configuration Manager
Create `app/services/xero_app_manager.py`:
- Manage app configurations
- Distribute tenants across apps
- Handle app selection logic
- Provide app credentials based on tenant/app_id

#### 3.2 Update XeroAuthService
- Modify to accept app_id parameter
- Use correct app credentials for OAuth2 flows
- Update token management per app
- Handle app-specific error scenarios

#### 3.3 Update API Endpoints
- Modify auth endpoints to handle app_id
- Update callback handling for multiple apps
- Add app management endpoints

### Phase 4: Tenant Distribution Strategy

#### 4.1 Automatic Distribution
Implement automatic tenant distribution:
- Round-robin distribution across 2 apps
- Load balancing based on current app usage
- Fallback mechanisms for app failures

#### 4.2 Manual Override
Allow manual tenant-to-app assignment:
- Configuration-based mapping
- Admin interface for reassignment
- Migration tools for existing tenants

### Phase 5: Token Management Enhancement

#### 5.1 Per-App Token Storage
- Store tokens with app_id association
- Handle app-specific token refresh
- Implement app-aware token validation

#### 5.2 Token Migration
- Migrate existing tokens to app_id=1 (default)
- Provide migration scripts for data consistency
- Handle token refresh during migration

### Phase 6: API Call Management

#### 6.1 App-Aware API Calls
- Update all Xero API calls to use correct app credentials
- Implement app selection logic in service layer
- Handle app-specific rate limiting

#### 6.2 Error Handling
- Handle app-specific errors (app limits, invalid credentials)
- Implement fallback mechanisms
- Log app-specific issues

### Phase 7: Monitoring and Logging

#### 7.1 Enhanced Logging
- Add app_id to all API logs
- Track app usage and performance
- Monitor app-specific error rates

#### 7.2 Health Checks
- Implement per-app health checks
- Monitor app credential validity
- Alert on app-specific issues

## Implementation Steps

### Step 1: Environment Setup
1. Create 4 Xero apps in Xero Developer Portal
2. Update `.env` with all app credentials
3. Test individual app configurations

### Step 2: Database Migration
1. Create migration script for app_id column
2. Update existing records with default app_id=1
3. Test database schema changes

### Step 3: Configuration Updates
1. Update `config.py` for multi-app support
2. Create app manager service
3. Test configuration loading

### Step 4: Service Layer Updates
1. Update `XeroAuthService` for multi-app support
2. Modify repository methods
3. Update API endpoints

### Step 5: Testing and Validation
1. Test OAuth2 flow with each app
2. Validate token management per app
3. Test API calls with correct app credentials

### Step 6: Deployment
1. Deploy database migrations
2. Update application with new configuration
3. Monitor for issues

## Risk Mitigation

### App Limits
- Monitor app usage to stay under 25 org limit
- Implement alerts when approaching limits
- Plan for app expansion if needed

### Token Management
- Ensure proper token isolation between apps
- Handle app-specific token refresh failures
- Implement retry mechanisms

### Data Consistency
- Maintain data integrity during migration
- Backup existing data before changes
- Test rollback procedures

## Monitoring and Maintenance

### Key Metrics
- Per-app organization count
- App-specific API call success rates
- Token refresh success rates per app
- App credential expiration monitoring

### Maintenance Tasks
- Regular app credential rotation
- Monitor app usage trends
- Clean up expired tokens per app
- Update tenant distribution as needed

## Future Considerations

### Scaling Beyond 4 Apps
- Design for easy app addition
- Implement dynamic app configuration
- Plan for automated app provisioning

### App Certification
- Consider pursuing Xero app certification
- Plan for higher organization limits
- Maintain backward compatibility

## Success Criteria

1. All 76 organizations successfully distributed across 4 apps
2. OAuth2 flow works correctly for each app
3. API calls use correct app credentials
4. Token management works per app
5. No data loss during migration
6. Monitoring and alerting in place
7. Documentation updated for multi-app support