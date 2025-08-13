# MakiAlert - Simple Alert System for Red-Bot

MakiAlert provides a simple HTTP endpoint for system services and scripts to send alerts directly to Nero via Discord DMs. The system runs automatically when the cog is loaded - no setup required!

## Quick Start

1. **Install the cog:**
   ```bash
   # In Discord: [p]load makialert
   ```

2. **That's it!** The server auto-starts and sends all alerts to Nero via DM.

## Usage

### HTTP API (for external services)

**Single endpoint:** `POST http://localhost:8080/alert`

```bash
curl -X POST http://localhost:8080/alert \
  -H "Content-Type: application/json" \
  -d '{
    "service": "nginx",
    "message": "Service is experiencing high load",
    "level": "warning",
    "details": "CPU usage at 85%, memory at 78%",
    "tags": ["monitoring", "performance"]
  }'
```

**No authentication required** - only localhost connections accepted.

### Health Check
```bash
curl http://localhost:8080/health
```

## Integration Examples

### Simple Bash Integration

Create `/usr/local/bin/send-alert.sh`:
```bash
#!/bin/bash

# Simple MakiAlert notification script
MAKI_URL="http://localhost:8080/alert"

send_alert() {
    local service="$1"
    local message="$2"
    local level="${3:-info}"
    local details="$4"
    
    curl -s -X POST "$MAKI_URL" \
        -H "Content-Type: application/json" \
        -d "{
            \"service\": \"$service\",
            \"message\": \"$message\",
            \"level\": \"$level\",
            \"details\": \"$details\"
        }"
}

# Usage examples:
# send_alert "nginx" "Service restarted" "info"
# send_alert "disk-space" "Low disk space" "warning" "/var partition at 89%"
# send_alert "system" "Server rebooted" "error" "Unexpected reboot detected"
```

### Audio Cog Integration (YouTube Failures)

MakiAlert includes built-in integration for Audio cog failures. To enable YouTube failure alerts:

1. **Import the integration in your Audio cog:**
```python
try:
    from cuscogs.makialert.audio_integration import youtube_load_failed
    MAKIALERT_AVAILABLE = True
except ImportError:
    MAKIALERT_AVAILABLE = False
```

2. **Call it when YouTube videos fail:**
```python
# In your error handling code:
if MAKIALERT_AVAILABLE:
    await youtube_load_failed(self.bot, track_url, str(error), requester_name)
```

3. **Other audio alerts available:**
```python
from cuscogs.makialert.audio_integration import (
    lavalink_connection_error,
    playlist_processing_error,
    send_audio_alert  # Generic function
)

# Examples:
await lavalink_connection_error(self.bot, "Connection timeout")
await playlist_processing_error(self.bot, playlist_url, "Invalid playlist")
```

### Common Examples

**Disk Space Monitor (Cron Job):**
```bash
#!/bin/bash
# /usr/local/bin/check-disk-space.sh
USAGE=$(df / | awk 'NR==2 {print $5}' | sed 's/%//')
if [ "$USAGE" -gt 80 ]; then
    curl -s -X POST http://localhost:8080/alert \
        -H "Content-Type: application/json" \
        -d "{\"service\": \"disk-monitor\", \"message\": \"High disk usage: ${USAGE}%\", \"level\": \"warning\"}"
fi
```

**Service Status Check:**
```bash
#!/bin/bash
if ! systemctl is-active --quiet nginx; then
    curl -s -X POST http://localhost:8080/alert \
        -H "Content-Type: application/json" \
        -d '{"service": "nginx", "message": "Nginx service is down", "level": "critical"}'
fi
```

**Python Example:**
```python
import requests

def send_alert(service, message, level="info"):
    requests.post("http://localhost:8080/alert", json={
        "service": service,
        "message": message, 
        "level": level
    })

# Usage
send_alert("backup-system", "Daily backup completed", "status")
```

## API Reference

### Request Format
- **Endpoint:** `POST http://localhost:8080/alert`
- **Headers:** `Content-Type: application/json`
- **Auth:** None required (localhost only)

### Request Fields
| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `service` | string | Yes | Service name (e.g., "nginx", "backup-system") |
| `message` | string | Yes | Alert message |
| `level` | string | No | Alert level: info, warning, error, critical, status |
| `details` | string | No | Additional context |
| `tags` | array | No | Tags for categorization |

### Alert Levels
- **info** (blue) - General information
- **status** (green) - Status updates  
- **warning** (orange) - Warning conditions
- **error** (red) - Error conditions
- **critical** (dark red) - Critical emergencies

All alerts are sent to Nero via DM with rich formatting.

## Admin Commands

- `[p]makialert status` - Show server status
- `[p]makialert test` - Send test alert
- `[p]makialert restart` - Restart HTTP server

## Features

✅ **Auto-start** - Server starts when cog loads  
✅ **No setup** - Works immediately after installation  
✅ **DM alerts** - All alerts sent directly to Nero  
✅ **Rate limiting** - 300 requests per minute max  
✅ **Localhost only** - Security by network isolation  
✅ **Audio integration** - Built-in YouTube failure alerts  
✅ **Rich formatting** - Color-coded embeds with icons