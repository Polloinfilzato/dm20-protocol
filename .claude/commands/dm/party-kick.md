---
description: Kick a player from the Party Mode session and revoke their token.
argument-hint: <player_name>
allowed-tools: Bash
---

# Party Mode — Kick Player

Disconnect a player from the Party Mode session and revoke their authentication token.

## Usage
```
/dm:party-kick <player_name>
```

## Prerequisites

### Check Arguments

**If no `$ARGUMENTS` provided:** Tell the user:
```
Usage: /dm:party-kick <player_name>

Specify the player name or character ID to kick.
```
Then stop.

### Check Server is Running

Run via `Bash`:

```bash
python3 -c "
from dm20_protocol.party.server import get_server_instance
srv = get_server_instance()
if srv is None:
    print('NOT_RUNNING')
else:
    print('RUNNING')
"
```

**If not running:** Tell the user:
```
Party Mode is not running. Nothing to kick.
```

### Validate Player Exists

Run via `Bash` (replace `{player_name}` with `$ARGUMENTS`):

```bash
python3 -c "
import json
from dm20_protocol.party.server import get_server_instance

srv = get_server_instance()
player_id = '${ARGUMENTS}'.strip()

# Check if player has a token
tokens = srv.token_manager.get_all_tokens()
connected = srv.connection_manager.get_connected_players()

found = player_id in tokens
is_connected = player_id in connected
conn_count = srv.connection_manager.connection_count(player_id) if is_connected else 0

print(json.dumps({
    'player_id': player_id,
    'has_token': found,
    'is_connected': is_connected,
    'connection_count': conn_count,
    'all_players_with_tokens': list(tokens.keys()),
}))
"
```

**If player not found:** Show available players and tell the user:
```
Player "{player_name}" not found. Active players:
  - {list of player names with tokens}
```

## Instructions

### Step 1 — Disconnect WebSocket Connections

If the player is currently connected via WebSocket, close their connections:

```bash
python3 -c "
import json, asyncio
from dm20_protocol.party.server import get_server_instance

srv = get_server_instance()
player_id = '${ARGUMENTS}'.strip()

# Close WebSocket connections from the server's event loop
async def kick_player():
    connections = srv.connection_manager._connections.get(player_id, set()).copy()
    for ws in connections:
        try:
            await ws.close(code=1008, reason='Kicked by host')
        except Exception as e:
            print(f'Warning: {e}')
    srv.connection_manager.disconnect(player_id, None)  # Clean up tracking
    return len(connections)

if srv._loop and not srv._loop.is_closed():
    future = asyncio.run_coroutine_threadsafe(kick_player(), srv._loop)
    closed = future.result(timeout=5.0)
    print(json.dumps({'closed_connections': closed}))
else:
    print(json.dumps({'closed_connections': 0, 'warning': 'No event loop available'}))
"
```

### Step 2 — Revoke Token

```bash
python3 -c "
import json
from dm20_protocol.party.server import get_server_instance

srv = get_server_instance()
player_id = '${ARGUMENTS}'.strip()

revoked = srv.token_manager.revoke_token(player_id)
print(json.dumps({'revoked': revoked, 'player_id': player_id}))
"
```

### Step 3 — Broadcast Disconnect Message

```bash
python3 -c "
import json, asyncio
from datetime import datetime
from dm20_protocol.party.server import get_server_instance

srv = get_server_instance()
player_id = '${ARGUMENTS}'.strip()

async def broadcast_kick():
    msg = {
        'type': 'system',
        'content': f'{player_id} was removed from the session by the DM.',
        'timestamp': datetime.now().isoformat(),
    }
    sent = await srv.connection_manager.broadcast(msg)
    return sent

if srv._loop and not srv._loop.is_closed():
    future = asyncio.run_coroutine_threadsafe(broadcast_kick(), srv._loop)
    sent = future.result(timeout=5.0)
    print(json.dumps({'broadcast_sent': sent}))
else:
    print(json.dumps({'broadcast_sent': 0}))
"
```

### Step 4 — Deactivate in PCRegistry

```bash
python3 -c "
import json
from dm20_protocol.party.server import get_server_instance

srv = get_server_instance()
player_id = '${ARGUMENTS}'.strip()

left = srv.pc_registry.leave_session(player_id)
print(json.dumps({'deactivated': left}))
"
```

### Step 5 — Display Confirmation

```
+--------------------------------------------------+
|          PLAYER KICKED                            |
+--------------------------------------------------+
| Player:      {player_id}                          |
| Connections: {closed_count} closed                |
| Token:       revoked                              |
| Status:      deactivated                          |
+--------------------------------------------------+
| The player can no longer connect.                 |
| Use /dm:party-token {player_id} to issue a new    |
| token if you want to let them rejoin.             |
+--------------------------------------------------+
```
