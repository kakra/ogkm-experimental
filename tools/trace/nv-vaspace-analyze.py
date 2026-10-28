#!/usr/bin/env python3
"""Evaluate a log of tools/trace/nv-vaspace-ioctl.bt.

Replays every RM map/unmap ioctl per client and, for each failed map, prints
the caller, the requested GPU VA range and the live mappings of the same
client it overlaps (who created them, when, and which partial unmaps hit
them since). Failed unmaps are listed as well.

Mappings created before the trace started are unknown; an overlap with one
of them shows up as "no tracked overlap".
"""
import re
import sys

KV = re.compile(r'(\w+)=(\S+)')
PAGE = 0xfff


def nvos46(flags):
    page = {0: 'default', 1: '4K', 2: 'big', 3: 'both', 4: 'huge', 5: '512M', 6: '256G'}
    parts = ['pagesize=' + page.get((flags >> 8) & 0xf, hex((flags >> 8) & 0xf))]
    if flags & (1 << 15):
        parts.append('OFFSET_FIXED')
    if flags & (1 << 3):
        parts.append('PAGE_KIND_VIRTUAL')
    if flags & (1 << 14):
        parts.append('GROWS_DOWN')
    if (flags & 3) == 1:
        parts.append('READ_ONLY')
    return ' '.join(parts)


def parse(line):
    head, _, comm = line.rstrip('\n').partition(' comm=')
    fields = head.split()
    if len(fields) < 3 or not fields[0].isdigit():
        return None
    ev = {'ts': int(fields[0]) / 1000.0, 'op': fields[1], 'comm': comm}
    for k, v in KV.findall(head):
        ev[k] = int(v, 16) if v.startswith('0x') else int(v)
    return ev


def main(path):
    # client -> {lo: [hi, dma, mem, who, ts, flags, history]}
    live = {}
    stats = {'map': 0, 'MAPFAIL': 0, 'unmap': 0, 'UNMAPFAIL': 0, 'unmatched': 0}

    with open(path, errors='replace') as f:
        for raw in f:
            ev = parse(raw)
            if ev is None:
                continue
            op = ev['op']
            stats[op] = stats.get(op, 0) + 1
            who = f"{ev['comm']}/{ev['pid']}:{ev['tid']}"
            maps = live.setdefault(ev['client'], {})

            if op in ('map', 'MAPFAIL'):
                va = ev['dmaoff']
                if op == 'MAPFAIL' and (ev['flags'] & (1 << 15) or va == 0):
                    va = ev['in']
                hi = va + ((ev['len'] + PAGE) & ~PAGE) - 1
                if op == 'map':
                    maps[va] = [hi, ev['dma'], ev['mem'], who, ev['ts'], ev['flags'], []]
                    continue
                print(f"{ev['ts']:.3f} MAP FAIL status={ev['status']:#x} {who} client={ev['client']:#x} "
                      f"dma={ev['dma']:#x} mem={ev['mem']:#x} va {va:#x}-{hi:#x} "
                      f"({ev['len'] >> 10} KiB, mem off {ev['off']:#x}) flags={ev['flags']:#x} "
                      f"[{nvos46(ev['flags'])}]")
                # Without a fixed offset RM maps at the start of the virtual
                # object hDma, so a live mapping of the same hDma collides too
                hits = [(l, v) for l, v in maps.items()
                        if (l <= hi and v[0] >= va) or (va == 0 and v[1] == ev['dma'])]
                for l, (h, dma, mem, owner, t, fl, hist) in sorted(hits):
                    same = ' (same hMemory)' if mem == ev['mem'] else ''
                    print(f"  overlaps {l:#x}-{h:#x} ({(h - l + 1) >> 10} KiB) dma={dma:#x} mem={mem:#x}{same} "
                          f"mapped by {owner} {ev['ts'] - t:.3f} s earlier, flags={fl:#x}")
                    for line in hist[-5:]:
                        print(f"    {line}")
                if not hits:
                    print("  no tracked overlap (mapping older than the trace?)")

            elif op in ('unmap', 'UNMAPFAIL'):
                lo = ev['dmaoff']
                if op == 'UNMAPFAIL':
                    print(f"{ev['ts']:.3f} UNMAP FAIL status={ev['status']:#x} {who} client={ev['client']:#x} "
                          f"dma={ev['dma']:#x} mem={ev['mem']:#x} va={lo:#x} size={ev['size']:#x}")
                    own = [f"{l:#x}" for l, v in maps.items() if v[1] == ev['dma']]
                    at = [f"dma={v[1]:#x} mem={v[2]:#x}" for l, v in maps.items() if l <= lo <= v[0]]
                    print(f"  this hDma is mapped at: {', '.join(own) or '-'}; "
                          f"VA {lo:#x} belongs to: {', '.join(at) or '-'}")
                    continue
                for l, v in list(maps.items()):
                    h = v[0]
                    if l <= lo <= h:
                        del maps[l]
                        if ev['size'] == 0:
                            break
                        uhi = lo + ((ev['size'] + PAGE) & ~PAGE) - 1
                        note = f"{ev['ts']:.3f} {who} unmapped {lo:#x}-{uhi:#x} of {l:#x}-{h:#x}"
                        if l < lo:
                            maps[l] = [lo - 1] + v[1:6] + [v[6] + [note]]
                        if h > uhi:
                            maps[uhi + 1] = [h] + v[1:6] + [v[6] + [note]]
                        break
                else:
                    stats['unmatched'] += 1

    print("\n" + ", ".join(f"{k}: {v}" for k, v in stats.items()))


if __name__ == '__main__':
    if len(sys.argv) != 2:
        sys.exit(f"usage: {sys.argv[0]} <nv-vaspace log>")
    main(sys.argv[1])
