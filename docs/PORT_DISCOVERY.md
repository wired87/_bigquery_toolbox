# Port Discovery & Auto-Jumping

## Overview

The BigQuery AIToolbox Engine now includes intelligent port discovery and auto-jumping functionality. When the default port (8000) is unavailable, the server automatically finds the next available port and clients automatically discover it by trying all ports sequentially.

## How It Works

### Server Side

1. **Port Jumping**: When starting the server, it checks if port 8000 is available
   - If available: Uses port 8000
   - If busy: Tries ports 8001, 8002, ..., up to 8009 (configurable)
   - Maximum attempts: 10 ports

2. **Port Broadcasting**: Once a port is found:
   - The port is saved to `.server_port` file in the project root
   - The port is stored in `GlobalServerConfig` singleton
   - Server info is exposed via HTTP endpoint `/api/server-info/`

### Client Side

Clients (RemoteEngine, CLI Interactor) use an intelligent connection approach with automatic port jumping:

1. **Initial Port Discovery** (During initialization):
   - Reads `.server_port` file if it exists
   - Probes ports 8000-8010 to find listening servers
   - Updates default connection settings

2. **Connection-Time Port Jumping** (During WebSocket connection):
   - **Automatically tries all ports 8000-8010 in sequence**
   - Each port gets a 2-second connection timeout
   - Moves to next port on failure (timeout, connection refused, etc.)
   - Stops immediately on successful connection
   - Provides detailed error messages if all ports fail

3. **Environment Variable Override**:
   - `SERVER_URL` or `DOMAIN` can be set to force a specific address
   - Useful for remote/cloud deployments
   - Skips port jumping when custom URL is provided

4. **Connection Persistence**:
   - Once connected, the client remembers the successful port
   - Re-uses the same port for subsequent operations
   - Automatically re-authenticates on reconnection

## Usage

### Starting the Server

```bash
python run_server.py
```

**Output Example:**
```
🚀 Starting BigQuery AIToolbox Engine...
⚠️  Port 8000 is already in use. Jumping to port 8001...
✅ Global Server Config initialized: 127.0.0.1:8001
🌍 Server info available globally:
   - HTTP: http://127.0.0.1:8001
   - WebSocket: ws://127.0.0.1:8001/ws/chat/
📝 Port saved to C:\Users\youruser\Desktop\_bigquery_toolbox-1\.server_port
```

### Client Connection

Clients automatically discover the port - no configuration needed:

```python
from remote_engine import RemoteEngine

# Automatically tries ports 8000-8010
engine = RemoteEngine()

# Client will show debug logs like:
# 🔌 Attempting connection to ws://127.0.0.1:8000/ws/chat/...
# ❌ Port 8000 refused, trying next...
# 🔌 Attempting connection to ws://127.0.0.1:8001/ws/chat/...
# ✅ Connected to WebSocket at ws://127.0.0.1:8001/ws/chat/
```

### Connection Behavior

The connection logic tries each port in sequence:

```
Port 8000 → Timeout/Refused → Try 8001
Port 8001 → Timeout/Refused → Try 8002
Port 8002 → Success! → Connected
```

**Total maximum time**: 11 ports × 2 seconds = ~22 seconds (if all ports fail)
**Typical time**: < 2 seconds (finds server on first or second port)

### Checking Server Info

You can query the server info endpoint:

```bash
curl http://localhost:8001/api/server-info/
```

**Response:**
```json
{
  "success": true,
  "data": {
    "port": 8001,
    "host": "127.0.0.1",
    "started_at": "2025-12-22T06:15:06.123456",
    "protocol": "ws",
    "is_running": true,
    "ws_url": "ws://127.0.0.1:8001/ws/chat/",
    "http_url": "http://127.0.0.1:8001"
  }
}
```

## Configuration

### Changing Port Range (Server)

Edit `run_server.py`:

```python
# Change max_attempts to try more ports
port = find_available_port(start_port=8000, max_attempts=20)
```

### Changing Port Range (Client)

Edit `remote_engine.py` or `interactor.py`:

```python
# Change the range(8000, 8011) to your desired range
for port in range(8000, 8020):  # Try ports 8000-8019
    ...
```

### Changing Connection Timeout

Edit `remote_engine.py` or `interactor.py`:

```python
# Change timeout=2.0 to a higher value for slower networks
self.ws = await asyncio.wait_for(
    websockets.connect(ws_url, ...),
    timeout=5.0  # 5 seconds per port instead of 2
)
```

### Using Environment Variables

```bash
# Force a specific server URL (skips port jumping)
export SERVER_URL=http://myserver.com:8001
python cli.py

# Or for CLI interactor
export DOMAIN=myserver.com:8001
```

## Troubleshooting

### Port File Stale

If `.server_port` contains an old port:
- Delete the file: `rm .server_port` or `del .server_port`
- Restart the server

### Connection Takes Too Long

If port jumping takes too long:
1. Check if many ports are timing out (shouldn't happen on localhost)
2. Reduce connection timeout in client code
3. Ensure server is actually running

### Connection Issues

1. **Check if server is running**:
   ```bash
   # Windows
   netstat -an | findstr "8000 8001 8002"
   
   # Linux/Mac
   netstat -an | grep "8000\|8001\|8002"
   ```

2. **Check the `.server_port` file**:
   ```bash
   # Windows
   type .server_port
   
   # Linux/Mac
   cat .server_port
   ```

3. **Enable debug logging** to see port jumping in action:
   ```python
   import logging
   logging.basicConfig(level=logging.DEBUG)
   
   from remote_engine import RemoteEngine
   engine = RemoteEngine()
   ```

4. **Test the server info endpoint**:
   ```bash
   # Try each port manually
   curl http://localhost:8000/api/server-info/
   curl http://localhost:8001/api/server-info/
   curl http://localhost:8002/api/server-info/
   ```

### Manual Override

If auto-discovery fails, manually set the port:

```python
from remote_engine import RemoteEngine
import os

# Skip discovery, use specific URL
os.environ['SERVER_URL'] = 'http://localhost:8002'
engine = RemoteEngine()
```

## Architecture

### Files Modified

1. **`run_server.py`**: Port jumping logic and file writing
2. **`remote_engine.py`**: Client-side port discovery and connection-time port jumping
3. **`toolbox_cli/interactor.py`**: CLI port discovery and connection-time port jumping
4. **`dj/views/server_info.py`**: HTTP endpoint for server info
5. **`dj/urls.py`**: Route registration for `/api/server-info/`
6. **`server_config.py`**: Global configuration singleton
7. **`.gitignore`**: Exclude runtime `.server_port` file

### Connection Flow

```
Client._connect_ws() called
    ↓
Try port 8000 (timeout: 2s)
    ↓ (connection failed)
Try port 8001 (timeout: 2s)
    ↓ (connection success!)
Update self.ws_url and self.server_url
    ↓
Auto-re-authenticate if credentials exist
    ↓
Return (ready to communicate)
```

### Error Handling

- **Timeout**: Moves to next port immediately
- **Connection Refused**: Moves to next port immediately  
- **Other Errors**: Logs error, moves to next port
- **All Ports Fail**: Raises ConnectionError with detailed message

## Security Considerations

- The `.server_port` file is local only (not exposed externally)
- Port jumping uses minimal timeout (2s) to avoid excessive delays
- Server info endpoint only exposes configuration, not sensitive data
- All connections still require authentication (if enabled)
- Port range is restricted to 8000-8010 (prevents port scanning abuse)

## Performance

- **Best case** (server on port 8000): < 0.1 second connection time
- **Typical case** (server on port 8001): ~2 seconds (one failed attempt + success)
- **Worst case** (all ports fail): ~22 seconds (11 ports × 2 seconds)

## Future Enhancements

- [ ] Parallel port probing for faster discovery
- [ ] mDNS/Bonjour service discovery for automatic server detection
- [ ] Health check endpoints with server metrics
- [ ] Automatic server restart on crash with port persistence
- [ ] Load balancing across multiple server instances
