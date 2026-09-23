#!/bin/bash
# Print libetran's per-connection receive/send state inside a running eTran
# application, by briefly attaching gdb (the process continues afterwards).
#
# Usage: sudo ./etran_lib_state.sh <pid | process name>   e.g. epoll_server
#
# rxb_used      bytes received and made readable, not yet read by the app
# rxb_bump      bytes read by the app, not yet returned to eBPF (window)
# epoll_events  readiness flags the lib holds for the socket (0x1 = EPOLLIN)
set -e

TARGET=${1:?usage: $0 <pid | process name>}
if [[ "$TARGET" =~ ^[0-9]+$ ]]; then PID=$TARGET; else PID=$(pgrep -n -x "$TARGET"); fi
[ -n "$PID" ] || { echo "process $TARGET not found" >&2; exit 1; }

CMDS=$(mktemp)
trap 'rm -f "$CMDS"' EXIT
cat > "$CMDS" <<'EOF'
set pagination off
set $i = 0
while $i < 4096
  if fds[$i].type == 1 && fds[$i].data.socket != 0
    set $s = fds[$i].data.socket
    if $s->type == 2 && $s->conn != 0
      set $c = $s->conn
      printf "fd %d: status %d rxb_used %u rxb_head %u rxb_bump %u force_rx_bump %d in_rx_bump_pending %d epoll_events 0x%x txb_sent %u txb_allocated %u xsk_budget %u\n", $i, $s->status, $c->rxb_used, $c->rxb_head, $c->rxb_bump, $c->force_rx_bump, $c->in_rx_bump_pending, $s->epoll_events, $c->txb_sent, $c->txb_allocated, $c->xsk_budget
    end
  end
  set $i = $i + 1
end
detach
EOF

gdb -q -batch -p "$PID" -x "$CMDS" 2>&1 | grep -E "^fd |No symbol|error" || echo "(no connected eTran sockets found)"
