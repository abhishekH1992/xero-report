# Fly.io Debugging Guide

## Overview
This document contains comprehensive debugging commands and techniques for troubleshooting Fly.io deployment issues, particularly focusing on volume sharing, machine management, and database performance.

## Table of Contents
1. [Machine Management](#machine-management)
2. [Volume Management](#volume-management)
3. [Application Status](#application-status)
4. [Logs and Monitoring](#logs-and-monitoring)
5. [Database Debugging](#database-debugging)
6. [File Storage Issues](#file-storage-issues)
7. [API Testing](#api-testing)
8. [Common Issues and Solutions](#common-issues-and-solutions)

## Machine Management

### List All Machines
```bash
fly machines list
```

### Show Machine Details
```bash
fly machine show <machine_id>
# Example:
fly machine show 48e2590f356358
```

### Check Machine Status
```bash
fly machine status <machine_id>
# Example:
fly machine status 48e2590f356358
```

### Destroy Machine
```bash
fly machine destroy <machine_id>
# Example:
fly machine destroy 48e2590f356358
```

### Update Machine Configuration
```bash
fly machine update <machine_id> --volume <volume_name>:/app/storage/reports
# Example:
fly machine update 48e2590f356358 --volume shared_reports_volume:/app/storage/reports
```

## Volume Management

### List All Volumes
```bash
fly volumes list
```

### Create Volume
```bash
fly volumes create <volume_name> --size <size_gb> --region <region>
# Example:
fly volumes create shared_reports_volume --size 1 --region syd
```

### Destroy Volume
```bash
fly volumes destroy <volume_name>
# Example:
fly volumes destroy vol_4m8nwq50g0od8e1r
```

### Check Volume Details
```bash
fly volumes show <volume_name>
# Example:
fly volumes show shared_reports_volume
```

## Application Status

### Check App Status
```bash
fly status
```

### Show App Configuration
```bash
fly config show
```

### List All Apps
```bash
fly apps list
```

## Scaling and Deployment

### Scale Machine Count
```bash
# Scale down to 1 machine
fly scale count 1

# Scale up to 2 machines
fly scale count 2

# Scale to specific count
fly scale count <number>
```

### Deploy Application
```bash
fly deploy
```

### Check Deployment Status
```bash
fly status
```

## Logs and Monitoring

### View Application Logs
```bash
# All logs
fly logs

# Specific machine logs
fly logs --instance <machine_id>

# Follow logs in real-time
fly logs --follow

# Filter logs by time
fly logs --since 1h
```

### Check Health Status
```bash
fly status
```

## Database Debugging

### Connect to Database
```bash
# Using fly proxy
fly proxy 5432:5432

# Direct connection (after proxy)
psql 'postgres://postgres:x8QPDqT2qgqy1ac@localhost:5432/finance_assistant?sslmode=disable'
```

### Check Active Database Connections
```bash
psql 'postgres://postgres:x8QPDqT2qgqy1ac@localhost:5432/finance_assistant?sslmode=disable' -c "
SELECT 
    pid,
    usename,
    application_name,
    client_addr,
    client_hostname,
    state,
    query_start,
    state_change,
    wait_event_type,
    wait_event,
    query
FROM pg_stat_activity 
WHERE state != 'idle';
"
```

### Find Long-Running Queries
```bash
psql 'postgres://postgres:x8QPDqT2qgqy1ac@localhost:5432/finance_assistant?sslmode=disable' -c "
SELECT 
    pid,
    usename,
    application_name,
    state,
    query_start,
    now() - query_start AS duration,
    query
FROM pg_stat_activity 
WHERE state != 'idle' 
AND query_start < now() - interval '5 minutes'
ORDER BY duration DESC;
"
```

### Check Database Locks
```bash
psql 'postgres://postgres:x8QPDqT2qgqy1ac@localhost:5432/finance_assistant?sslmode=disable' -c "
SELECT 
    l.pid,
    l.mode,
    l.granted,
    a.usename,
    a.application_name,
    a.state,
    a.query
FROM pg_locks l
JOIN pg_stat_activity a ON l.pid = a.pid
WHERE l.mode != 'AccessShareLock';
"
```

### Check Database Performance
```bash
psql 'postgres://postgres:x8QPDqT2qgqy1ac@localhost:5432/finance_assistant?sslmode=disable' -c "
SELECT 
    schemaname,
    tablename,
    attname,
    n_distinct,
    correlation
FROM pg_stats 
WHERE schemaname NOT IN ('information_schema', 'pg_catalog')
ORDER BY n_distinct DESC;
"
```

### Kill Long-Running Queries
```bash
# First, find the PID of the problematic query
psql 'postgres://postgres:x8QPDqT2qgqy1ac@localhost:5432/finance_assistant?sslmode=disable' -c "
SELECT pid, query_start, state, query 
FROM pg_stat_activity 
WHERE state != 'idle';
"

# Then kill the specific process
psql 'postgres://postgres:x8QPDqT2qgqy1ac@localhost:5432/finance_assistant?sslmode=disable' -c "
SELECT pg_cancel_backend(<pid>);
"

# Force kill if necessary
psql 'postgres://postgres:x8QPDqT2qgqy1ac@localhost:5432/finance_assistant?sslmode=disable' -c "
SELECT pg_terminate_backend(<pid>);
"
```

## File Storage Issues

### Check Storage Directory
```bash
# Inside the container
ls -la /app/storage/
ls -la /app/storage/reports/
ls -la /app/storage/queue/
```

### Check File Permissions
```bash
# Check ownership
ls -la /app/storage/reports/
# Check if appuser owns the files
```

### Test File Creation
```bash
# Test if you can create files
touch /app/storage/reports/test_file.txt
echo "test" > /app/storage/reports/test_file.txt
```

### Check Mount Points
```bash
mount | grep app
mount | grep vol
df -h
```

## API Testing

### Test API Endpoint with curl
```bash
# Test file existence
curl -I -H "x-api-key: YOUR_API_KEY" \
     "https://your-app.fly.dev/api/v1/reports/excel/filename.xlsx"

# Download file
curl -H "x-api-key: YOUR_API_KEY" \
     -H "Accept: application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" \
     "https://your-app.fly.dev/api/v1/reports/excel/filename.xlsx?download=true" \
     --output downloaded_file.xlsx

# Test with download parameter
curl -H "x-api-key: YOUR_API_KEY" \
     "https://your-app.fly.dev/api/v1/reports/excel/filename.xlsx?download=true"
```

### Test Local API
```bash
# Test from inside the container
curl -I "http://localhost:8000/excel/filename.xlsx"
curl -I "http://localhost:8000/health"
```

## Common Issues and Solutions

### Issue: Volume Sharing Between Machines
**Problem**: Multiple machines have separate volumes, files not accessible across machines.

**Solution**: 
1. Scale down to 1 machine: `fly scale count 1`
2. Or use external storage (S3, etc.)
3. Or recreate machines with shared volume configuration

### Issue: Read-Only File System
**Problem**: `/app` directory is read-only.

**Solution**:
1. Check volume mounts: `mount | grep app`
2. Check permissions: `ls -la /app/storage/`
3. Ensure proper volume configuration in `fly.toml`

### Issue: File Not Found in API
**Problem**: API can't find files that exist in storage.

**Solution**:
1. Check if API and worker are on same machine
2. Verify file paths and permissions
3. Check if machines are using different volumes

### Issue: Memory Limits
**Problem**: Cannot exceed 2048 MiB for shared CPU machines.

**Solution**:
1. Use `memory = '2gb'` (maximum for shared CPU)
2. Or change to `cpu_kind = 'dedicated'` for higher memory

### Issue: Database Bottlenecks
**Problem**: Slow queries, locks, or connection issues.

**Solution**:
1. Check active connections: Use the database debugging queries above
2. Kill long-running queries
3. Check for locks and blocking processes
4. Monitor query performance

## Performance Monitoring

### Check Machine Resources
```bash
# Inside container
top
htop
free -h
df -h
```

### Monitor Network
```bash
# Check network connections
netstat -tulpn
ss -tulpn
```

### Check Process Status
```bash
# Check running processes
ps aux | grep python
ps aux | grep gunicorn
ps aux | grep uvicorn
```

## Troubleshooting Workflow

1. **Check Machine Status**: `fly machines list`
2. **Check Application Status**: `fly status`
3. **Check Logs**: `fly logs`
4. **Check Storage**: `ls -la /app/storage/reports/`
5. **Test API**: Use curl commands above
6. **Check Database**: Use database debugging queries
7. **Scale if Needed**: `fly scale count 1` or `fly scale count 2`

## Useful Fly.io Commands Reference

```bash
# General
fly help
fly version
fly status

# Machines
fly machines list
fly machine show <id>
fly machine destroy <id>
fly machine update <id> [options]

# Volumes
fly volumes list
fly volumes create <name> [options]
fly volumes destroy <name>
fly volumes show <name>

# Scaling
fly scale count <number>
fly scale memory <size>
fly scale cpu <count>

# Deployment
fly deploy
fly config show
fly config save

# Logs
fly logs
fly logs --instance <id>
fly logs --follow

# Proxy (for database access)
fly proxy 5432:5432
```

## Notes

- **Volume Sharing**: Fly.io machines cannot share the same volume. Each machine gets its own isolated volume.
- **Memory Limits**: Shared CPU machines are limited to 2GB memory maximum.
- **File Persistence**: Files are stored in machine-specific volumes and are not shared between machines.
- **Scaling**: Scaling down/up recreates machines with new configurations.
- **Database Access**: Use `fly proxy` to access the database from your local machine.

## Quick Fixes

### For Volume Issues:
```bash
fly scale count 1
fly deploy
```

### For Memory Issues:
```bash
# Edit fly.toml to use 2gb memory
# Then deploy
fly deploy
```

### For Database Issues:
```bash
fly proxy 5432:5432
# Then use psql commands above
```
