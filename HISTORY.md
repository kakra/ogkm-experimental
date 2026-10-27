# History

What changed in the series per driver release, and why. Newest first. Patch
numbers refer to `patches/<release>/README.md`.

## 615.78.08

Fork branch `ogkm/615.78.08`, 45 patches on the upstream tag `615.78.08`.

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
[pr-1368]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1368
[pr-1383]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1383
[pr-1424]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1424
[pr-1430]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1430
[pr-1432]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1432
[pr-1466]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1466
[pr-1483]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1483
