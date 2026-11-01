# "can't update VA space" in Guardians of the Galaxy only with VRAM full (2026-11-01)

Follow-up to `evidence/2026-10-28-gotg-vaspace-overlap/`, with a second
tracer that also records allocs, frees and dups. Two sessions on the same
boot: one without VRAM pressure (no errors) and one that ran into the VRAM
limit (errors reproduced).

## Setup

- System: see `docs/system.md`
- Driver: 615.78.08, series `ogkm/615.78.08` at `30982d9d` (built and loaded
  on this boot)
- Kernel: 6.18.59, boot at 08:00; uptime at capture: about 7 h 25 min (run 1)
  and 11 h 31 min to 12 h 58 min (run 2)
- Workload: Marvel's Guardians of the Galaxy (Steam app 1088850), D3D12 via
  vkd3d-proton, Proton Experimental `experimental-11.0-20261027b`
  (vkd3d-proton `cae2e003b`), without `dxgi.maxDeviceMemory` and
  without `VKD3D_CONFIG=no_upload_hvv`. Chrome, Discord and the Plasma
  desktop ran in the background. Graphics settings were not recorded.

## Steps

1. Tracer: `tools/trace/nv-va-trace.bt` and `tools/trace/nv_va_analyze.py`
   by "Bober" from the [NVIDIA forum thread][forum-dx12] (MIT). It hooks the
   ioctl syscall tracepoints and logs the parameter blocks of `RM_ALLOC`,
   `RM_ALLOC_MEMORY`, `RM_FREE`, `RM_DUP_OBJECT`, `RM_MAP_MEMORY_DMA` and
   `RM_UNMAP_MEMORY_DMA` at syscall entry and exit. Both runs used the
   version with the bpftrace 0.26 warning fix.
2. Start the trace before the game:
   `sudo bpftrace tools/trace/nv-va-trace.bt > trace.log`, stop with Ctrl+C
   after the game has exited.
3. `python3 -I tools/trace/nv_va_analyze.py trace.log --json analyze.json`,
   and `--va <address>` for the history of one VA.

## Files

| File | Content |
|---|---|
| `trace-no-pressure.log.xz` | Run 1, 15:25 to 15:55 (29 min of play). Raw tracer output, all processes. Times are `CLOCK_MONOTONIC` in ns, the same clock as the dmesg timestamps. |
| `analyze-no-pressure.{txt,json}` | Analyzer output of run 1 |
| `trace-vram-full.log.xz` | Run 2, 19:31 to 20:58 (87 min of play), same format |
| `analyze-vram-full.{txt,json}.xz` | Analyzer output of run 2 |
| `dmesg-excerpt.log` | All NVRM and nvidia-drm lines of run 2 (run 1 had none) |

## Result

Measured, run 1: 21244 RM calls, all with status 0. 564 maps of GotG with
flags `0x208` (the temporary object of the move sequence from 2026-10-28),
no failed unmap, no failed map. No NVRM or nvidia-drm line in the kernel log
since boot, so VRAM never ran full.

Measured, run 2: 34928 RM calls; 662 failed unmaps (status `0x57`
`NV_ERR_OBJECT_NOT_FOUND`) and 11 failed maps (status `0x1f`
`NV_ERR_INVALID_ARGUMENT`), all from GotG threads. The 11 failed maps match
the 11 "can't update VA space" blocks in dmesg to the millisecond.

GotG threads, per 5 minutes of play (run 2):

| Minutes | Maps | Unmaps | Frees | Flags 0x208 | Failed maps | Failed unmaps |
|---|---|---|---|---|---|---|
| 0-5 | 1999 | 1238 | 2756 | 517 | 0 | 0 |
| 5-55 | 38-224 | 14-196 | 12-266 | 0-55 | 0 | 0 |
| 55-60 | 473 | 283 | 437 | 195 | 0 | 47 |
| 60-75 | 88-301 | 100-296 | 99-456 | 4-53 | 0 | 18-67 |
| 75-80 | 1064 | 1514 | 3052 | 600 | 4 | 461 |
| 80-85 | 299 | 357 | 601 | 88 | 6 | 49 |
| 85-87 | 33 | 27 | 25 | 3 | 1 | 1 |

Timeline (dmesg time in seconds since boot):

```
44863.918 NVRM: GPU0 sysmemConstruct_IMPL: Sysmem alloc of 0x1000000 bytes with page size 0x10000 failed, retrying with page size 0x1000.
44865.070 first failed unmap of the session (gotg.exe, 0x57)
44980.115 [nvidia-drm] Failed to allocate NVKMS video memory for GEM object of Xwayland[3303], trying to fall back to sysmem
46208.765 first "dmaAllocMapping_GM107: can't update VA space for mapping @vaddr=0x2e69a0000"
46635.762 last of 11 blocks, @vaddr=0xb9c00000
```

The first unmap failure comes 1.2 s after RM starts to place allocations in
system memory, i.e. when VRAM is full. Before that, 56 minutes of play had no
failure at all.

The first failed map is the sequence from 2026-10-28 (handles shortened,
`A` = virtual object `0xcaf00aff`, `T` = temporary `0xcaf00c8a`, `M` =
memory `0x151`):

```
46197.509 DeferedReleaseT  map    T <- M  flags 0x208         VA 0xe64b0000   ok
46197.518 DeferedReleaseT  unmap  A                           VA 0x2e69a0000  ok
46197.518 DeferedReleaseT  map    A <- M  flags 0x0           VA 0x2e69a0000  ok
46208.765 ZRenderManager   unmap  A                           VA 0xe64b0000   0x57
46208.765 ZRenderManager   map    A <- M  flags 0x40000208                    0x1f
```

`A` is unmapped at the VA that `T` had during the move, the unmap misses,
and the next map into `A` collides with the still existing mapping. The map
comes 11.2 s after the move, so it is stale state, not a race between the two
threads. Many of the other failed unmaps go to a temporary handle that the
same thread freed (`RM_FREE`) just before.

Reported by the user, not measured: the game ran smoothly until the first
NVRM message, then frame rates became unstable with heavy stutter. After the
VA space errors it settled again, but less smoothly than before and with
higher GPU load (above 95 % instead of about 75 %, already from the first
NVRM message on).

Not usable: the user stacks of the failed calls only resolve the `ioctl`
frame in libc; the NVIDIA user space driver has no frame pointers.

## Open questions

- Is the higher GPU load the cost of allocations that now live in system
  memory (PCIe), or of the move storm itself? The trace does not show
  residency.
- Run 1 had 564 moves without a single stray unmap; run 2 had them only once
  VRAM was full. Does the driver use a different move path under eviction,
  or does the stray unmap only show when the temporary VA is reused?
- Does the same happen with the proprietary kernel modules and other D3D12
  games?

[forum-dx12]: https://forums.developer.nvidia.com/t/native-directx-12-on-linux/386938/38
