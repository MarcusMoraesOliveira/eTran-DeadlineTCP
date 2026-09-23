#!/usr/bin/env python3
"""
Print eTran TCP fast-path state (eBPF map bpf_tcp_conn_map) for every connection.

Usage: sudo ./etran_conn_dump.py

Useful when a transfer stalls, e.g. rx_remote_avail == 0 with tx_sent == 0 on
the sender means the peer's receive window is closed and nothing is in flight.
"""
import json
import socket
import struct
import subprocess

# struct bpf_tcp_conn in common/intf/intf_ebpf.h (packed), up to cc_idx
FMT = "<IQI6s6sIIHHIIIIIIHIIIIIIII"
NAMES = ["lock", "opaque_connection", "qid", "local_mac", "remote_mac", "local_ip", "remote_ip",
         "local_port", "remote_port", "rx_buf_size", "tx_buf_size", "rx_avail", "rx_remote_avail",
         "rx_next_pos", "rx_next_seq", "rx_dupack_cnt", "rx_ooo_start", "rx_ooo_len", "tx_pending",
         "tx_sent", "tx_next_pos", "tx_next_seq", "tx_next_ts", "cc_idx"]
SHOW = ["cc_idx", "rx_avail", "rx_remote_avail", "tx_pending", "tx_sent", "tx_next_seq",
        "rx_next_seq", "rx_dupack_cnt", "rx_ooo_len"]


def main():
    out = subprocess.run(["bpftool", "-j", "map", "dump", "name", "bpf_tcp_conn_ma"],
                         check=True, capture_output=True, text=True).stdout
    entries = json.loads(out)
    if not entries:
        print("(no connections)")
    for e in entries:
        v = bytes(int(b, 16) for b in e["value"])
        c = dict(zip(NAMES, struct.unpack_from(FMT, v)))
        local = f"{socket.inet_ntoa(struct.pack('>I', c['local_ip']))}:{c['local_port']}"
        remote = f"{socket.inet_ntoa(struct.pack('>I', c['remote_ip']))}:{c['remote_port']}"
        print(f"{local} -> {remote}  " + "  ".join(f"{k}={c[k]}" for k in SHOW))
        if c["rx_remote_avail"] == 0 and c["tx_sent"] == 0:
            print("  ^ peer receive window closed, nothing in flight: sender is waiting for a window update")
        if (c["rx_avail"] >> 3) == 0:
            print("  ^ our receive window is closed: the application is not reading fast enough")


if __name__ == "__main__":
    main()
