#!/usr/bin/env python3
"""Decode nv-va-trace.bt output and replay a GPU-VA mapping model (original).

Layouts come from the 615.78.08 headers (nvos.h, nv-ioctl.h) and are
unchanged in 620.70.06; offsets are little-endian x86-64 with the
NV_ALIGN_BYTES(8) padding made explicit. A log whose "V <version>" line names
another release is refused: check the headers, then add it to KNOWN_RELEASES.
The model is an observer's reconstruction, not RM state: anything the trace
cannot see (objects older than the trace, kernel-internal frees) is reported
as UNKNOWN rather than guessed.

Usage: python3 -I nv_va_analyze.py trace.log [--json out.json] [--va 0xADDR]
           [--series [SECONDS]] [--csv out.csv] [--journal kernel.log]

--series prints a time series per bucket (default 60 s) and process: live
mappings and their bytes as the model sees them at the end of the bucket
(none after the process exited),
and the MAP, UNMAP and FREE calls and failures in it. --csv writes the same
rows for plotting (implies --series). --journal takes the output of
`journalctl -k -o short-monotonic` for the traced boot and counts NVRM, Xid
and VA space messages per bucket; bpftrace's nsecs and the monotonic
journal stamps share one clock as long as the system did not suspend.
"""
import argparse
import csv
import json
import re
import struct
import sys
from collections import Counter, defaultdict

# escape -> (name, {size: (struct name, decoder)})
U32, U64 = '<I', '<Q'


def _u32(b, o):
    return struct.unpack_from(U32, b, o)[0]


def _u64(b, o):
    return struct.unpack_from(U64, b, o)[0]


def nvos00(b):  # RM_FREE
    return dict(client=_u32(b, 0), parent=_u32(b, 4), handle=_u32(b, 8), status=_u32(b, 12))


def nvos21(b):  # RM_ALLOC, 32 bytes
    return dict(client=_u32(b, 0), parent=_u32(b, 4), handle=_u32(b, 8), cls=_u32(b, 12),
                params_size=_u32(b, 24), status=_u32(b, 28))


def nvos64(b):  # RM_ALLOC, 48 bytes
    return dict(client=_u32(b, 0), parent=_u32(b, 4), handle=_u32(b, 8), cls=_u32(b, 12),
                params_size=_u32(b, 32), alloc_flags=_u32(b, 36), status=_u32(b, 40))


def nvos02(b):  # RM_ALLOC_MEMORY, 48 bytes (+ int fd and padding = 56)
    return dict(client=_u32(b, 0), parent=_u32(b, 4), handle=_u32(b, 8), cls=_u32(b, 12),
                flags=_u32(b, 16), limit=_u64(b, 32), status=_u32(b, 40))


def nvos55(b):  # RM_DUP_OBJECT
    return dict(client=_u32(b, 0), parent=_u32(b, 4), handle=_u32(b, 8), client_src=_u32(b, 12),
                handle_src=_u32(b, 16), flags=_u32(b, 20), status=_u32(b, 24))


def nvos46(b):  # RM_MAP_MEMORY_DMA
    return dict(client=_u32(b, 0), device=_u32(b, 4), dma=_u32(b, 8), memory=_u32(b, 12),
                offset=_u64(b, 16), length=_u64(b, 24), flags=_u32(b, 32), flags2=_u32(b, 36),
                kind=_u32(b, 40), va=_u64(b, 48), status=_u32(b, 56))


def nvos47(b):  # RM_UNMAP_MEMORY_DMA
    return dict(client=_u32(b, 0), device=_u32(b, 4), dma=_u32(b, 8), memory=_u32(b, 12),
                flags=_u32(b, 16), va=_u64(b, 24), size=_u64(b, 32), status=_u32(b, 40))


# Driver releases whose escapes and parameter blocks match the decoders below.
KNOWN_RELEASES = ('615.78.08', '620.70.06')

ESCAPES = {
    0x27: ('ALLOC_MEMORY', {48: nvos02, 56: nvos02}),
    0x29: ('FREE', {16: nvos00}),
    0x2B: ('ALLOC', {32: nvos21, 48: nvos64}),
    0x34: ('DUP', {28: nvos55}),
    0x57: ('MAP', {64: nvos46}),
    0x58: ('UNMAP', {48: nvos47}),
}
# Fields the caller supplies; a change between entry and exit means userspace
# (or something else) rewrote the buffer while the call was in the kernel.
IN_FIELDS = {
    'FREE': ('client', 'parent', 'handle'),
    'ALLOC': ('client', 'parent', 'cls'),
    'ALLOC_MEMORY': ('client', 'parent', 'cls', 'flags'),
    'DUP': ('client', 'parent', 'client_src', 'handle_src', 'flags'),
    'MAP': ('client', 'device', 'dma', 'memory', 'offset', 'length', 'flags', 'flags2', 'kind'),
    'UNMAP': ('client', 'device', 'dma', 'memory', 'flags', 'va', 'size'),
}

LINE = re.compile(r'^(?P<kind>[EX]) (?P<ns>\d+) (?P<pid>-?\d+) (?P<tid>-?\d+) fd=(?P<fd>-?\d+) '
                  r'nr=0x(?P<nr>[0-9a-f]+) size=(?P<size>\d+) (?:xfer=(?P<xfer>\d)|ret=(?P<ret>-?\d+)) '
                  r'blk=(?P<blk>\S*) comm=(?P<comm>.*)$')
SIMPLE = re.compile(r'^(?P<kind>[OCP]) (?P<ns>\d+) (?P<pid>-?\d+) (?P<tid>-?\d+) (?P<rest>.*)$')
HEX = re.compile(r'\\x([0-9a-fA-F]{2})')


def raw(blk):
    if blk == 'UNSUPPORTED_SIZE':
        return None
    data = bytes(int(h, 16) for h in HEX.findall(blk))
    return data if len(HEX.sub('', blk)) == 0 else None


def parse(lines):
    """Pair entry/exit records per thread; yield ordered call records."""
    pending, out, stack = {}, [], None
    for number, line in enumerate(lines, 1):
        line = line.rstrip('\n')
        if stack is not None:
            if line == 'S-END':
                out.append(stack)
                stack = None
            elif line.strip():
                stack['frames'].append(line.strip())
            continue
        if line.startswith('V '):
            version = line[2:].strip()
            if version not in KNOWN_RELEASES:
                raise ValueError(f'line {number}: driver {version} is not one of {", ".join(KNOWN_RELEASES)}; '
                                 'check the struct layouts before decoding this log')
            out.append(dict(kind='VERSION', version=version, line=number))
            continue
        if line.startswith('S '):
            parts = line.split()
            stack = dict(kind='STACK', ns=int(parts[1]), pid=int(parts[2]), tid=int(parts[3]),
                         status=parts[4], frames=[], line=number)
            continue
        m = LINE.match(line)
        if m:
            nr, size = int(m['nr'], 16), int(m['size'])
            name, decoders = ESCAPES.get(nr, (None, {}))
            data, decode = raw(m['blk']), decoders.get(size)
            fields = decode(data) if (decode and data is not None and len(data) == size) else None
            key = int(m['tid'])
            if m['kind'] == 'E':
                pending[key] = dict(kind='CALL', op=name or hex(nr), nr=nr, size=size, pid=int(m['pid']),
                                    tid=key, fd=int(m['fd']), xfer=m['xfer'] == '1', comm=m['comm'],
                                    t_enter=int(m['ns']), entry=fields, line=number)
            else:
                call = pending.pop(key, None)
                if call is None:
                    out.append(dict(kind='ORPHAN_EXIT', tid=key, line=number))
                    continue
                call.update(t_exit=int(m['ns']), ret=int(m['ret']), exit=fields)
                out.append(call)
            continue
        m = SIMPLE.match(line)
        if m:
            out.append(dict(kind={'O': 'OPEN', 'C': 'CLOSE', 'P': 'PROC_EXIT'}[m['kind']], ns=int(m['ns']),
                            pid=int(m['pid']), tid=int(m['tid']), rest=m['rest'], line=number))
        elif line.strip() and not line.startswith('Attaching'):
            out.append(dict(kind='UNPARSED', text=line[:200], line=number))
    for call in pending.values():
        call.update(kind='NO_EXIT')
        out.append(call)
    return out


class Model:
    """Live mappings per (client, dma); objects per (client, handle)."""

    def __init__(self):
        self.maps = defaultdict(dict)        # (client, dma) -> {va: record}
        self.objects = {}                    # (client, handle) -> record
        self.freed = {}                      # (client, handle) -> last free record
        self.va_history = defaultdict(list)  # va -> [event summaries]
        self.findings = []
        self.counts = Counter()

    def note(self, va, text):
        self.va_history[va].append(text)

    def live_at(self, client, va):
        """Live mappings in this client that start at va or contain it."""
        start, inside = [], []
        for (c, dma), table in self.maps.items():
            if c != client:
                continue
            for base, rec in table.items():
                if base == va:
                    start.append((dma, rec))
                elif base < va < base + max(rec['length'], 1):
                    inside.append((dma, rec))
        return start, inside

    def drop_children(self, client, handle, call):
        """RM frees descendants with the object; the trace only knows observed parents."""
        removed = []
        for key, rec in list(self.objects.items()):
            if key[0] == client and rec.get('parent') == handle:
                removed += self.drop_children(client, key[1], call)
                del self.objects[key]
                removed.append(key[1])
        return removed

    def implicit_unmaps(self, client, handle, call, cause):
        for (c, dma), table in self.maps.items():
            if c != client:
                continue
            for va, rec in list(table.items()):
                if handle in (dma, rec['memory']):
                    del table[va]
                    self.counts['implicit_unmap_inferred'] += 1
                    self.note(va, f"t={call['t_enter']} INFERRED_IMPLICIT_UNMAP dma=0x{dma:x} "
                                  f"memory=0x{rec['memory']:x} cause={cause}(0x{handle:x}) tid={call['tid']}")

    def apply(self, call):
        op, e, x = call['op'], call['entry'], call['exit']
        if e is None or x is None:
            self.findings.append(dict(type='UNDECODED', line=call['line'], op=op, size=call['size']))
            return
        self.counts[(op, 'status', x['status'])] += 1
        changed = [f for f in IN_FIELDS.get(op, ()) if e.get(f) != x.get(f)]
        if changed:
            self.findings.append(dict(type='IN_FIELD_CHANGED_DURING_CALL', op=op, line=call['line'],
                                      tid=call['tid'], fields={f: (e[f], x[f]) for f in changed}))
        ok = x['status'] == 0
        client = e['client']
        if op in ('ALLOC', 'ALLOC_MEMORY', 'DUP') and ok:
            key = (client, x['handle'])
            if key in self.freed:
                self.counts['handle_reused_after_free'] += 1
            if key in self.objects:
                self.findings.append(dict(type='ALLOC_OVER_LIVE_HANDLE', line=call['line'], handle=x['handle']))
            self.objects[key] = dict(parent=e['parent'], cls=e.get('cls'), op=op, t=call['t_exit'],
                                     tid=call['tid'], src=(e.get('client_src'), e.get('handle_src')))
        elif op == 'FREE' and ok:
            key = (client, e['handle'])
            if key not in self.objects:
                self.counts['free_of_object_older_than_trace'] += 1
            children = self.drop_children(client, e['handle'], call)
            self.objects.pop(key, None)
            self.freed[key] = call
            for handle in [e['handle']] + children:
                self.implicit_unmaps(client, handle, call, 'FREE')
        elif op == 'MAP':
            if ok:
                table = self.maps[(client, e['dma'])]
                rec = dict(memory=e['memory'], length=e['length'], offset=e['offset'], t=call['t_exit'],
                           tid=call['tid'], pid=call['pid'], line=call['line'], flags=e['flags'])
                start, inside = self.live_at(client, x['va'])
                if start or inside:
                    self.findings.append(dict(type='MAP_RETURNED_LIVE_VA', line=call['line'], va=x['va'],
                                              dma=e['dma'], other=[(d, r['line']) for d, r in start + inside]))
                table[x['va']] = rec
                self.note(x['va'], f"t={call['t_exit']} MAP ok dma=0x{e['dma']:x} memory=0x{e['memory']:x} "
                                   f"len=0x{e['length']:x} tid={call['tid']} line={call['line']}")
            else:
                self.findings.append(dict(type='MAP_FAILED', line=call['line'], status=x['status'],
                                          dma=e['dma'], memory=e['memory'], requested_va=e.get('va'),
                                          tid=call['tid'], comm=call['comm']))
        elif op == 'UNMAP':
            va, table = e['va'], self.maps[(client, e['dma'])]
            if ok:
                if va in table:
                    rec = table.pop(va)
                    self.note(va, f"t={call['t_exit']} UNMAP ok dma=0x{e['dma']:x} tid={call['tid']} "
                                  f"(mapped line {rec['line']})")
                else:
                    self.counts['unmap_ok_of_mapping_older_than_trace'] += 1
                    self.note(va, f"t={call['t_exit']} UNMAP ok UNKNOWN_MAPPING dma=0x{e['dma']:x}")
                return
            start, inside = self.live_at(client, va)
            own = [d for d, _ in start if d == e['dma']]
            # Earlier events only: this failure is recorded after classification.
            history = [h for h in self.va_history[va] if f"dma=0x{e['dma']:x}" in h]
            self.note(va, f"t={call['t_exit']} UNMAP FAIL status=0x{x['status']:x} dma=0x{e['dma']:x} "
                          f"tid={call['tid']} comm={call['comm']} line={call['line']}")
            if own:
                cls = 'LIVE_SAME_DMA'                       # RM refused although the model says it is mapped
            elif start:
                cls = 'START_OF_OTHER_DMA_MAPPING'
            elif inside:
                cls = 'INSIDE_OTHER_MAPPING'
            elif history:
                cls = 'STALE_SAME_DMA'                      # this dma had the VA earlier; it is gone now
            else:
                cls = 'NEVER_SEEN'
            self.counts[('unmap_fail', cls)] += 1
            self.findings.append(dict(type='UNMAP_FAILED', cls=cls, line=call['line'], status=x['status'],
                                      va=va, dma=e['dma'], memory=e['memory'], tid=call['tid'], comm=call['comm'],
                                      other=[dict(dma=d, mapped_line=r['line'], memory=r['memory'],
                                                  mapped_tid=r['tid']) for d, r in start + inside],
                                      dma_history=history[-6:]))

    def proc_exit(self, pid):
        self.counts['process_exit'] += 1


JOURNAL = re.compile(r'^\[\s*(?P<s>\d+)\.(?P<us>\d{6})\]')
JOURNAL_MATCH = re.compile(r"NVRM|Xid|gpu_vaspace|can't update VA space")
SERIES_FIELDS = ('bucket', 't_mono_s', 'pid', 'comm', 'live', 'live_mib', 'map', 'unmap', 'free',
                 'map_fail', 'unmap_fail', 'kmsg')


def journal_marks(path):
    """Monotonic ns of the kernel messages that matter for the VA space."""
    marks = []
    with open(path, errors='replace') as stream:
        for line in stream:
            m = JOURNAL.match(line)
            if m and JOURNAL_MATCH.search(line):
                marks.append(int(m['s']) * 1_000_000_000 + int(m['us']) * 1000)
    return marks


class Series:
    """Rows per (bucket, pid), filled while the model replays the calls."""

    def __init__(self, width_ns, marks=()):
        self.width, self.marks = width_ns, sorted(marks)
        self.t0 = self.bucket = None
        self.ops = defaultdict(Counter)   # pid -> counts in the current bucket
        self.comms = defaultdict(Counter)  # pid -> thread names seen
        self.exited = set()                # RM drops the mappings of a client with its process
        self.rows = []

    def advance(self, t, model):
        if self.t0 is None:
            self.t0, self.bucket = t, 0
        bucket = (t - self.t0) // self.width
        if bucket > self.bucket:
            self.flush(model)
            self.bucket = bucket

    def count(self, call):
        e, x = call['entry'], call['exit']
        if e is None or x is None:
            return
        ok = x['status'] == 0
        name = {'MAP': 'map', 'UNMAP': 'unmap', 'FREE': 'free'}.get(call['op'])
        if name:
            self.ops[call['pid']][name if ok or name == 'free' else name + '_fail'] += 1
        self.comms[call['pid']][call['comm']] += 1

    def flush(self, model):
        if self.t0 is None:
            return
        start = self.t0 + self.bucket * self.width
        kmsg = sum(1 for t in self.marks if start <= t < start + self.width)
        live = defaultdict(lambda: [0, 0])
        for table in model.maps.values():
            for rec in table.values():
                if rec['pid'] in self.exited:
                    continue
                live[rec['pid']][0] += 1
                live[rec['pid']][1] += rec['length']
        for pid in sorted(set(live) | set(self.ops)):
            ops, (n, size) = self.ops.get(pid, Counter()), live.get(pid, (0, 0))
            comm = self.comms[pid].most_common(1)[0][0] if self.comms[pid] else '?'
            self.rows.append(dict(bucket=self.bucket, t_mono_s=start // 1_000_000_000, pid=pid, comm=comm,
                                  live=n, live_mib=round(size / 2**20, 1), map=ops['map'], unmap=ops['unmap'],
                                  free=ops['free'], map_fail=ops['map_fail'], unmap_fail=ops['unmap_fail'],
                                  kmsg=kmsg))
        if not live and not self.ops and kmsg:
            self.rows.append(dict(bucket=self.bucket, t_mono_s=start // 1_000_000_000, pid=0, comm='-',
                                  live=0, live_mib=0, map=0, unmap=0, free=0, map_fail=0, unmap_fail=0,
                                  kmsg=kmsg))
        self.ops.clear()


def run(path, focus=None, series_s=None, journal=None):
    with open(path, errors='replace') as stream:
        records = parse(stream)
    model = Model()
    series = Series(series_s * 1_000_000_000, journal_marks(journal) if journal else ()) if series_s else None
    stacks = defaultdict(list)
    for rec in records:
        if rec['kind'] == 'CALL':
            if series:
                series.advance(rec['t_exit'], model)
            model.apply(rec)
            if series:
                series.count(rec)
        elif rec['kind'] == 'STACK':
            stacks[rec['tid']].append(rec)
        elif rec['kind'] in ('NO_EXIT', 'ORPHAN_EXIT', 'UNPARSED'):
            model.findings.append(dict(type=rec['kind'], line=rec['line']))
        elif rec['kind'] == 'PROC_EXIT':
            model.proc_exit(rec['pid'])
            if series:
                series.advance(rec['ns'], model)
                series.exited.add(rec['pid'])
    calls = [r for r in records if r['kind'] == 'CALL']
    report = dict(
        driver=next((r['version'] for r in records if r['kind'] == 'VERSION'), None),
        calls=len(calls),
        by_op=dict(Counter(r['op'] for r in calls)),
        xfer_calls=sum(1 for r in calls if r['xfer']),
        status=[dict(op=k[0], status=hex(k[2]), n=v) for k, v in model.counts.items()
                if isinstance(k, tuple) and k[1] == 'status'],
        unmap_fail_classes={k[1]: v for k, v in model.counts.items()
                            if isinstance(k, tuple) and k[0] == 'unmap_fail'},
        counters={k: v for k, v in model.counts.items() if isinstance(k, str)},
        findings=model.findings,
        failure_stacks={tid: [s['frames'] for s in v] for tid, v in stacks.items()},
        live_mappings_at_end=sum(len(t) for t in model.maps.values()),
    )
    if focus is not None:
        report['va_history'] = model.va_history.get(focus, [])
    if series:
        series.flush(model)
        report['series'] = series.rows
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('trace')
    parser.add_argument('--json')
    parser.add_argument('--va', type=lambda s: int(s, 0))
    parser.add_argument('--series', nargs='?', type=int, const=60, metavar='SECONDS')
    parser.add_argument('--csv')
    parser.add_argument('--journal')
    args = parser.parse_args()
    if (args.csv or args.journal) and not args.series:
        args.series = 60
    try:
        report = run(args.trace, args.va, args.series, args.journal)
    except ValueError as err:
        sys.exit(f'{args.trace}: {err}')
    if args.json:
        with open(args.json, 'w') as out:
            json.dump(report, out, indent=1, default=str)
    print(f"driver {report['driver'] or 'unknown (log without V line)'}")
    print(f"calls {report['calls']} by_op {report['by_op']} xfer {report['xfer_calls']}")
    for row in report['status']:
        print(f"  {row['op']:13s} status {row['status']:>6s} x{row['n']}")
    print('unmap failures by class:', report['unmap_fail_classes'] or 'none')
    print('counters:', report['counters'])
    kinds = Counter(f['type'] for f in report['findings'])
    print('findings:', dict(kinds))
    for f in report['findings']:
        if f['type'] in ('UNMAP_FAILED', 'MAP_FAILED', 'IN_FIELD_CHANGED_DURING_CALL', 'MAP_RETURNED_LIVE_VA'):
            print(' ', json.dumps(f, default=str)[:400])
    if args.va is not None:
        print(f'history of VA 0x{args.va:x}:')
        for h in report['va_history']:
            print('  ', h)
    if 'series' in report:
        print(f'series per {args.series} s (live: model state at the end of the bucket, '
              'mappings older than the trace are not counted):')
        print(f"{'bucket':>6} {'t_mono_s':>9} {'pid':>7} {'comm':15s} {'live':>6} {'live_mib':>9} "
              f"{'map':>5} {'unmap':>5} {'free':>5} {'mapF':>4} {'unmapF':>6} {'kmsg':>4}")
        for r in report['series']:
            print(f"{r['bucket']:6d} {r['t_mono_s']:9d} {r['pid']:7d} {r['comm'][:15]:15s} {r['live']:6d} "
                  f"{r['live_mib']:9.1f} {r['map']:5d} {r['unmap']:5d} {r['free']:5d} {r['map_fail']:4d} "
                  f"{r['unmap_fail']:6d} {r['kmsg']:4d}")
        if args.csv:
            with open(args.csv, 'w', newline='') as out:
                writer = csv.DictWriter(out, fieldnames=SERIES_FIELDS)
                writer.writeheader()
                writer.writerows(report['series'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
