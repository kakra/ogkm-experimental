#!/usr/bin/env python3
"""Race or logic error? For every failed unmap/map in an nv-va-trace.bt log,
find the earlier RM calls on the same virtual object (hDma) and the call that
last owned the VA, and report thread, time gap and ioctl overlap."""
import re, sys, collections, statistics

def blk(l):
    return bytes(int(x, 16) for x in re.search(r'blk=(\S+)', l).group(1).split('\\x')[1:])

u32 = lambda b, o: int.from_bytes(b[o:o + 4], 'little')
u64 = lambda b, o: int.from_bytes(b[o:o + 8], 'little')

calls, pend = [], {}
for l in open(sys.argv[1], errors='replace'):
    if l[:2] not in ('E ', 'X '):
        continue
    p = l.split()
    t, tid, nr = int(p[1]), int(p[3]), p[5]
    if nr not in ('nr=0x57', 'nr=0x58', 'nr=0x29'):
        continue
    if l[0] == 'E':
        pend[tid] = t
        continue
    b = blk(l); comm = l.rsplit('comm=', 1)[1].strip()
    c = dict(t0=pend.pop(tid, t), t1=t, tid=tid, comm=comm)
    if nr == 'nr=0x57' and len(b) >= 64:
        c.update(op='MAP', h=u32(b, 8), mem=u32(b, 12), flags=u32(b, 32), va=u64(b, 48), st=u32(b, 56))
    elif nr == 'nr=0x58' and len(b) >= 48:
        c.update(op='UNMAP', h=u32(b, 8), va=u64(b, 24), st=u32(b, 40))
    elif nr == 'nr=0x29' and len(b) >= 16:
        c.update(op='FREE', h=u32(b, 8), st=u32(b, 12))
    else:
        continue
    calls.append(c)
calls.sort(key=lambda c: c['t0'])

by_h = collections.defaultdict(list)
for i, c in enumerate(calls):
    by_h[c['h']].append(i)
va_owner = {}  # VA -> index of last successful MAP there
res = collections.Counter(); gaps = collections.defaultdict(list); overlap = 0
for i, c in enumerate(calls):
    if c['op'] == 'MAP' and c['st'] == 0:
        va_owner[c['va']] = i
    if c['op'] not in ('MAP', 'UNMAP') or c['st'] == 0:
        continue
    # concurrent calls on the same handle from another thread
    for j in by_h[c['h']]:
        d = calls[j]
        if j != i and d['tid'] != c['tid'] and d['t0'] <= c['t1'] and c['t0'] <= d['t1']:
            overlap += 1
    prev = [j for j in by_h[c['h']] if j < i]
    if prev:
        p = calls[prev[-1]]
        k = f"{c['op']} fail: last op on same handle = {p['op']}{'(fail)' if p['st'] else ''}, {'same' if p['tid'] == c['tid'] else 'other'} thread"
        res[k] += 1; gaps[k].append((c['t0'] - p['t1']) / 1e6)
    else:
        res[f"{c['op']} fail: handle never seen before"] += 1
    if c['op'] == 'UNMAP':
        o = va_owner.get(c['va'])
        if o is None:
            res['UNMAP fail: VA never mapped in trace'] += 1
        else:
            m = calls[o]
            k = f"UNMAP fail: VA last mapped by {'same' if m['h'] == c['h'] else 'other'} handle, {'same' if m['tid'] == c['tid'] else 'other'} thread"
            res[k] += 1; gaps[k].append((c['t0'] - m['t1']) / 1e6)
print(f"failed calls overlapping a call on the same handle from another thread: {overlap}")
for k, v in sorted(res.items()):
    g = gaps.get(k)
    s = f"  gap ms min {min(g):.3f} median {statistics.median(g):.3f} max {max(g):.0f}" if g else ''
    print(f"{v:5d}  {k}{s}")
