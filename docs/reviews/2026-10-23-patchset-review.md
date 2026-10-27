# Patch set review (2026-10-23)

> Historical review, written before the own sysmem fixes were added to the
> series. Commit hashes refer to `gulafaran/patches` unless noted. See
> `HISTORY.md` and `analysis/` for what happened to each finding.

Reviewed the 32 commits on `patches` (base 615.78.08) by reading code only;
nothing was built or run. No crash-class bugs found. SHAs below are from
`gulafaran/patches`; the local branch has rebased copies with the same
patch-ids.

## Findings

- `2ccd6ad0` vblank: the switch to CLOCK_MONOTONIC is a real fix. Holding flip
  events can report a frame one vblank early when a commit reaches the
  hardware just after the latch: `__nv_drm_crtc_find_flip_vblank` picks the
  first vblank whose start is at or after submit_time. Fix idea: bound the
  choice by the event arrival time. Only active with `nvidia_drm.vblank=1`
  and not with VRR.
- `806e24ec` deadline boost: correct. A render-node client can pin all 4
  slots with far-future deadlines on prime fences, which silently disables
  boosting. Fix idea: ignore deadlines with more than about 100 ms lead.
- `9f459be6` speculation barriers: negligible performance gain. It removes
  `array_index_nospec` at sites the kernel itself keeps even with
  `mitigations=off`. Optional.
- `1c401dd2`: theoretical use-after-free of pOpenDev/pDevEvo while nvkms_lock
  is dropped, only on GPU hot-unplug or a failed core-channel realloc. The
  comment overstates what the PM lock protects (nvkms_suspend takes the write
  lock only for gpuId 0).
- `a01d1e18`, `0afcf166`: a failed lazy bind or map is only logged (bind) or
  stores GPU VA 0 (map) instead of failing cleanly.
- `679489a6`: the hand-defined registers 0x611848 and HEAD_SEM_DEBUG were only
  verified on AD104, but the code also runs on GA102.
- `vram-fallback.patch`: stale, and wrong. Sysmem ISO surfaces are rejected
  on a dGPU (nvkms-surface.c:493), so the framebuffer gets pSurface=NULL:
  black screen or missing cursor instead of -ENOMEM.

## Memory fragmentation (upstream issue [#1254][issue-1254])

- Covered by the patch set: `aa0f2a4b` (atomic state via kvzalloc; it was an
  order-3 allocation on every commit) and `5507a4f1` (page tables of PMD_SIZE
  or more via vmalloc).
- nvkms_alloc (vmalloc above PAGE_SIZE) and RM os_alloc_mem (vmalloc fallback)
  are fine. No other large kmalloc was found in the commit path.
- Missing, recommended:
  - PR [#1278][pr-1278]: nv_set_memory_type walks unallocated slots after a
    partial sysmem OOM, causing a "x86/PAT: freeing invalid memtype [mem
    0x0-0xfff]" flood under the RM API lock. The maintainer hit this with
    007FirstLight.exe (more than 2658 messages, with kmsg overrun).
  - PR [#1368][pr-1368]: nvKmsKapiRegisterSemaphoreSurfaceCallback leaks cb on
    ALREADY_SIGNALLED (confirmed in nvkms-kapi-sync.c:447). nvidia-drm loops on
    it (nvidia-drm-fence.c:1747). The result is unreclaimable kmalloc-64 slab
    growth.
- Gap with no PR yet: nv_compute_gfp_mask (nv-vm.c) sets __GFP_RETRY_MAYFAIL
  even for order>0 attempts that have a fallback, which forces hard
  reclaim/compaction. Candidate fix: __GFP_NORETRY for order>0 with fallback.
- Harmless noise: the `_kgmmuClientShadowFaultBufferPagesAllocate` big-page
  retry.

## Other upstream PRs (113 open, triaged by title)

- Maybe: [#1004][pr-1004] (shrinker/fence-destroy use-after-free, mostly on
  unload) and [#1316][pr-1316] (async cursor update, about 400 lines).
- Noise: [#1014][pr-1014] (jiffies are 64-bit on x86_64, so the claim is wrong)
  and [#1426][pr-1426] (only matters without ReBAR).
- Already in the patch set: [#1383][pr-1383], [#1398][pr-1398],
  [#1403][pr-1403], [#1424][pr-1424], [#1430][pr-1430], [#1432][pr-1432],
  [#1466][pr-1466].

## dmesg/journal analysis (boot of 2026-10-16, 7 days uptime)

- x86/PAT memtype flood: 37152 lines in the journal, all from
  007FirstLight.exe. Fixed on `ogkm/615.78.08` by the maintainer's commit
  (memtype_set).
- No Xid, no GSP "Stuck interrupt", no flip timeouts, no hung tasks. So
  679489a6/d3e97741 (RG_SEM_SKIPPED) have no observed symptom here.
- gpu_vaspace.c:4502/4586/4594 and intermapRegisterDmaMapping failures (about
  260 asserts, VA around 0xDE..., many bursts): userspace maps a range that is
  already mapped for this GPU, or unmaps partially. RM rejects these cleanly.
  No process name is logged, and there is no kernel-side fix. PR
  [#1354][pr-1354] is about BAR1 mapping_reuse and does not match.
- GEM scanout allocation failures (-EINVAL), 3 every ~52 s around 144119 s:
  Chrome trying RGBA_F16 Scanout BOs ("Failed to create BO with modifiers");
  Chrome falls back on its own. Possible cosmetic fix: return -ENOMEM instead
  of -EINVAL in nv_drm_gem_alloc_nvkms_memory_ioctl.
- At 249709 s: 19 NO_SCANOUT allocations where both VRAM and the sysmem
  fallback failed. The maintainer attributes it to fragmentation. COMPR_ANY in
  sysmem is ruled out: RM silently downgrades it to COMPR_NONE (mem_mgr_gm107.c
  ~436). On GA102, bSysmemPageSizeDefaultAllowLargePages is false, so client
  sysmem uses 4K pages. High-order sysmem attempts come from UVM
  (nv_gpu_ops.c:5071) and the explicit HUGE shadow fault buffer, and both have
  fallbacks.
- Scanout vidmem allocations are PHYSICALLY CONTIGUOUS
  (nvKmsKapiAllocateVideoMemory), and compressed allocations need a
  compression-page-size alignment (mem_mgr_ga100.c). So VRAM fragmentation
  explains the Chrome RGBA_F16 scanout failures. Fix on branch
  `fix-gem-alloc-fragmented-vram` (3433796b), cherry-picked to
  `ogkm/615.78.08`: retry without compression, return -ENOMEM, log the size and
  type of the failed allocation.
- "HDMI FRL link training failed" (8x): happens when the monitors are switched
  on or off (confirmed by the maintainer). The sink is not ready, and the driver falls back
  to fake link training. Harmless.
- HDMI-A-3 is a Samsung TV (2020) with FRL up to 10G x4, DSC (FRL 6G x4), 4K120
  VRR. So 54b0f06f (FRL DSC hblankMin) can matter for it, which corrects the
  earlier "no effect" assessment. HDMI-A-4 (LG SDQHD) is TMDS only.

## Samsung TV VRR flicker below 60 Hz

- The maintainer now uses a fiber HDMI cable, and 4K120 is detected reliably. The
  picture flickers when VRR drops below 60 Hz (EDID VRRmin 48).
- This is most likely the panel itself (low-refresh gamma flicker) rather
  than GSP firmware. Mitigation: raise the VRR minimum so the display engine
  repeats frames earlier (the LFC-like timeout in nvAdjustHwModeTimingsForVrrEvo).
- NVKMS already supports NvKmsSetModeRequest.head.vrrOverrideMinRefreshRate,
  limited to the EDID minimum +-10 Hz (NVKMS_VRR_MIN_REFRESH_RATE_MAX_VARIANCE),
  so at most 58 Hz here. KAPI/nvidia-drm never set it. Options: an EDID
  override with VRRmin 60 (drm.edid_firmware; d5a7ef03 fixes accumulating
  override modes), or a patch that exposes the override via nvidia-drm.

[issue-1254]: https://github.com/NVIDIA/open-gpu-kernel-modules/issues/1254
[pr-1004]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1004
[pr-1014]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1014
[pr-1278]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1278
[pr-1316]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1316
[pr-1354]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1354
[pr-1368]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1368
[pr-1383]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1383
[pr-1398]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1398
[pr-1403]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1403
[pr-1424]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1424
[pr-1426]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1426
[pr-1430]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1430
[pr-1432]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1432
[pr-1466]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1466
