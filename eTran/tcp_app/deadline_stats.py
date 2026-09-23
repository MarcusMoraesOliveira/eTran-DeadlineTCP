#!/usr/bin/env python3
"""
Print DeadlineTCP per-connection state from the eBPF map deadline_map.

Usage: sudo ./deadline_stats.py [-i interval_s] [-a] [-c csv_file]
  -i  refresh every interval_s seconds (default: print once)
  -a  also show connections without deadline parameters (flags == 0)
  -c  append one row per connection per refresh to a CSV file

With -i, "acked_Mbps" is the measured throughput (bytes_acked delta over the
interval), the ground truth for the R_available estimators; err_bw and
err_avail are their relative errors against it.

Entries stay in the map after a connection closes, until its cc_idx is reused.
"""
import argparse
import csv
import ctypes
import json
import mmap
import os
import struct
import subprocess
import time

# struct deadline_tcp_state in common/intf/intf_ebpf.h
FMT = "<QQIIIIQQQIIQQQQQIIIIQQQQQQQQQQQQqqIIIHHQ"
FIELDS = ["deadline_ns", "total_bytes", "priority", "flags", "gen", "ebpf_seen_gen",
          "start_ns", "bytes_sent", "delivery_rate", "srtt_us", "min_rtt_us",
          "bytes_acked", "retx_bytes", "last_ack_ns", "dr_win_start_ns", "dr_win_bytes",
          "snd_high_seq", "rtt_samples", "tx_pkts", "acks",
          "r_cwnd", "r_bw", "r_available",
          "bw_max0_t", "bw_max0_v", "bw_max1_t", "bw_max1_v", "bw_max2_t", "bw_max2_v",
          "r_required", "r_target", "pacing_rate", "slack_ns", "t_remaining_ns",
          "cwnd_target", "mode", "policy_runs", "urgent_runs", "moderate_runs", "pacing_max"]
assert struct.calcsize(FMT) == 256
MODES = {0: "none", 1: "normal", 2: "moderate", 3: "URGENT", 4: "done"}

CSV_FIELDS = ["time_s", "cc_idx", "bytes_sent", "bytes_acked", "retx_bytes", "srtt_us", "min_rtt_us",
              "acked_Mbps", "delivery_rate_Mbps", "r_cwnd_Mbps", "r_bw_Mbps", "r_available_Mbps",
              "mode", "r_required_Mbps", "pacing_Mbps", "slack_us"]


def mbps(bps):
    return bps * 8 / 1e6


BPF_SYSCALL = 321  # x86_64
BPF_MAP_GET_FD_BY_ID = 14
MAX_TCP_FLOWS = 65536


class DeadlineMap:
    """deadline_map is BPF_F_MMAPABLE: map it once and read it directly."""

    def __init__(self):
        self.map_id = None
        self.mem = None
        self.refresh()

    @staticmethod
    def newest_id():
        out = subprocess.run(["bpftool", "-j", "map", "show", "name", "deadline_map"],
                             check=True, capture_output=True, text=True).stdout
        maps = json.loads(out) if out.strip() else []
        maps = maps if isinstance(maps, list) else [maps]
        # the newest map belongs to the most recently started micro_kernel
        return max((m["id"] for m in maps), default=None)

    def refresh(self):
        """(Re)open the newest deadline_map, e.g. after micro_kernel was restarted."""
        map_id = self.newest_id()
        if map_id is None:
            raise SystemExit("deadline_map not found: is micro_kernel running?")
        if map_id == self.map_id:
            return False
        if self.mem is not None:
            self.mem.close()  # also releases the old map
        self.open(map_id)
        return True

    def open(self, map_id):
        libc = ctypes.CDLL(None, use_errno=True)
        attr = ctypes.create_string_buffer(struct.pack("<I", map_id), 128)
        fd = libc.syscall(BPF_SYSCALL, BPF_MAP_GET_FD_BY_ID, attr, 128)
        if fd < 0:
            raise SystemExit(f"BPF_MAP_GET_FD_BY_ID failed: {os.strerror(ctypes.get_errno())} (run with sudo)")
        size = struct.calcsize(FMT) * MAX_TCP_FLOWS
        size = (size + mmap.PAGESIZE - 1) // mmap.PAGESIZE * mmap.PAGESIZE
        self.mem = mmap.mmap(fd, size, mmap.MAP_SHARED, mmap.PROT_READ)
        os.close(fd)
        self.map_id = map_id

    def read(self, show_all):
        sz = struct.calcsize(FMT)
        start_off = FIELDS.index("start_ns")  # start_ns != 0: slot used since micro_kernel start
        start_pos = struct.calcsize(FMT[:start_off + 1])
        rows = {}
        for idx in range(MAX_TCP_FLOWS):
            base = idx * sz
            if not struct.unpack_from("<Q", self.mem, base + start_pos)[0]:
                continue
            st = dict(zip(FIELDS, struct.unpack_from(FMT, self.mem, base)))
            if not show_all and not st["flags"]:
                continue
            rows[idx] = st
        return rows


def err(est, truth):
    return f"{(est - truth) / truth * 100:+.0f}%" if truth > 0 else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("-i", type=float, default=0)
    ap.add_argument("-a", action="store_true")
    ap.add_argument("-c")
    args = ap.parse_args()

    writer = None
    if args.c:
        new = not os.path.exists(args.c)
        f = open(args.c, "a", newline="")
        writer = csv.writer(f)
        if new:
            writer.writerow(CSV_FIELDS)

    dmap = DeadlineMap()
    prev, prev_t, t0 = {}, None, time.monotonic()
    while True:
        if dmap.refresh():
            print(f"(micro_kernel restarted: now reading deadline_map id {dmap.map_id})")
            prev, prev_t = {}, None
        now = time.monotonic()
        now_ns = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
        rows = dmap.read(args.a)

        print(f"{'cc_idx':>6} {'age_s':>7} {'dl_in_ms':>9} {'sent_MB':>9} {'acked_MB':>9} {'retx':>7} "
              f"{'srtt':>5} {'minrtt':>6} {'acked_Mbps':>10} {'r_cwnd':>9} {'r_bw':>9} {'r_avail':>9} "
              f"{'err_bw':>7} {'err_avail':>9} {'mode':>8} {'r_req':>9} {'pacing':>9} {'slack_ms':>9}")
        for idx, st in sorted(rows.items()):
            truth = 0.0
            p = prev.get(idx)
            if p and prev_t and p["start_ns"] == st["start_ns"] and st["bytes_acked"] >= p["bytes_acked"]:
                truth = mbps((st["bytes_acked"] - p["bytes_acked"]) / (now - prev_t))
            dl = (st["deadline_ns"] - now_ns) / 1e6 if st["flags"] & 0x1 else float("nan")
            r_cwnd, r_bw, r_av = mbps(st["r_cwnd"]), mbps(st["r_bw"]), mbps(st["r_available"])
            req = float("inf") if st["r_required"] == 2**64 - 1 else mbps(st["r_required"])
            print(f"{idx:>6} {(now_ns - st['start_ns']) / 1e9:>7.1f} {dl:>9.1f} "
                  f"{st['bytes_sent'] / 1e6:>9.1f} {st['bytes_acked'] / 1e6:>9.1f} {st['retx_bytes']:>7} "
                  f"{st['srtt_us']:>5} {st['min_rtt_us']:>6} {truth if truth else float('nan'):>10.1f} "
                  f"{r_cwnd:>9.1f} {r_bw:>9.1f} {r_av:>9.1f} "
                  f"{err(r_bw, truth):>7} {err(r_av, truth):>9} {MODES.get(st['mode'], '?'):>8} "
                  f"{req:>9.1f} {mbps(st['pacing_rate']):>9.1f} {st['slack_ns'] / 1e6:>9.2f}")
            if writer and truth:
                writer.writerow([f"{now - t0:.3f}", idx, st["bytes_sent"], st["bytes_acked"], st["retx_bytes"],
                                 st["srtt_us"], st["min_rtt_us"], f"{truth:.1f}", f"{mbps(st['delivery_rate']):.1f}",
                                 f"{r_cwnd:.1f}", f"{r_bw:.1f}", f"{r_av:.1f}",
                                 MODES.get(st["mode"], "?"), f"{req:.1f}", f"{mbps(st['pacing_rate']):.1f}",
                                 f"{st['slack_ns'] / 1e3:.0f}"])
        if not rows:
            print("(no connections)")
        if writer:
            f.flush()

        if not args.i:
            break
        prev, prev_t = rows, now
        time.sleep(args.i)
        print()


if __name__ == "__main__":
    main()
