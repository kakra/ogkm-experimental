# History

What changed in the series per driver release, and why. Newest first. Patch
numbers refer to `patches/<release>/README.md`.

## 615.78.08

Fork branch `ogkm/615.78.08`, 129 patches on the upstream tag `615.78.08`.

### 2026-10-30: VRR flip events (patches 125, 126)

Two more patches from Tom's set, before our GEM allocation patches, which
are now 127 to 129 (the numbers in the entries below are the old ones).

- 125: with VRR, flip events carried vblank timestamps that were too early
  by the time the raster waited in the front porch (about 11 ms at 60 fps
  on a 240 Hz panel). Flips are now reported at the kick time plus the rest
  of the blanking interval; `nvidia_drm.vrr_flip_timestamps=0` restores the
  old behaviour at runtime.
- 126: moving the cursor only unstalls the VRR head it is on, not every
  VRR head (found by code reading).

Built against 6.18.59, not installed yet.

### 2026-10-30: Tom Englund's set of 2026-10-30 (patches 100 to 124)

25 new patches from `gulafaran/patches`, most of them open upstream pull
requests by other authors (see `patches/615.78.08/README.md`). Left out:
"nvidia-uvm: reserve the least busy channel of a pool" (channel half of
upstream PR [#1375][pr-1375]) together with Tom's revert of it. Tom's
audit found it correct but costly: rotating on ties puts consecutive
pushes on different channels even on an idle pool, so most dependencies
become cross-channel semaphore acquires, block trackers need heap
allocations and `uvm_tracker_add_push()` can fail with `NV_ERR_NO_MEMORY`;
the pull request shows no measured benefit. The TLB batch half of the same
pull request (patch 117) is kept.

Relevant here: static BAR1 updates of noncontiguous allocations coalesced
(upstream PR [#1500][pr-1500], with 16 GiB Resizable BAR), no assert or
reference leak on a failed BAR1 mapping, HDMI DSC max slices at 400 MHz
(the TV), chunked I2C-over-AUX for i2c-dev (ddcutil on DisplayPort), DP
head detaches during detection, and lifetime fixes for the NVKMS revoke
and `nv_drm_device`. The rest is Turing RTD3, Blackwell, hibernation,
Apple Thunderbolt, ACPI AC state, Mellanox, 16K page kernels and
linux-next builds.

Patches 100 to 102 of the entry below are now 125 to 127, after Tom's
patches. Built against 6.18.59.

Installed on 2026-10-30 (all 127 patches, kernel 6.18.59). The boot was
clean: no NVRM messages and no warnings from the nvidia modules. First
impressions, not measured: new desktop windows open faster, without the
lag felt before; games now fill all 12 GB of VRAM (MangoHUD at 100 %),
where frame rate drops or crashes used to start from about 11.5 GB.
Both cover several changes since the 73-patch series, they can't be
attributed to a single patch.

Test on 2026-10-30, Guardians of the Galaxy without workarounds with a
video tab open in Chrome, about 2 h (bpftrace `tools/trace/nv-pat-latency.bt`
from 19:06, kernel log of the boot). The game ran stable.

- Uncached pool (patch 44), compared with finding 3 of
  `analysis/2026-10-26-lock-stalls.md` (`set_pages_array_uc`: 128 calls of
  8 to 16 ms, 17 of 32 to 64 ms; `nv_alloc_system_pages`: 152 of 8 to
  16 ms, 17 of 32 to 64 ms, one of 256 to 512 ms): `set_pages_array_uc`
  822 calls, 40 of 8 to 16 ms, none slower; `nv_alloc_system_pages` 47 of
  8 to 16 ms, none slower. The sessions differ, so this is a comparison
  of the tail, not a measurement of the pool alone. All 3243 write-back
  resets came from kswapd0 or kworkers (pool shrinker and free worker);
  frees took at most 2 to 4 ms, all in kworkers.
- GEM allocation rate limit (patch 125) works: 575 messages and 15014
  suppressed in 88 minutes, at most 5 per 10 s, all "scanout GEM object of
  Chrome_ChildIOT[6039]".
- The back-off (patch 127) does not work in this case: the 15589 failed
  attempts all reached NVKMS (attempts held back by the back-off are not
  logged), up to 26 per second from one thread, while a working back-off
  allows one every 2 s per file. Likely cause, not verified: a
  successful smaller or offscreen allocation between the attempts resets
  the back-off. Fixed in patch 127 on 2026-10-30 (folded in): only a
  success that the back-off would have held back resets it. Built, not
  installed yet.
- 35 known "can't update VA space" blocks (user space driver), five
  explicit 64 KB-page sysmem allocations fell back to 4 KB pages, and one
  20 MB Xwayland GEM allocation fell back to sysmem.

### 2026-10-30: rate limit and back off failed GEM allocations (now patches 125 to 127)

In a 72-minute session of Guardians of the Galaxy without workarounds,
Chrome's GPU process asked for the same 3.2 MB NV12 video scanout buffer on
every frame while VRAM was full: 17336 "Failed to allocate NVKMS memory of
size 3342336 for scanout GEM object" errors in 28 minutes, up to 60 per
second. Frame drops and lag spikes were reported at the same time; that
the failed allocations caused them is not measured yet.

- 125: the three GEM allocation messages are rate limited together (5 per
  10 s) and name the calling process and PID.
- 126: `drm_file::driver_priv` points to a `struct nv_drm_file` instead of
  holding the file id itself.
- 127: per file back-off: after a failed allocation, allocations of that
  file that are not smaller fail with `-ENOMEM` without calling into NVKMS,
  for 100 ms doubling up to 2 s; a success resets it. Failed scanout
  allocations don't hold back offscreen ones.

Built against 6.18.59; installed on 2026-10-30, see above.

### 2026-10-29: the series follows Tom Englund's set (all 99 patches)

Tom's `gulafaran/patches` now carries our own patches too, so the series is
his branch in his order, without the speculation barrier change, the hwmon
device (two patches) and fdinfo usage stats. Our patches moved from the
middle to 71 to 80. Built against 6.18.58.

Installed on 2026-10-29 together with kernel 6.18.59 (two changes at
once). The boot was clean: no NVRM messages, no warnings, KFENCE or
lockdep reports from the nvidia modules, `uncached_pool_max_mb` at its
default of 256, `nvidia_drm.vblank` on. No games tested yet.

- 71: Tom fixed a use-after-free in our patch: it wrote `kick_time` into a
  flip that the flip event handler may already have freed. It is now set
  only under `flip_list_lock` while the flip is still queued. The fix is
  folded into our patch, with a note naming Tom. The 73-patch series of
  2026-10-28 has this bug.
- 72: Tom folded the underscan enum list (patch 66) into our `static const`
  fix.
- 64 to 70: properties for KWin (scaling mode, underscan, MST PATH, content
  type), fewer modesets on max bpc changes, and the full range YUV chroma
  offset fix.
- 81 to 86, 95: use-after-free and locking fixes (MemoryMapper worker,
  semaphore surface fence context, CeUtils event, display ISR callback
  lists against the unlocked low latency path, non-stall event list), and
  a modeset only on the heads that need one.
- 87 to 94, 96 to 99: mostly laptops, hibernation, vfio, confidential
  computing and build fixes for other kernels, each for an upstream issue
  (see `patches/615.78.08/README.md`); upstream PR [#1493][pr-1493].
- 34 and 53 (upstream PRs [#1483][pr-1483] and [#1368][pr-1368]) are now
  Tom's copies: same code, reworded messages.

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
[pr-1375]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1375
[pr-1383]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1383
[pr-1424]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1424
[pr-1430]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1430
[pr-1432]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1432
[pr-1466]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1466
[pr-1483]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1483
[pr-1493]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1493
[pr-1498]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1498
[pr-1500]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1500
