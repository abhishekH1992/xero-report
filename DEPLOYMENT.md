# Deployment Guide for Fly.io

This guide will help you deploy your Finance Assistant API to Fly.io.

## Prerequisites

1. **Fly.io CLI**: Install the Fly CLI
   ```bash
   # macOS
   brew install flyctl
   
   # Or download from https://fly.io/docs/hands-on/install-flyctl/
   ```

2. **Fly.io Account**: Sign up at https://fly.io and authenticate
   ```bash
   fly auth login
   ```

## Pre-deployment Setup

### 1. Update Environment Variables

Create a production `.env` file or set environment variables in Fly.io:

```bash
# Set your Xero credentials
fly secrets set XERO_CLIENT_ID="your_xero_client_id"
fly secrets set XERO_CLIENT_SECRET="your_xero_client_secret"
fly secrets set XERO_REDIRECT_URI="https://your-app-name.fly.dev/api/v1/auth/callback"

# Set API keys (comma-separated)
fly secrets set API_KEYS="your-api-key-1,your-api-key-2"

# Set production settings
fly secrets set DEBUG="false"
fly secrets set APP_NAME="Finance Assistant"
```

### 2. Create Database Volume

Create a persistent volume for your SQLite database:

```bash
fly volumes create finance_assistant_data --size 1 --region iad
```

## Deployment Steps

### 1. Deploy the Application

```bash
# Deploy to Fly.io
fly deploy

# Or if you want to specify a region
fly deploy --region iad
```

### 2. Verify Deployment

```bash
# Check app status
fly status

# View logs
fly logs

# Open the app in browser
fly open
```

### 3. Scale (Optional)

```bash
# Scale to multiple instances
fly scale count 2

# Scale memory/CPU if needed
fly scale vm shared-cpu-1x --memory 1024
```

## Post-deployment Configuration

### 1. Update Xero App Settings

1. Go to your Xero Developer Portal
2. Update your app's redirect URI to: `https://your-app-name.fly.dev/api/v1/auth/callback`
3. Save the changes

### 2. Test the Application

1. Visit `https://your-app-name.fly.dev/health` to check health
2. Visit `https://your-app-name.fly.dev/docs` to see API documentation
3. Test the authentication flow

## Monitoring and Maintenance

### View Logs
```bash
fly logs
fly logs --follow  # Follow logs in real-time
```

### Check App Status
```bash
fly status
fly ps
```

### Update Environment Variables
```bash
fly secrets set VARIABLE_NAME="new_value"
```

### Redeploy
```bash
fly deploy
```

## Troubleshooting

### Common Issues

1. **Database Connection**: Ensure the volume is properly mounted
2. **Environment Variables**: Check if all secrets are set correctly
3. **Port Configuration**: Verify the app is listening on port 8000
4. **Health Checks**: Check if the `/health` endpoint is responding

### Debug Commands

```bash
# SSH into the running container
fly ssh console

# Check environment variables
fly ssh console -C "env"

# Check database file
fly ssh console -C "ls -la /app/database/"
```

## Security Considerations

1. **API Keys**: Use strong, unique API keys in production
2. **CORS**: Update CORS settings to only allow your frontend domain
3. **Rate Limiting**: Monitor rate limiting effectiveness
4. **HTTPS**: Fly.io automatically provides HTTPS

## Cost Optimization

1. **Auto-scaling**: The app is configured to scale to 0 when not in use
2. **Resource Limits**: Start with minimal resources and scale as needed
3. **Monitoring**: Use Fly.io's built-in monitoring to track usage

## Backup Strategy

The SQLite database is stored in a persistent volume. For additional backup:

1. **Database Backup**: Periodically backup the database file
2. **Configuration**: Keep environment variables documented
3. **Code**: Use Git for version control

## Support

- [Fly.io Documentation](https://fly.io/docs/)
- [Fly.io Community](https://community.fly.io/)
- [FastAPI Documentation](https://fastapi.tiangolo.com/) 