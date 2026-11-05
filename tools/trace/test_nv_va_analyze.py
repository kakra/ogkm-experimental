"""Synthetic self-test for nv_va_analyze.py: CPU only, no device, no tracer run.

Builds log lines in the exact tracer format from header-derived struct packing
and checks each failure classification the analyzer claims to make.
"""
from pathlib import Path
import struct
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import nv_va_analyze as A  # noqa: E402

CLIENT, DEVICE = 0xC1D00001, 0xCAFE0001


def hexblk(data):
    return ''.join(f'\\x{b:02x}' for b in data)


def nvos46(dma, memory, length, va=0, status=0):
    return struct.pack('<IIIIQQIIIIQI4x', CLIENT, DEVICE, dma, memory, 0, length, 0, 0, 0, 0, va, status)


def nvos47(dma, memory, va, status=0, size=0):
    return struct.pack('<IIIII4xQQI4x', CLIENT, DEVICE, dma, memory, 0, va, size, status)


def nvos00(handle, parent=DEVICE, status=0):
    return struct.pack('<IIII', CLIENT, parent, handle, status)


def nvos64(handle, parent, cls, status=0):
    return struct.pack('<IIIIQQIII4x', CLIENT, parent, handle, cls, 0, 0, 0, 0, status)


class Log:
    def __init__(self):
        self.lines, self.t = [], 1000

    def call(self, nr, entry, exit_=None, tid=7, comm='vkd3d_queue'):
        self.t += 10
        self.lines.append(f'E {self.t} 100 {tid} fd=5 nr=0x{nr:x} size={len(entry)} xfer=0 blk={hexblk(entry)} comm={comm}')
        self.t += 5
        self.lines.append(f'X {self.t} 100 {tid} fd=5 nr=0x{nr:x} size={len(entry)} ret=0 blk={hexblk(exit_ or entry)} comm={comm}')

    def map(self, dma, memory, length, va, status=0, tid=7):
        self.call(0x57, nvos46(dma, memory, length), nvos46(dma, memory, length, va, status), tid)

    def unmap(self, dma, memory, va, status=0, tid=7, exit_va=None):
        self.call(0x58, nvos47(dma, memory, va), nvos47(dma, memory, va if exit_va is None else exit_va, status), tid)

    def run(self, va=None):
        with tempfile.NamedTemporaryFile('w', suffix='.log', delete=False) as f:
            f.write('\n'.join(self.lines) + '\n')
        return A.run(f.name, va)


class AnalyzerTests(unittest.TestCase):
    def test_layout_sizes_match_header_sizes(self):
        self.assertEqual(len(nvos46(1, 2, 3)), 64)
        self.assertEqual(len(nvos47(1, 2, 3)), 48)
        self.assertEqual(len(nvos00(1)), 16)
        self.assertEqual(len(nvos64(1, 2, 3)), 48)
        d = A.nvos46(nvos46(0x11, 0x22, 0x1000, 0x27bb60000, 0))
        self.assertEqual((d['dma'], d['memory'], d['length'], d['va'], d['status']), (0x11, 0x22, 0x1000, 0x27bb60000, 0))
        d = A.nvos47(nvos47(0x11, 0x22, 0x28720000, 0x57))
        self.assertEqual((d['dma'], d['va'], d['status']), (0x11, 0x28720000, 0x57))

    def test_unmap_failure_classes(self):
        log = Log()
        log.map(0xA, 0x100, 0x10000, 0x1000000)              # A live
        log.map(0xB, 0x200, 0x10000, 0x2000000)              # B live
        log.unmap(0xA, 0x100, 0x2000000, status=0x57)         # A's handle, B's start VA
        log.unmap(0xA, 0x100, 0x2000800, status=0x57)         # inside B
        log.unmap(0xA, 0x100, 0x1000000)                      # A ok
        log.unmap(0xA, 0x100, 0x1000000, status=0x57)         # stale on same dma
        log.unmap(0xA, 0x100, 0x9000000, status=0x57)         # never seen
        log.map(0xC, 0x300, 0x1000, 0x3000000)
        log.unmap(0xC, 0x300, 0x3000000, status=0x57)         # refused while live in the model
        r = log.run(0x2000000)
        self.assertEqual(r['unmap_fail_classes'], {'START_OF_OTHER_DMA_MAPPING': 1, 'INSIDE_OTHER_MAPPING': 1,
                                                   'STALE_SAME_DMA': 1, 'NEVER_SEEN': 1, 'LIVE_SAME_DMA': 1})
        first = [f for f in r['findings'] if f['type'] == 'UNMAP_FAILED'][0]
        self.assertEqual(first['other'][0]['dma'], 0xB)
        self.assertTrue(any('UNMAP FAIL' in h for h in r['va_history']))

    def test_failed_unmap_keeps_other_mapping_live(self):
        log = Log()
        log.map(0xB, 0x200, 0x10000, 0x2000000)
        log.unmap(0xA, 0x100, 0x2000000, status=0x57)
        log.unmap(0xB, 0x200, 0x2000000)                      # B still removable through its own handle
        r = log.run()
        self.assertEqual(r['counters'].get('unmap_ok_of_mapping_older_than_trace'), None)
        self.assertEqual(r['live_mappings_at_end'], 0)

    def test_entry_exit_rewrite_is_flagged(self):
        log = Log()
        log.map(0xA, 0x100, 0x10000, 0x1000000)
        log.unmap(0xA, 0x100, 0x1000000, exit_va=0x5000000)   # buffer rewritten during the call
        r = log.run()
        changed = [f for f in r['findings'] if f['type'] == 'IN_FIELD_CHANGED_DURING_CALL']
        self.assertEqual(len(changed), 1)
        self.assertEqual(changed[0]['fields'], {'va': (0x1000000, 0x5000000)})

    def test_free_infers_implicit_unmap_and_handle_reuse(self):
        log = Log()
        log.call(0x2B, nvos64(0x100, DEVICE, 0x40), nvos64(0x100, DEVICE, 0x40))
        log.map(0xA, 0x100, 0x10000, 0x1000000)
        log.call(0x29, nvos00(0x100))                          # free the memory object
        log.call(0x2B, nvos64(0x100, DEVICE, 0x40), nvos64(0x100, DEVICE, 0x40))  # same handle again
        log.unmap(0xA, 0x100, 0x1000000, status=0x57)
        r = log.run(0x1000000)
        self.assertEqual(r['counters']['implicit_unmap_inferred'], 1)
        self.assertEqual(r['counters']['handle_reused_after_free'], 1)
        self.assertEqual(r['unmap_fail_classes'], {'STALE_SAME_DMA': 1})
        self.assertTrue(any('INFERRED_IMPLICIT_UNMAP' in h for h in r['va_history']))

    def test_stack_and_unsupported_lines(self):
        log = Log()
        log.unmap(0xA, 0x100, 0x1000, status=0x57, tid=9)
        log.lines += ['S 2000 100 9 status=0x57', '        7f00deadbeef wine_thread+0x10', 'S-END',
                      'E 3000 100 11 fd=5 nr=0x58 size=40 xfer=0 blk=UNSUPPORTED_SIZE comm=x',
                      'X 3005 100 11 fd=5 nr=0x58 size=40 ret=0 blk=UNSUPPORTED_SIZE comm=x']
        r = log.run()
        self.assertEqual(r['failure_stacks'][9][0], ['7f00deadbeef wine_thread+0x10'])
        self.assertTrue(any(f['type'] == 'UNDECODED' for f in r['findings']))

    def test_driver_version_line(self):
        log = Log()
        log.lines.append('V 620.70.06')
        log.map(0xA, 0x100, 0x1000, 0x200000)
        self.assertEqual(log.run()['driver'], '620.70.06')
        log.lines[0] = 'V 999.1.2'
        with self.assertRaises(ValueError):
            log.run()


if __name__ == '__main__':
    unittest.main(verbosity=2)
