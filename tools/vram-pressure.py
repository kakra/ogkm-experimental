#!/usr/bin/env python3
"""Sample and evaluate the video memory pressure counters of the ogkm series.

The driver patch "nvidia: count video memory pressure events in procfs"
adds /proc/driver/nvidia/vram_pressure: one line per event (name, count,
bytes, CLOCK_MONOTONIC time of the last event in ns) that only grow. This
tool differences them over time.

  vram-pressure.py watch  [-i SECONDS]             live view with PSI-like averages
  vram-pressure.py record [-i SECONDS] -o FILE.csv record deltas until Ctrl+C
  vram-pressure.py report FILE.csv [--gap SECONDS] totals and bursts of a recording

The averages work like the load average and PSI: an exponentially decaying
mean over 10, 60 and 300 seconds. For each event it is the rate in events
per second; "pressure" is the share of time in which any event happened, in
percent, like PSI's "some" line. That share is coarse: an interval counts
as fully under pressure if one event happened in it, so use -i 1 or less.

Times in the CSV are CLOCK_MONOTONIC like the kernel log
(journalctl -k -o short-monotonic, dmesg) and nv-va-trace.bt, plus the
wall clock for the journal. Needs no root: the file is world-readable.
"""
import argparse
import csv
import datetime
import math
import signal
import sys
import time

PROC = '/proc/driver/nvidia/vram_pressure'
WINDOWS = (10, 60, 300)


def read(path):
    """Return (now_ns, {event: (count, bytes, last_ns)}) in file order."""
    now_ns, ev = None, {}
    with open(path) as f:
        for line in f:
            if line.startswith('#'):
                for tok in line.split():
                    if tok.startswith('now_ns='):
                        now_ns = int(tok[7:])
                continue
            p = line.split()
            if len(p) == 4:
                ev[p[0]] = (int(p[1]), int(p[2]), int(p[3]))
    if now_ns is None:
        now_ns = time.clock_gettime_ns(time.CLOCK_MONOTONIC)
    return now_ns, ev


def human(n):
    for unit in ('B', 'KiB', 'MiB', 'GiB'):
        if abs(n) < 1024 or unit == 'GiB':
            return f'{n:.0f} {unit}' if unit == 'B' else f'{n:.1f} {unit}'
        n /= 1024.0


class Averages:
    """Exponentially decaying means over WINDOWS, updated per interval."""

    def __init__(self, names):
        self.rate = {n: [0.0] * len(WINDOWS) for n in names}
        self.some = [0.0] * len(WINDOWS)

    def update(self, dt, deltas):
        if dt <= 0:
            return
        for i, w in enumerate(WINDOWS):
            k = math.exp(-dt / w)
            for n, d in deltas.items():
                self.rate[n][i] = self.rate[n][i] * k + (d / dt) * (1 - k)
            busy = 100.0 if any(deltas.values()) else 0.0
            self.some[i] = self.some[i] * k + busy * (1 - k)


def sampler(path, interval):
    """Yield (t0_ns, t1_ns, wall, {name: (dcount, dbytes)}) per interval."""
    t0, prev = read(path)
    names = list(prev)
    stop = []
    signal.signal(signal.SIGINT, lambda *a: stop.append(1))
    signal.signal(signal.SIGTERM, lambda *a: stop.append(1))
    while not stop:
        time.sleep(interval)
        t1, cur = read(path)
        d = {n: (cur[n][0] - prev[n][0], cur[n][1] - prev[n][1]) for n in names if n in cur}
        yield t0, t1, time.time(), d
        t0, prev = t1, cur


def cmd_watch(a):
    _, ev = read(a.file)
    names = list(ev)
    avg = Averages(names)
    for t0, t1, wall, d in sampler(a.file, a.interval):
        dt = (t1 - t0) / 1e9
        avg.update(dt, {n: c for n, (c, _) in d.items()})
        stamp = datetime.datetime.fromtimestamp(wall).strftime('%H:%M:%S')
        some = ' '.join(f'avg{w}={v:5.1f}' for w, v in zip(WINDOWS, avg.some))
        print(f'{stamp} pressure some {some}')
        for n in names:
            c, b = d.get(n, (0, 0))
            r = avg.rate[n]
            if c or any(x > 0.005 for x in r):
                rates = ' '.join(f'{x:6.2f}' for x in r)
                print(f'  {n:20} +{c:<5} {human(b):>10}   /s avg10/60/300 {rates}')
        sys.stdout.flush()


def cmd_record(a):
    _, ev = read(a.file)
    names = list(ev)
    with open(a.output, 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['mono_ns', 'interval_ns', 'wall'] +
                   [f'{n}_{k}' for n in names for k in ('count', 'bytes')])
        rows = 0
        for t0, t1, wall, d in sampler(a.file, a.interval):
            w.writerow([t1, t1 - t0, f'{wall:.3f}'] +
                       [v for n in names for v in d.get(n, (0, 0))])
            f.flush()
            rows += 1
    print(f'{rows} intervals written to {a.output}', file=sys.stderr)


def load(path):
    with open(path, newline='') as f:
        r = csv.DictReader(f)
        names = [c[:-6] for c in r.fieldnames if c.endswith('_count')]
        rows = []
        for row in r:
            rows.append((int(row['mono_ns']), int(row['interval_ns']), float(row['wall']),
                         {n: (int(row[n + '_count']), int(row[n + '_bytes'])) for n in names}))
    return names, rows


def fmt_time(mono_ns, wall):
    return (f'{datetime.datetime.fromtimestamp(wall).strftime("%Y-%m-%d %H:%M:%S")}'
            f' [{mono_ns / 1e9:12.3f}]')


def cmd_report(a):
    names, rows = load(a.csv)
    if not rows:
        sys.exit('no intervals in ' + a.csv)
    span = sum(r[1] for r in rows) / 1e9
    busy = sum(r[1] for r in rows if any(c for c, _ in r[3].values())) / 1e9
    print(f'{fmt_time(rows[0][0] - rows[0][1], rows[0][2] - rows[0][1] / 1e9)} to '
          f'{fmt_time(rows[-1][0], rows[-1][2])}: {span:.0f} s, {len(rows)} intervals')
    print(f'time with any event: {busy:.1f} s ({100 * busy / span:.1f} %)\n')
    print(f'  {"event":20} {"count":>8} {"bytes":>11} {"per min":>8} {"max/interval":>13}')
    for n in names:
        c = sum(r[3][n][0] for r in rows)
        b = sum(r[3][n][1] for r in rows)
        m = max(r[3][n][0] for r in rows)
        print(f'  {n:20} {c:8} {human(b):>11} {60 * c / span:8.2f} {m:13}')

    # Bursts: runs of intervals with events, joined across gaps up to --gap.
    bursts, cur = [], None
    for mono, iv, wall, d in rows:
        if any(c for c, _ in d.values()):
            if cur and (mono - iv - cur['end']) / 1e9 <= a.gap:
                cur['end'], cur['wall_end'] = mono, wall
            else:
                cur = {'start': mono - iv, 'end': mono, 'wall': wall - iv / 1e9,
                       'wall_end': wall, 'ev': {n: [0, 0] for n in names}}
                bursts.append(cur)
            for n, (c, b) in d.items():
                cur['ev'][n][0] += c
                cur['ev'][n][1] += b
    print(f'\n{len(bursts)} bursts (events no more than {a.gap:g} s apart):')
    for b in bursts:
        dur = (b['end'] - b['start']) / 1e9
        what = ', '.join(f'{n} {c}' + (f' ({human(s)})' if s else '')
                         for n, (c, s) in b['ev'].items() if c)
        print(f'  {fmt_time(b["start"], b["wall"])} {dur:6.1f} s  {what}')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('--file', default=PROC, help=f'counter file (default {PROC})')
    sub = ap.add_subparsers(dest='cmd', required=True)
    w = sub.add_parser('watch', help='live view')
    w.add_argument('-i', '--interval', type=float, default=1.0)
    r = sub.add_parser('record', help='write per-interval deltas to a CSV file')
    r.add_argument('-i', '--interval', type=float, default=1.0)
    r.add_argument('-o', '--output', required=True)
    p = sub.add_parser('report', help='summarize a CSV recording')
    p.add_argument('csv')
    p.add_argument('--gap', type=float, default=2.0,
                   help='join events up to this many seconds apart into one burst')
    a = ap.parse_args()
    if a.cmd != 'report':
        try:
            read(a.file)
        except FileNotFoundError:
            sys.exit(f'{a.file} not found: is the ogkm series with the counter patch loaded?')
    {'watch': cmd_watch, 'record': cmd_record, 'report': cmd_report}[a.cmd](a)


if __name__ == '__main__':
    main()
