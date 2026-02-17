---
description: Generate a new token and QR code for a player (invalidates old token).
argument-hint: <player_name>
allowed-tools: Bash, Read
---

# Party Mode — Refresh Token

Generate a new session token and QR code for a player, invalidating their previous token.

## Usage
```
/dm:party-token <player_name>
```

Use this when a player needs a new connection link (e.g., lost their QR code, security concern, or after being kicked and readmitted).

## Prerequisites

### Check Arguments

**If no `$ARGUMENTS` provided:** Tell the user:
```
Usage: /dm:party-token <player_name>

Specify the player name or character ID to refresh.
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
Party Mode is not running. Start it with /dm:party-mode first.
```

## Instructions

### Step 1 — Refresh Token and Generate QR Code

Run via `Bash` (replace `{player_name}` with `$ARGUMENTS`):

```bash
python3 -c "
import json
from dm20_protocol.party.server import get_server_instance
from dm20_protocol.party.auth import QRCodeGenerator

srv = get_server_instance()
player_id = '${ARGUMENTS}'.strip()

# Check if this player exists or if we are creating a new token
old_tokens = srv.token_manager.get_all_tokens()
had_old_token = player_id in old_tokens

# Generate new token (automatically invalidates old one)
new_token = srv.token_manager.refresh_token(player_id)

# Generate QR code
qr_path = QRCodeGenerator.generate_player_qr(
    player_id,
    new_token,
    srv.host_ip,
    srv.port,
    srv.campaign_dir,
)

url = f'http://{srv.host_ip}:{srv.port}/play?token={new_token}'

# Reactivate in PCRegistry if needed
try:
    from dm20_protocol.permissions import PlayerRole
    role = PlayerRole.OBSERVER if player_id == 'OBSERVER' else PlayerRole.PLAYER
    srv.pc_registry.join_session(player_id, player_id, role=role)
except Exception:
    pass  # May not need reactivation

print(json.dumps({
    'player_id': player_id,
    'new_token': new_token,
    'url': url,
    'qr_path': str(qr_path),
    'had_old_token': had_old_token,
    'old_token_invalidated': had_old_token,
}))
"
```

### Step 2 — Display New Connection Info

```
+--------------------------------------------------+
|          TOKEN REFRESHED                          |
+--------------------------------------------------+
| Player:    {player_id}                            |
| Old Token: {invalidated / none}                   |
| New Token: {new_token}                            |
+--------------------------------------------------+
| URL: {url}                                        |
| QR:  {qr_path}                                    |
+--------------------------------------------------+
| The old token is now invalid. The player must     |
| use the new URL or scan the new QR code.          |
+--------------------------------------------------+
```

Display the QR code PNG image by reading it with the `Read` tool so the user can show it to the player.

## Error Handling

- **QR generation fails:** Display the URL without a QR code and warn that `qrcode` or `Pillow` may not be installed.
- **Player not in registry:** The token is still generated. The player will be registered when they first connect.
