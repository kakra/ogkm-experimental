# Elite Dangerous spilling video memory to system memory, seen through the counters (2026-11-18)

## Setup

- System: see `docs/system.md`; differences: kernel 7.3.4-gentoo with the
  sleepable BPF arena allocation backported from 7.4 (`kakra/linux`
  `rebase-7.3/platform`), uptime 3 days.
- Driver: 620.70.06, series `ogkm/620.70.06` at `b7533472` (144 patches,
  including the video memory pressure counters of patch 144).
- Workload: Elite Dangerous: Odyssey (Steam, Proton Experimental, DXVK) with
  the ED-UP mod v0.22.3 (flat profile, DLSS preset M), output 3072x1728, game
  supersampling raised during the session so that ED-UP reported a 2496x1404
  scene (about 81 %). `dxvk.conf`: `d3d11.cachedDynamicResources = c`.
  In the background: OBS recording with Intel Quick Sync (the iGPU), a
  YouTube video in Chrome, Discord. The game wrapper sets the game's scope to
  `MemorySwapMax=0 MemoryZSwapMax=0`.

## Steps

1. Flew in the game from 22:29, recording with OBS from about 23:10, a
   combat zone from about 23:13 to 23:22, then YouTube in Chrome.
2. Afterwards, read the counters and the kernel log; nothing was traced live.

## Files

| File | Content |
|---|---|
| `kernel-2225-2333.log` | `journalctl -k`, 22:25 to 23:33, NVRM, sched_ext and OOM lines (the OOM task list left out) |
| `vram_pressure-after.txt` | `/proc/driver/nvidia/vram_pressure` after the session (cumulative since boot, 3 days) |
| `edup-vram-cpu-2229-2332.log.xz` | ED-UP's `vram:`, `flat cpu 5s:` and `flat scene candidates` lines, 22:29 to 23:32 |
| `host-state.txt` | kernel, driver build, vm sysctls at capture |

## Result

Measured:

- The game's DXGI budget (as ED-UP logs it from DXVK) fell from about
  7.7 GB at 22:29 to 6.8 GB from 23:09 on, while other clients took more
  video memory (Chrome's GPU process about 900 MB with the video, kwin about
  480 MB). Its spill to system memory (`nonlocal_used_mb`) grew from 1.4 GB
  (22:32) to 4.9 GB (23:31), at 91 to 93 % of the budget throughout.
- The game kept a steady frame rate while it spilled. In the combat zone
  (17 five-second windows with more than 6000 constant buffer writes a
  frame): median 299 frames per 5 s (60 fps cap), worst 278, p95 frame time
  median 21 ms, worst 27 ms. No window collapsed to the 20 fps frame pacing
  breakdown the user reported for such spills before the series.
- `vram_pressure` since boot: `vidmem_alloc_fail` 948 (157 GB requested in
  total, last at the OOM below), `dma_map_fail` 16 (the last at 23:05:49, the
  only `can't update VA space` block of the session), `gem_backoff` 112,
  `gem_sysmem_fallback` 29. There was no message flood and no Xid.
- 23:32:27: global OOM, not in the driver: `chrome invoked oom-killer:
  gfp_mask=0x140dca(GFP_HIGHUSER_MOVABLE|__GFP_ZERO|__GFP_COMP), order=0`,
  `Free swap = 25172036kB`, `Memory cgroup min protection 2620776kB -- low
  protection 21225592kB`, then `Killed process ... (EliteDangerous6) ...
  anon-rss:4252260kB, file-rss:291168kB, shmem-rss:6142896kB ...
  oom_score_adj:200`. In the same second RM logged a failed sysmem
  allocation (`_memdescAllocInternal` at `mem_desc.c:1202`, `system_mem.c:601`).

Inferred, not measured:

- The smooth degradation fits the series' fail-fast paths (sysmem and GEM
  allocations that fail quickly, the GEM back-off, no PAT flood) and DXVK's
  own defragmentation; there is no A/B run against the stock driver.
- The OOM with 25 GB of free swap: the game's ~10 GB were not swappable
  (`MemorySwapMax=0` on its scope), the spilled video memory is pinned system
  memory outside the LRU lists, and the file cache sat at the le9uo
  `clean_min_ratio=15` floor. The kernel picked the game over Chrome's
  renderers (`oom_score_adj` 300) because of its size at `oom_score_adj` 200.

## Open questions

- An A/B run of the same spill on the stock 620.70.06 driver, to separate the
  series' share from DXVK's.
- Whether a soft protection of the game scope (`MemoryLow`) with a small
  swap cap avoids the OOM without the stutter the swap ban was meant to
  prevent.
