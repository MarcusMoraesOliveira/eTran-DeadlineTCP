#!/usr/bin/env python3
"""
Print DeadlineTCP per-connection state from the eBPF map deadline_map.

Usage: sudo ./deadline_stats.py [-i interval_s] [-a]
  -i  refresh every interval_s seconds (default: print once)
  -a  also show connections without deadline parameters (flags == 0)

Entries stay in the map after a connection closes, until its cc_idx is reused.
"""
import argparse
import json
import struct
import subprocess
import time

# struct deadline_tcp_state in common/intf/intf_ebpf.h
FMT = "<QQIIIIQQQIIQQQQQIIIIQ"
FIELDS = ["deadline_ns", "total_bytes", "priority", "flags", "gen", "ebpf_seen_gen",
          "start_ns", "bytes_sent", "delivery_rate", "srtt_us", "min_rtt_us",
          "bytes_acked", "retx_bytes", "last_ack_ns", "dr_win_start_ns", "dr_win_bytes",
          "snd_high_seq", "rtt_samples", "tx_pkts", "acks", "reserved"]
assert struct.calcsize(FMT) == 128


def to_bytes(v):
    return bytes(int(b, 16) for b in v)


def dump(show_all):
    out = subprocess.run(["bpftool", "-j", "map", "dump", "name", "deadline_map"],
                         check=True, capture_output=True, text=True).stdout
    now_ns = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    rows = []
    for e in json.loads(out):
        st = dict(zip(FIELDS, struct.unpack(FMT, to_bytes(e["value"]))))
        if not st["start_ns"] or (not show_all and not st["flags"]):
            continue
        st["cc_idx"] = struct.unpack("<I", to_bytes(e["key"]))[0]
        rows.append(st)

    print(f"{'cc_idx':>6} {'age_ms':>8} {'deadline_in_ms':>14} {'total':>10} {'prio':>4} "
          f"{'sent':>10} {'acked':>10} {'retx':>8} {'pkts':>7} {'acks':>7} "
          f"{'srtt_us':>7} {'minrtt':>6} {'rate_Mbps':>9}")
    for st in rows:
        dl = (st["deadline_ns"] - now_ns) / 1e6 if st["flags"] & 0x1 else float("nan")
        print(f"{st['cc_idx']:>6} {(now_ns - st['start_ns']) / 1e6:>8.1f} {dl:>14.1f} "
              f"{st['total_bytes']:>10} {st['priority']:>4} "
              f"{st['bytes_sent']:>10} {st['bytes_acked']:>10} {st['retx_bytes']:>8} "
              f"{st['tx_pkts']:>7} {st['acks']:>7} {st['srtt_us']:>7} {st['min_rtt_us']:>6} "
              f"{st['delivery_rate'] * 8 / 1e6:>9.1f}")
    if not rows:
        print("(no connections)")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", type=float, default=0)
    ap.add_argument("-a", action="store_true")
    args = ap.parse_args()
    while True:
        dump(args.a)
        if not args.i:
            break
        time.sleep(args.i)
        print()


if __name__ == "__main__":
    main()
