# History

What changed in the series per driver release, and why. Newest first. Patch
numbers refer to `patches/<release>/README.md`.

## 615.78.08

Fork branch `ogkm/615.78.08`, 73 patches on the upstream tag `615.78.08`.

### 2026-10-28: Tom Englund's set of 2026-10-28 (patches 1 to 63)

Built against 6.18.58 and installed on 2026-10-28. In a short session of
Guardians of the Galaxy without `no_upload_hvv` there was no crash. The
known "can't update VA space" blocks (`gpu_vaspace.c:4502`, cause in the
user space driver, `analysis/2026-10-28-vaspace-overlap.md`) appeared four
times in about 20 minutes, as before. One 20 MB scanout GEM allocation
failed in fragmented VRAM and fell back to system memory through patch 65
and the upstream fallback. Not measured yet: `set_pages_array_uc` latency
with the uncached pool (patch 44).

Further games on 2026-10-28/29, same boot (a few hours of uptime after
several reboots for driver changes):

- Star Wars Outlaws and Avatar: Frontiers of Pandora, both VRAM hungry: no
  NVRM messages.
- No Rest for the Wicked, while a Borg backup ran: loading still takes
  long, but all assets are visible as soon as the world appears; before,
  some showed up 30 to 90 s later. No NVRM messages, no OOM.
- 007 First Light, also during the backup, loaded into the world only:
  no problems.

Open: repeat these games after about 40 h of uptime, when memory is
fragmented the way the earlier failures needed (`docs/system.md`).

- 1 to 32: new versions of Tom's patches. They drop the A/B module
  parameters (`lazy_ctxdma_bind`, `unlocked_surface_rm`, `deadline_boost_stats`
  and others) and keep the former defaults. `deadline_boost=0` remains.
- 33 to 53, 56 to 63: new from Tom: dma-buf and PRIME fixes, BAR1
  bookkeeping fixes, fewer RM API lock waits (UNREGISTER_WAITER, DMA map and
  unmap), cursor framebuffer lifetime, per-flip work, upstream PRs
  [#1286][pr-1286] and [#1498][pr-1498], `nvidia_drm.vblank` on by default,
  and the connector and plane properties Broadcast RGB, max bpc, cursor
  SIZE_HINTS and zpos. Left out: the hwmon device, fdinfo usage stats and the
  speculation barrier change.
- 43, 44: free non-cached sysmem from a worker, and keep it uncached in a
  pool, so neither allocation nor free changes PAT for pooled pages (finding 3
  of `analysis/2026-10-26-lock-stalls.md`). They replace our kthread free
  (old patch 44). The pool's failure path frees partly allocated pages as
  cached, which also covers the PAT memtype flood, so our fix for it (old
  patch 33) is dropped.
- 55: own fix for 54: static enum lists, the stack frame of
  `nv_drm_dev_load()` exceeded 1024 bytes.
- 59 replaces our infoframe newline fix (old patch 41).

### 2026-10-27: fixes next to what they fix

Moved "nvidia-drm: don't report flips a vblank early when NVKMS takes long"
from position 41 to 4, directly after the patch it fixes (patch 3, from Tom
Englund's set). Patches 4 to 40 of the earlier order are now 5 to 41. The
numbers in this file follow the current order.

### 2026-10-27: zero the RM heap (patch 45)

- 45: `os_alloc_mem()` returns zeroed memory, so RM behaves the same on a
  kernel without `init_on_alloc`. GPU system memory was already zeroed by the
  driver with the default `NVreg_InitializeSystemMemoryAllocations=1`. Built
  against 6.18.58, not yet run.

### 2026-10-27: repository created

First export of the series as it ran on the test system since 2026-10-26.

### 2026-10-26: lock stalls and explicit page size fallback (patches 42 to 44)

- 42: retry explicit big-page sysmem allocations with smaller pages. Guardians
  of the Galaxy exited after four failed 64 KB-page requests without a VRAM
  budget workaround; with the patch the same requests fell back to 4 KB pages
  8 times without errors.
- 43: `os_alloc_mem()` no longer retries high-order kmalloc before its
  vmalloc fallback.
- 44: non-cached sysmem is freed from a kthread, so the PAT reset no longer
  runs under the GPU lock and the RW API lock. Verified with bpftrace.
- Analyses: `analysis/2026-10-24-sysmem-fragmentation.md`,
  `analysis/2026-10-26-lock-stalls.md`.

### 2026-10-26: VA space partial unmaps, flip events, log cleanup (patches 4, 40, 41)

- 40: upstream PR [#1483][pr-1483]. Built and installed; the `gpu_vaspace.c`
  asserts it targets still appear on this system (`analysis/README.md`).
- 41: drop a duplicate newline from the infoframe log message (introduced in
  615.71.09).
- 4: flips whose vblank started during applyModeSetConfig() were reported one
  vblank early with `nvidia_drm.vblank=1` (finding of the 2026-10-23 review of
  patch 3).

### 2026-10-24: fail fast for big-page sysmem attempts with a fallback (patches 36 to 39)

Sysmem allocations that have a fallback use `__GFP_NORETRY` above order 0, so
they do not stall in direct reclaim and compaction; their expected failures are
no longer logged as errors.

### 2026-10-23: first local series (patches 1 to 3, 5 to 35)

- 1 to 3, 5 to 32: Tom Englund's patch set (`gulafaran/patches`), including the
  upstream PRs [#1383][pr-1383], [#1424][pr-1424], [#1430][pr-1430],
  [#1432][pr-1432] and [#1466][pr-1466], without the change that removes
  speculation barriers (negligible gain, removes hardening). Reviewed in
  `docs/reviews/2026-10-23-patchset-review.md`.
- 33: own fix for the x86/PAT memtype flood after failed sysmem allocations,
  preferred over upstream PR [#1278][pr-1278]
  (`analysis/2026-10-18-pat-memtype-flood.md`).
- 34: upstream PR [#1368][pr-1368], semaphore surface callback leak.
- 35: retry scanout GEM allocations without compression when VRAM is
  fragmented, return `-ENOMEM` instead of `-EINVAL`.

[pr-1278]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1278
[pr-1286]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1286
[pr-1368]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1368
[pr-1383]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1383
[pr-1424]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1424
[pr-1430]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1430
[pr-1432]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1432
[pr-1466]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1466
[pr-1483]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1483
[pr-1498]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1498
