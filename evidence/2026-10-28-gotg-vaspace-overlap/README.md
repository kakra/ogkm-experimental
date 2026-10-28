# "can't update VA space" in Guardians of the Galaxy: RM map/unmap ioctls (2026-10-28)

## Setup

- System: see `docs/system.md`
- Driver: 615.78.08, series `ogkm/615.78.08` (incl. upstream PR [#1483][pr-1483])
- Kernel: 6.18.58, uptime at capture: about 2 h 15 min
- Workload: Marvel's Guardians of the Galaxy (Steam app 1088850), D3D12 via
  vkd3d-proton, without `dxgi.maxDeviceMemory` and without
  `VKD3D_CONFIG=no_upload_hvv`. Chrome, Discord and the Plasma desktop ran in
  the background. Short session.

## Steps

1. Start the trace, then the game:
   `sudo bpftrace tools/trace/nv-vaspace-ioctl.bt | tee vaspace.log | grep --line-buffered FAIL`
2. Play until two "can't update VA space" blocks show up in dmesg, stop with
   Ctrl+C.
3. `tools/trace/nv-vaspace-analyze.py vaspace.log`

## Files

| File | Content |
|---|---|
| `vaspace.log.xz` | Output of `nv-vaspace-ioctl.bt`: every `NV_ESC_RM_MAP_MEMORY_DMA` / `NV_ESC_RM_UNMAP_MEMORY_DMA` ioctl of all processes (5850 maps, 4878 unmaps). The "Addrspace mismatch" warnings at the top are from bpftrace 0.26 and did not affect the values. Times are `CLOCK_MONOTONIC` in ms, about 0.1 s ahead of the dmesg timestamps. |
| `dmesg-excerpt.log` | The two RM error blocks of the session |

## Result

Measured: 2 failed maps (status `0x1f` `NV_ERR_INVALID_ARGUMENT`), both from
gotg.exe, matching the two dmesg blocks (8117.37 s at `0x27bb60000`, 8120.25 s
at `0x28720000`). 22 failed unmaps (status `0x57` `NV_ERR_OBJECT_NOT_FOUND`),
all from gotg.exe. No other process has a failure.

All failures are in one recurring sequence of the user space driver on the
game threads `DeferedReleaseThread` and `ZRenderManager`. It moves a physical
allocation `M` into a virtual object `A` through a temporary virtual object
`T` (handles shortened, `hDma` = virtual object, `hMemory` = backing):

```
map    T <- M  flags 0x208          T at its own VA
unmap  A at VA(A)
unmap  T at VA(T)
map    A <- M  flags 0x0            A at VA(A)
unmap  T at <a VA that is not T's>  -> 0x57
```

The final unmap of `T` is redundant (T is already unmapped) and always passes
a VA that does not belong to `T`; in 18 of 22 cases it is the VA of another
live mapping of the process. RM finds no mapping of `T` there and changes
nothing.

Both failed maps follow a move of the same `A` and start with an unmap of `A`
at the VA that `T` had in that move:

```
8117.459 DeferedReleaseT  map   T=0xcaf0096a <- 0x153          VA 0x287b60000  ok
8117.463 DeferedReleaseT  unmap A=0xcaf0095f                    VA 0x27bb60000  ok
8117.463 DeferedReleaseT  unmap T=0xcaf0096a                    VA 0x287b60000  ok
8117.464 DeferedReleaseT  map   A=0xcaf0095f <- 0x153 flags 0x0 VA 0x27bb60000  ok
8117.464 DeferedReleaseT  unmap T=0xcaf0096a                    VA 0x27bb60000  0x57
8117.465 ZRenderManager   unmap A=0xcaf0095f                    VA 0x287b60000  0x57
8117.465 ZRenderManager   map   A=0xcaf0095f <- 0x153 flags 0x40000208          0x1f
```

```
8117.596 DeferedReleaseT  map   T=0xcaf0096c <- 0x1f4          VA 0x1c2000000  ok
8117.597 DeferedReleaseT  unmap A=0xcaf00491                    VA 0x28720000   ok
8117.597 DeferedReleaseT  unmap T=0xcaf0096c                    VA 0x1c2000000  ok
8117.597 DeferedReleaseT  map   A=0xcaf00491 <- 0x1f4 flags 0x0 VA 0x28720000   ok
8117.597 DeferedReleaseT  unmap T=0xcaf0096c                    VA 0x283b60000  0x57
8120.344 ZRenderManager   unmap A=0xcaf00491                    VA 0x1c2000000  0x57
8120.344 ZRenderManager   map   A=0xcaf00491 <- 0x1f4 flags 0x40000208          0x1f
```

The unmap of `A` misses, so `A` keeps its mapping of `M` from the move. The
next map into `A` (no fixed offset, so RM maps at the start of `A`) finds that
mapping in the VA space mapping tree and fails at `gpu_vaspace.c:4502`. The
second case comes 2.7 s after the move, so it is not a race between the two
threads.

Inferred, not verified:

- The driver records `T`'s VA for `A` after a move (and some other VA for
  `T`), and uses it on the next operation on `A`.
- The new map asks for the same memory with `ENABLE_FORCE_COMPRESSED_MAP`
  (bit 30) and `PAGE_KIND_VIRTUAL` (bit 3). After the failure `A` stays
  mapped to the right memory, but with the kind of the `flags 0x0` map.

## Open questions

- Is the wrong kind visible (corruption) or only a missed compression
  change? The session had no crash; artifacts were not checked.
- Do the moves only happen under VRAM pressure (compaction or eviction)? The
  earlier sessions with these errors had VRAM full; this one was not
  checked.
- Does the same sequence happen in other D3D12 games, and with the
  proprietary kernel modules?

[pr-1483]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1483
