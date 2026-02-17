---
description: Stop the Party Mode web server and disconnect all players.
allowed-tools: Bash, mcp__dm20-protocol__get_game_state
---

# Party Mode Stop

Gracefully shut down the Party Mode web server.

## Usage
```
/dm:party-stop
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
    import json
    from datetime import datetime
    uptime = (datetime.now() - srv.start_time).total_seconds()
    connected = srv.connection_manager.get_connected_players()
    actions_total = len(srv.action_queue._actions)
    responses_total = len(srv.response_queue._responses)
    pending = srv.action_queue.get_pending_count()
    print(json.dumps({
        'running': True,
        'host': srv.host_ip,
        'port': srv.port,
        'uptime_seconds': uptime,
        'connected_players': connected,
        'total_connections': srv.connection_manager.connection_count(),
        'actions_processed': actions_total,
        'responses_sent': responses_total,
        'pending_actions': pending,
    }))
"
```

**If not running:** Tell the user:
```
Party Mode is not running. Nothing to stop.
```

**If there are pending actions:** Warn the user before stopping:
```
Warning: There are {N} pending actions that have not been processed.
Stopping will discard them. Continue? (The actions are persisted in the JSONL log.)
```

## Instructions

### Step 1 — Stop the Server

Run via `Bash`:

```bash
python3 -c "
from dm20_protocol.party.server import stop_party_server
stop_party_server()
print('STOPPED')
"
```

### Step 2 — Display Session Summary

Using the data gathered in the prerequisites step, display:

```
+--------------------------------------------------+
|            PARTY MODE STOPPED                     |
+--------------------------------------------------+
| Session Duration:  {hours}h {minutes}m {seconds}s |
| Actions Processed: {actions_total}                |
| Responses Sent:    {responses_total}              |
| Players Connected: {total_connections}            |
+--------------------------------------------------+
| Action/response logs saved in:                    |
| {campaign_dir}/party/actions.jsonl                |
| {campaign_dir}/party/responses.jsonl              |
+--------------------------------------------------+
```

Format the uptime as hours/minutes/seconds from the `uptime_seconds` value.

## Error Handling

- **Server not running:** Display a clear message, do not error out.
- **Thread did not exit cleanly:** Report that the server may still be partially running and suggest restarting Claude Code.
