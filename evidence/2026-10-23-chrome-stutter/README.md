# Chrome stutter under RAM/IO load: NVIDIA ruled out (2026-10-23)

A negative result, kept because it bounds the sysmem problem: the desktop
applications that allocate sysmem through the NVIDIA driver did not stall on
memory in a week of uptime.

## Setup

- System: see `docs/system.md`
- Driver: 615.78.08, **stock** open modules
- Kernel: 6.18.57 before the reboot, 6.18.58 after; `scx_lavd` scheduler
- Snapshot 2026-10-23 03:50 to 04:05 (local, CEST) at 7 days uptime, during a
  backup, a package build and a Steam download. Chrome was idle (no user at
  the machine), so the numbers show background exposure, not a captured
  stutter.

## Files

| Directory | Content |
|---|---|
| `baseline-pre-reboot-20261023-0402/` | `host-state.txt`: meminfo, buddyinfo, full vmstat, PSI (global, Chrome and KWin cgroups), `vm.*` sysctls, THP/mTHP stats, zswap, BDI limits, IRQ threads, NVRM message counts of the last 7 days; `pagetypeinfo.txt` |
| `post-reboot-20261023-0448/` | The same, 10 minutes after the reboot into the patched driver |

## Result

- Chrome's cgroup, browser up about 4 h: memory PSI 3.5 s total, IO PSI
  2124 s some / 2107 s full. Memory PSI includes direct reclaim and direct
  compaction, also inside NVIDIA ioctls of Chrome's GPU process, so the sysmem
  fallback and compaction chain does not explain stutter in Chrome.
- KWin's cgroup over 7 days: memory PSI 0.13 s, IO 13 s. The compositor did
  not stall on memory either.
- NVRM `NV_ERR_NO_MEMORY` in the last 7 days: all are the UVM shadow fault
  buffer retry (`mem_desc.c:1348` → `_kgmmuClientShadowFaultBufferPagesAllocate
  ... retrying with default page size` → `system_mem.c:448` →
  `nv_gpu_ops.c:5071`), at UVM client starts; none from a Chrome allocation.
- Where tasks blocked (40 s of D-state sampling): `balance_dirty_pages` and
  page waits on a slow HDD-backed file system. The stutter is an IO
  writeback problem of this system, not a driver problem.

### Pageblock types

`pagetypeinfo`, zone Normal, Unmovable/Movable/Reclaimable pageblocks: after
7 days 2129/13064/291 (14 % unmovable); 10 minutes after the reboot
3437/11630/416 (22 %). Within 10 minutes of boot `compact_stall` was already
5725 with `compact_fail` 4763 (83 %), and zone Normal had only 3 free order-7
blocks and one order-8 block.
