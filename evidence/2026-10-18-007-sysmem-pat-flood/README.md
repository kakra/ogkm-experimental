# x86/PAT memtype flood and sysmem failures in 007 First Light (2026-10-18)

## Setup

- System: see `docs/system.md`
- Driver: 615.78.08, **stock** open modules (before the series)
- Kernel: 6.18.57, uptime about 2.8 days at the crash
- Workload: 007 First Light (Steam app 3768760) via Proton/vkd3d-proton,
  3840x2160, `DXVK_CONFIG="dxgi.maxDeviceMemory = 7000"`
- Times are local (CEST, UTC+2).

## Steps

1. Play until the game crashes. In the failing sessions the desktop had been
   up for days (fragmented memory, see the buddyinfo below).
2. `sudo tools/trace/pat-pfn0-trace.sh` while playing, Ctrl+C after the crash.
3. Second session: `sudo tools/trace/nv-sysmem-fail-trace.sh` while playing.

## Files

| File | Content |
|---|---|
| `pat-pfn0-trace-20261018-221632.txt.xz` | kprobe trace of the PAT flood: `memtype_free` with `start=0`, `remap_pfn_range` with pfn 0, `pfnmap_track_ctx` release with pfn 0, with stack traces (17 MB unpacked) |
| `nv-sysmem-fail-20261018-233818.txt.xz` | kretprobe trace of `nv_alloc_system_pages()` with order, page count, caching type and a buddyinfo snapshot (2.8 MB unpacked) |

## Result

### PAT flood

Three crashes (2026-10-17 18:27:04, 2026-10-18 04:08:28 and 22:20:45): all game
processes exit with code -1, no Xid, no kernel oops. Each time the kernel
logged a flood of

```
x86/PAT: 007FirstLight.e:<pid> freeing invalid memtype [mem 0x00000000-0x00000fff]
```

in the same second or one second before (6439, 6634 and 20224 lines; the 04:08
flood overran the kmsg buffer). One flood came mid-game without a crash.

The trace of the 22:20 crash has 20224 `memtype_free(start=0, end=4096)`
events within 0.1 s (uptime 243681.564 to 243681.667 s), all from
`007FirstLight.exe`, all with the same stack:

```
memtype_free <- set_pages_array_wb <- nv_free_system_pages <- nv_alloc_system_pages
  <- nv_alloc_pages <- sysmemConstruct_IMPL <- RmDeprecatedVidHeapControl <- rm_ioctl
```

There are no `pfn0_remap` and no `pfn0_release` events: the driver never maps
physical page 0, and nothing is corrupted. The error path of a partially
failed sysmem allocation resets the caching type of every page slot, including
the slots that were never filled (pfn 0).

### Sysmem allocations

The second run (23:38 to about 01:44, uptime 248497 to 255876 s) ran with
`vm.watermark_scale_factor=200` and THP `shmem_enabled=advise`. **No
allocation failed** in it (0 `nvsys_fail:` events). The 3375 stack traces in
the file are not failures: a tracefs trigger ignores the event filter, so
`stacktrace` fired on every return of `nv_alloc_system_pages()` (fixed in the
script afterwards). They show who allocates sysmem through
`RmDeprecatedVidHeapControl`: 007FirstLight.exe 3019, chrome 291, Discord 25,
kwin_wayland 19, plasmashell 12, vkd3d/D3D12 threads.

Buddyinfo at the start, zone Normal:

```
9480 35447 28124 12593 4456 225 53 15 0 0 0
```

No free block of order 8 or higher.

### Memory state at the 22:20 crash

Uptime about 243000 s, 31 GB RAM, 10 GB swap used. `compact_success` 12547 vs.
`compact_stall` 407595, `pgmigrate_fail` about 11 % of migrations. Zone Normal
had 4 free 2 MB blocks and no 4 MB block. `echo 1 > /proc/sys/vm/compact_memory`
changed buddyinfo almost not at all. VRAM was nearly full (11.9 of 12.3 GB) even
with `maxDeviceMemory = 7000`, which only lowers the reported budget.

## Open questions

- The order of the allocation that fails right before the crash; the second
  run had no failure. See `2026-10-26-gotg-explicit-pagesize` for the next
  occurrence.
- Interpretation and fixes: `analysis/2026-10-18-pat-memtype-flood.md`.
