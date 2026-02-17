---
description: Start Party Mode web server for multi-player sessions.
argument-hint: [port]
allowed-tools: Bash, Read, mcp__dm20-protocol__get_game_state, mcp__dm20-protocol__list_characters, mcp__dm20-protocol__get_character
---

# Party Mode Start

Start the Party Mode web server so multiple players can connect via their browsers.

## Usage
```
/dm:party-mode [port]
```

Default port is **8080**. Pass a custom port number as argument if needed.

## Prerequisites

Before starting, verify the following preconditions. If any fail, report the error and stop.

### 1. Check Campaign Loaded

Call `get_game_state` to confirm a campaign is active.

**If no campaign is loaded:** Tell the user:
```
No campaign loaded. Run /dm:start first to load a campaign.
```

### 2. Check Server Not Already Running

Run this Python check via `Bash`:

```bash
python3 -c "
from dm20_protocol.party.server import get_server_instance
srv = get_server_instance()
if srv:
    import json
    from datetime import datetime
    uptime = (datetime.now() - srv.start_time).total_seconds()
    print(json.dumps({'running': True, 'host': srv.host_ip, 'port': srv.port, 'uptime': uptime}))
else:
    print(json.dumps({'running': False}))
"
```

**If server is already running:** Display current status and tell the user:
```
Party Mode is already running at http://{host}:{port}
Use /dm:party-status to see connected players, or /dm:party-stop to shut down.
```

### 3. Get Active Player Characters

Call `list_characters` to get all PCs in the campaign.

**If no characters exist:** Tell the user:
```
No player characters found. Create characters first before starting Party Mode.
```

## Instructions

### Step 1 — Initialize Token Manager and Generate Tokens

Run the following via `Bash` to start the server, generate tokens, and create QR codes.

Use port from `$ARGUMENTS` if provided, otherwise default to `8080`.

```bash
python3 -c "
import json, sys
from pathlib import Path
from dm20_protocol.party.server import start_party_server, get_server_instance
from dm20_protocol.party.auth import QRCodeGenerator, detect_host_ip
from dm20_protocol.claudmaster.pc_tracking import PCRegistry, MultiPlayerConfig
from dm20_protocol.permissions import PermissionResolver
from dm20_protocol.storage import DnDStorage

# Get campaign dir from environment or storage
storage = DnDStorage()
campaign_dir = storage.campaign_dir

# Build PCRegistry from character list
config = MultiPlayerConfig()
registry = PCRegistry(config)
permission_resolver = PermissionResolver()

# Get all characters
characters = storage.list_characters()
for char in characters:
    registry.register_pc(char.name, char.player_name or char.name)

# Start server
port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
server = start_party_server(
    pc_registry=registry,
    permission_resolver=permission_resolver,
    storage=storage,
    campaign_dir=campaign_dir,
    port=port,
)

# Generate tokens for each PC
host_ip = server.host_ip
tokens = {}
qr_paths = {}

for char in characters:
    token = server.token_manager.generate_token(char.name)
    tokens[char.name] = token
    qr_path = QRCodeGenerator.generate_player_qr(
        char.name, token, host_ip, port, campaign_dir
    )
    qr_paths[char.name] = str(qr_path)

# Generate OBSERVER token
observer_token = server.token_manager.generate_token('OBSERVER')
observer_qr = QRCodeGenerator.generate_player_qr(
    'OBSERVER', observer_token, host_ip, port, campaign_dir
)
qr_paths['OBSERVER'] = str(observer_qr)
tokens['OBSERVER'] = observer_token

# Output result
result = {
    'host': host_ip,
    'port': port,
    'url': f'http://{host_ip}:{port}',
    'tokens': tokens,
    'qr_paths': qr_paths,
    'player_count': len(characters),
}
print(json.dumps(result, indent=2))
" ${ARGUMENTS:-8080}
```

### Step 2 — Display Connection Info

Format and display the results using this template:

```
+--------------------------------------------------+
|              PARTY MODE ACTIVE                    |
+--------------------------------------------------+
| Server: http://{host}:{port}                     |
| Players: {count} PCs + 1 Observer                |
+--------------------------------------------------+

Player Connections:
  {character_name}
    URL:  http://{host}:{port}/play?token={token}
    QR:   {qr_path}

  ... (repeat for each player)

  OBSERVER (read-only)
    URL:  http://{host}:{port}/play?token={observer_token}
    QR:   {observer_qr_path}

+--------------------------------------------------+
| Players can scan QR codes or open URLs on their  |
| phones/tablets to join the session.               |
|                                                   |
| Use /dm:party-next to process player actions.     |
| Use /dm:party-status to monitor connections.      |
| Use /dm:party-stop to end Party Mode.             |
+--------------------------------------------------+
```

Display the QR code image files by reading them with the `Read` tool (Claude Code can display PNG images).

## Error Handling

- **Port already in use:** Report the error and suggest a different port: `/dm:party-mode 8081`
- **Import errors:** Check that party mode dependencies are installed: `pip install qrcode[pil] starlette uvicorn`
- **Network errors:** Display fallback URL with `127.0.0.1` and warn about LAN access
