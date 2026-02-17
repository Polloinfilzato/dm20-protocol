---
description: Show Party Mode server status, connected players, and queue stats.
allowed-tools: Bash
---

# Party Mode Status

Display the current state of the Party Mode server.

## Usage
```
/dm:party-status
```

## Prerequisites

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
+--------------------------------------------------+
|          PARTY MODE: OFFLINE                      |
+--------------------------------------------------+
| Server is not running.                            |
| Use /dm:party-mode to start it.                   |
+--------------------------------------------------+
```
Then stop.

## Instructions

### Gather Status Data

Run via `Bash`:

```bash
python3 -c "
import json
from datetime import datetime
from dm20_protocol.party.server import get_server_instance

srv = get_server_instance()

# Server info
uptime = (datetime.now() - srv.start_time).total_seconds()

# Connection info
connected_players = srv.connection_manager.get_connected_players()
player_connections = {}
for pid in connected_players:
    player_connections[pid] = srv.connection_manager.connection_count(pid)
total_connections = srv.connection_manager.connection_count()

# Queue stats
pending = srv.action_queue.get_pending_count()
total_actions = len(srv.action_queue._actions)
processing = sum(1 for a in srv.action_queue._actions.values() if a['status'] == 'processing')
resolved = sum(1 for a in srv.action_queue._actions.values() if a['status'] == 'resolved')
total_responses = len(srv.response_queue._responses)

# Next pending action preview
next_preview = None
with srv.action_queue._lock:
    if srv.action_queue._pending:
        next_id = srv.action_queue._pending[0]
        next_action = srv.action_queue._actions.get(next_id)
        if next_action:
            next_preview = {
                'id': next_action['id'],
                'player_id': next_action['player_id'],
                'text': next_action['text'][:80],
                'timestamp': next_action['timestamp'],
            }

# Token info
tokens = srv.token_manager.get_all_tokens()

# Stale players
stale = srv.connection_manager.get_stale_players(timeout_seconds=60.0)

result = {
    'host': srv.host_ip,
    'port': srv.port,
    'url': f'http://{srv.host_ip}:{srv.port}',
    'uptime_seconds': uptime,
    'connected_players': player_connections,
    'total_connections': total_connections,
    'tokens_issued': len(tokens),
    'stale_players': stale,
    'queue': {
        'pending': pending,
        'processing': processing,
        'resolved': resolved,
        'total_actions': total_actions,
        'total_responses': total_responses,
    },
    'next_action': next_preview,
}
print(json.dumps(result, indent=2))
"
```

### Display Formatted Status

Format the output as follows:

```
+--------------------------------------------------+
|           PARTY MODE: ONLINE                      |
+--------------------------------------------------+
| Server:  http://{host}:{port}                     |
| Uptime:  {hours}h {minutes}m {seconds}s           |
| Tokens:  {tokens_issued} issued                   |
+--------------------------------------------------+

Connected Players:
  {player_id} ............ {N} connection(s)
  {player_id} ............ {N} connection(s)
  (none connected)

Stale Players (no heartbeat >60s):
  {player_id}
  (none)

Action Queue:
  Pending:    {pending}
  Processing: {processing}
  Resolved:   {resolved}
  Total:      {total_actions} actions, {total_responses} responses

Next Pending Action:
  [{action_id}] {player_id}: "{text_preview}..."
  Submitted: {timestamp}
  (or: No pending actions)

+--------------------------------------------------+
| /dm:party-next   - Process next action            |
| /dm:party-auto   - Auto-process all actions       |
| /dm:party-kick   - Disconnect a player            |
| /dm:party-stop   - Shut down server               |
+--------------------------------------------------+
```

Format `uptime_seconds` as `{h}h {m}m {s}s`.

If there are stale players, highlight them with a warning.
