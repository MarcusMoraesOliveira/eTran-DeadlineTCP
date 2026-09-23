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
      printf "fd %d: rx_buf_size %u rx_addrs %lu ooo_rx_addrs %lu\n", $i, $c->rx_buf_size, $c->rx_addrs._M_impl._M_node._M_size, $c->ooo_rx_addrs._M_impl._M_node._M_size
      # rx_addrs: std::list<pair<uint64_t addr, char *pkt>>, value at node + 16, pkt at node + 24
      # rx metadata sits before pkt: rx_pos at pkt-20, poff at pkt-16, plen at pkt-14
      set $head = &$c->rx_addrs._M_impl._M_node
      set $n = $head->_M_next
      set $k = 0
      set $sum = 0
      set $minpos = 0xffffffff
      while $n != $head
        set $pkt = *(char **)((char *)$n + 24)
        set $pos = *(unsigned int *)($pkt - 20)
        set $poff = *(unsigned short *)($pkt - 16)
        set $plen = *(unsigned short *)($pkt - 14)
        set $sum = $sum + $plen
        if $pos < $minpos
          set $minpos = $pos
        end
        if $pos == $c->rxb_head
          printf "fd %d:   pkt[%d] rx_pos %u plen %u poff %u  <- at rxb_head\n", $i, $k, $pos, $plen, $poff
        else
          if $k < 8
            printf "fd %d:   pkt[%d] rx_pos %u plen %u poff %u\n", $i, $k, $pos, $plen, $poff
          end
        end
        set $k = $k + 1
        set $n = $n->_M_next
      end
      printf "fd %d: rx_addrs total payload %u (rxb_used %u), lowest rx_pos %u\n", $i, $sum, $c->rxb_used, $minpos
    end
  end
  set $i = $i + 1
end
detach
EOF

gdb -q -batch -p "$PID" -x "$CMDS" 2>&1 | grep -E "^fd |No symbol|rror" || echo "(no connected eTran sockets found)"
