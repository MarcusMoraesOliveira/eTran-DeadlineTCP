#!/bin/bash
# Single-host testbed for DeadlineTCP: an SR-IOV VF of the eTran NIC is moved
# into a network namespace and acts as the remote host. The NIC switches
# PF <-> VF traffic internally, so no second machine is needed.
#
#   host (eTran, PF $IF, $CLIENT_IP)  <-- NIC eswitch -->  netns $NS (eTran, VF, $SERVER_IP)
#
# The server side must run eTran too: eTran does not generate valid IP/TCP
# checksums, so a Linux TCP peer drops its packets.
#
# Usage: sudo ./deadline_single_host.sh setup|server|teardown
#   setup     create the VF and the namespace (stop micro_kernel first)
#   server    run micro_kernel + epoll_server inside the namespace, with a
#             private /tmp and /dev/shm so they do not clash with the host
#             micro_kernel (extra arguments are passed to epoll_server)
#   teardown  remove the namespace and the VF (stop everything first)
set -e

IF=${IF:-ens1f1np1}
NS=${NS:-dlserver}
SERVER_IP=${SERVER_IP:-10.10.1.200}
VF_MAC=${VF_MAC:-02:00:0a:0a:01:c8}

CLIENT_IP=$(ip -4 -o addr show dev "$IF" | awk '{print $4}' | cut -d/ -f1 | head -1)
PREFIX=$(ip -4 -o addr show dev "$IF" | awk '{print $4}' | cut -d/ -f2 | head -1)
PF_MAC=$(cat /sys/class/net/"$IF"/address)
DEV=/sys/class/net/$IF/device

setup() {
    if ping -c 1 -W 1 "$SERVER_IP" > /dev/null 2>&1; then
        echo "ERROR: $SERVER_IP is already in use, choose another SERVER_IP" >&2
        exit 1
    fi

    echo 1 > "$DEV"/sriov_numvfs
    for _ in $(seq 50); do
        VF=$(ls "$DEV"/virtfn0/net/ 2>/dev/null | head -1)
        [ -n "$VF" ] && break
        sleep 0.1
    done
    [ -n "$VF" ] || { echo "ERROR: VF netdev did not appear" >&2; exit 1; }

    ip link set "$IF" vf 0 mac "$VF_MAC"
    # the VF driver picks up the new MAC on rebind
    VF_PCI=$(basename "$(readlink "$DEV"/virtfn0)")
    echo "$VF_PCI" > /sys/bus/pci/drivers/mlx5_core/unbind
    echo "$VF_PCI" > /sys/bus/pci/drivers/mlx5_core/bind
    for _ in $(seq 50); do
        VF=$(ls "$DEV"/virtfn0/net/ 2>/dev/null | head -1)
        [ -n "$VF" ] && break
        sleep 0.1
    done

    ip netns add "$NS"
    ip link set "$VF" netns "$NS"
    ip -n "$NS" link set lo up
    ip -n "$NS" addr add "$SERVER_IP/$PREFIX" dev "$VF"
    ip -n "$NS" link set "$VF" up

    # static neighbors: ARP is unreliable once XDP is attached to the PF
    ip neigh replace "$SERVER_IP" lladdr "$VF_MAC" dev "$IF" nud permanent
    ip -n "$NS" neigh replace "$CLIENT_IP" lladdr "$PF_MAC" dev "$VF" nud permanent

    sleep 1
    ping -c 2 -W 1 "$SERVER_IP"
    echo
    echo "OK: server namespace '$NS' at $SERVER_IP (VF $VF), client $CLIENT_IP on $IF"
}

server() {
    VF=$(ip -n "$NS" -br link | awk '$1 != "lo" {print $1; exit}')
    [ -n "$VF" ] || { echo "ERROR: no VF in namespace $NS, run setup first" >&2; exit 1; }
    ETRAN_DIR=$(cd "$(dirname "$0")/.." && pwd)
    EPOLL_ARGS=${*:-"-b 1000 -l 4096"}

    exec ip netns exec "$NS" unshare -m --propagation private bash -c "
        mount -t tmpfs tmpfs /tmp
        mount -t tmpfs tmpfs /dev/shm
        cd '$ETRAN_DIR/micro_kernel'
        ./micro_kernel -i $VF -q 1 > /tmp/micro_kernel.log 2>&1 &
        MK=\$!
        trap 'kill \$MK 2>/dev/null' EXIT
        for _ in \$(seq 100); do [ -S /tmp/micro_kernel_socket ] && break; sleep 0.1; done
        [ -S /tmp/micro_kernel_socket ] || { echo 'ERROR: server micro_kernel failed:'; cat /tmp/micro_kernel.log; exit 1; }
        echo 'server micro_kernel up on $VF'
        cd '$ETRAN_DIR/tcp_app'
        ETRAN_PROTO=tcp ETRAN_NR_APP_THREADS=1 ETRAN_NR_NIC_QUEUES=1 LD_PRELOAD=../shared_lib/libetran.so \\
            ./epoll_server -i $SERVER_IP $EPOLL_ARGS
    "
}

teardown() {
    ip netns del "$NS" 2>/dev/null || true
    ip neigh del "$SERVER_IP" dev "$IF" 2>/dev/null || true
    echo 0 > "$DEV"/sriov_numvfs
    echo "OK: removed namespace '$NS' and VFs"
}

case "$1" in
    setup) setup ;;
    server) shift; server "$@" ;;
    teardown) teardown ;;
    *) echo "Usage: sudo $0 setup|teardown" >&2; exit 1 ;;
esac
