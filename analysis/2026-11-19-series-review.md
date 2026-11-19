# Review of the 620.73.04 series

A read-only code review of the series at 380b6ba1 (145 patches on
`620.73.04`), the fixes that came out of it, and the changes that followed
until the series at cee76fcb (158 patches). Patch numbers below are those of
the series at cee76fcb; the number at 380b6ba1 is given in parentheses where
it differs.

## Method

The series was split by subsystem and every patch was read against the
resulting code and against stock 620.73.04. A finding counts as verified when
the defect follows from the code at the given lines with a concrete sequence
and an attempt to refute it failed. That is not the same as reproduced: none
of the findings below was observed on the test system.

The unmap and destroy paths were reviewed a second time, by a separate
reviewer that was given only the code and the questions (see
[Second review of the unmap and destroy paths](#second-review-of-the-unmap-and-destroy-paths)).

Status of the series at cee76fcb: built against Linux 7.3.5, installed and
booted on the test system (2026-11-19). The fixes have not been tested
against the failures they address; the observations below are from normal
use and one game session.

## Verified findings and fixes

All patches that are fixed here are other authors' work, so every fix is a
separate commit with a `Fixes:` trailer, placed directly after the patch it
fixes. Exception: the fix of the GEM allocation back-off (151) sits after the
pressure counters (150), whose context it uses.

### Partial unmaps below the mapping page size (32, 152; fixes 153 to 157)

Patch 32 (31) splits the DMA mapping list of a VirtualMemory at mapping page
boundaries; the resource server keeps splitting its inter-mappings at the
byte range of the request (`rs_server.c`, `serverInterUnmapMapping()`). After
a partial unmap that does not end on a mapping page boundary, the right-hand
server fragment starts inside the released page, and the DMA mapping that
still holds the rest starts after it. With 64 KiB pages: map
`[0x100000, 0x140000)`, unmap 0x1000 bytes at 0x111000; the server fragment
is at 0x112000, the DMA mapping at 0x120000. A later unmap of the fragment
finds no DMA mapping at 0x112000 and, with patch 152 (145), returns success.

Left behind are the DMA mapping with valid PTEs and a reference on the
backing memory, and, when the VirtualMemory is freed with a non-empty list,
its `devMemoryTableNode` linked in `Device::DevMemoryTable` inside freed
memory. That is the failure class of upstream issue [#1540][issue-1540]
(patch 149, 143 at 380b6ba1), on a path 149 does not cover.

- 153 (veldenb): when the start of an unmap is not registered, unmap the
  overlap with the DMA mapping that starts at the next mapping page
  boundary. A request that matches no such mapping stays a no-op. This
  replaces a fix of the review for the same case.
- 154 (veldenb): the DMA mapping list is keyed by VA only, so after the
  partial unmap another memory can be mapped into the released page, and the
  unmap of the old server fragment found and split that memory's mapping.
  Each DMA mapping now records the resource it was made from, and a mapping
  of another resource counts as unregistered. A second mapping of the same
  resource in the released page still matches; the commit message notes
  this limitation.
- 155: `virtmemDestruct()` unmaps and frees DMA mappings still on the list
  before the common teardown, with one log line per mapping. A safety net;
  every "Freeing leftover DMA mapping" line points to a mismatch elsewhere.
  Kernel and P2P mappings can be left over too (see the second review) and
  get their kernel or BAR1 P2P mapping torn down as in
  `virtmemUnmapFrom()`.
- 156 counts unmaps of unregistered ranges as `dma_unmap_unregistered` in
  `/proc/driver/nvidia/vram_pressure`: the ioctl status of such an unmap
  changed from `NV_ERR_INVALID_OBJECT_HANDLE` to `NV_OK` with 152, so
  `dma_unmap_fail` no longer sees it. Diagnostic, like 150.
- 157 corrects the code comment of 152: the quoted assertion
  `0 == (pMapNode->gpuMask & gpuMask)` does not exist in 620.73.04 (the
  overlap check is "range must not already be mapped" in
  `_gvaspaceMappingInsert()`), and the automatic unmap of back references
  passes a size of 0, for which the resource server drops its inter-mapping
  whether the unmap fails or not.

### Flip written after it was enqueued (3, 115; fix 116)

`nv_drm_atomic_apply_modeset_config()` wrote the submit time, the kick time
and the VRR raster frame of each flip after enqueueing it, without
`flip_list_lock`. `flip_list` adds and completes at its head, and a blocking
commit enqueues without waiting for outstanding flips, so the event of an
earlier flip can dequeue and free the new one before these writes. 116 sets
them through `nv_drm_crtc_set_flip_submit_time()`, which checks under
`flip_list_lock` that the flip is still queued, like the existing kick time
helper of patch 69 (67).

### Flip events sent by the 50 ms fallback (3; fix 4)

A flip whose vblank is not in the history is held until a vblank callback
arrives or a delayed work flushes it after 50 ms with the latest vblank. If
vblank callbacks stop, the display is paced at about 20 fps from stale
timestamps with no trace. 4 counts these events and logs them, at most once
per 10 s. The timestamps are unchanged. See
[Vblank delivery threads at RT priority](#vblank-delivery-threads-at-rt-priority-158)
for the one occurrence so far.

### RM control per LFC repeat under nvkms_lock (111; fix 112)

Each LFC repeat asked RM whether the main layer channel is idle
(`NVC370_CTRL_CMD_GET_CHANNEL_INFO`, routed to GSP, RM API write lock and GPU
lock) with `nvkms_lock` held: the stall pattern that other patches of the
series remove from the flip path. 112 marks a main layer flip pending when
LFC is told about it and clears the mark with the flip's completion notifier
event; RM is only asked while the mark is set. Without completion notifier
events it asks every time, as before.

### FRL failure flag after the fallback to TMDS (124; fix 125)

`hdmi.frlLinkFailures` was only reset by a successful FRL training and by a
probe. After one failed training and a working TMDS mode, every later run of
nvidia-drm's hotplug work set link-status BAD on the working connector
again. 125 resets the counter when a modeset sets up a head without FRL.

### Link training on every probe of a display that is off (130; fix 131)

With restored FRL caps and no head, every EDID read assessed the link again,
and the probe resets the failure counter first, so the limit that drops the
restored caps was never reached: a TV in standby with a readable EDID was
trained against under `nvkms_lock` on every connector probe. 131 bounds these
assessments to three, counted separately and reset when the caps are restored
anew or the sink is hotplugged.

### GEM allocation back-off (119, 120; fix 151)

The back-off refused allocations after a failure regardless of memory freed
in between, compared size and scanout but not the layout, and was visible
only in `gem_backoff`. 151 ends the window when any NVKMS GEM object is freed,
adds the layout to the comparison and logs one line per window with the
number of refused allocations. Single refusals stay unlogged on purpose. The
back-off itself is a deliberate workaround: it keeps the retries from
stalling other clients and from flooding the log, while the allocation still
fails; 119 (115) now says so in its commit message.

### Content type on connectors without the property (65; fix 66)

DRM creates the content type property object for the whole device once one
connector attaches it, and nvidia-drm attaches it to HDMI connectors only. A
connector without it (an HDMI sink behind a passive DP++ adapter) had state
value 0, which was passed as "No Data" instead of keeping the NVKMS default.
66 passes the content type only for connectors that have the property.

## Verified, not changed

- 18/26 (17/25, RG_SEM_SKIPPED): the CPU acknowledges the latched error
  event; why the display skips the RG semaphore release stays open. Kept as a
  workaround for the GSP interrupt storm; its log line and counter already
  exist.
- 32 (31): the failure chain in the commit message does not match the code.
  `gvaspaceUnmap_IMPL()` returns void and only asserts when
  `_gvaspaceMappingRemove()` fails, before the PTEs are unmapped; the
  `vaspaceFree()` the second hunk removes was reached by argument errors and
  a failed TLB invalidate. The snap in the first hunk is the actual fix. To
  be corrected with the author.
- 25 (24): the regkey `DP_ENABLE_SST_EDID_RECOVERY_FIX` is no longer read by
  anything in 620.73.04; the patch has no effect.

## Changes from the rebase of gulafaran/patches onto 620.73.04

Tom Englund rebased gulafaran/patches onto 620.73.04 (at 5ea8c6ab). The
series takes over his versions of two patches it had adapted itself:

- 55, "nvidia-drm: fix color pipeline state handling": his version.
- 129, "nvidia-drm: keep the plane ILUT in sync with the CRTC DEGAMMA_LUT"
  (ElXreno, upstream PR [#1506][pr-1506]): his version, which keeps the one
  case of the PR that 620.73.04 still misses.

veldenb's two unmap patches from the same branch (153, 154) are described
above.

## Second review of the unmap and destroy paths

A second review covered the unmap and destroy paths in `virtual_mem.c` and
`mapping_list.c` of the series with 153 to 157 applied, with the resource
server code as context. The reviewer got the diff, the commit subjects and a
list of questions, no assessment. Three findings, each checked against the
code afterwards:

1. Medium. The leftover free of 155 skipped the unmap of kernel and P2P
   mappings and freed their descriptors, without the kernel mapping or BAR1
   P2P teardown of the normal unmap path. Such mappings can be left over:
   for an unmap with a size of 0 the resource server destroys its
   inter-mapping also when `virtmemUnmapFrom()` fails early, for example
   when the resource reference or the VA space cannot be looked up. Fixed in
   155: these mappings are now torn down as in `virtmemUnmapFrom()`.
2. Low, indirect peer systems only. The normal unmap removes the IOMMU
   mapping of an indirect peer mapping (`memdescUnmapIommu()`); the leftover
   free cannot, because it cannot tell an indirect peer mapping without the
   source memory object, which it does not dereference. 155 notes this in
   its commit message; not changed.
3. Low. `dma_unmap_unregistered` also counted an expected case: the client
   side rounds a partial unmap outwards to the mapping page size, so a
   server fragment next to the request can lie entirely in released pages,
   and its later unmap finds nothing. Example with 4 KiB pages: map
   `[0, 0x3000)`, unmap `[0x800, 0x1800)`; the server keeps `[0, 0x800)` and
   `[0x1800, 0x3000)`, the client keeps `[0x2000, 0x3000)`, and a later
   unmap of `[0, 0x800)` finds no DMA mapping. Fixed in 156: a partial
   unmap counts such fragments per VirtualMemory
   (`orphanedServerFragments`), and that many later no-ops are logged at
   info level without being counted.

No problem was found for double frees or unmaps (the resource server unmaps
inter-mappings and back references before `objDelete()`), for the resource
reference on split descriptors (all three split paths copy it), or for
overflow and size 0 cases.

## Vblank delivery threads at RT priority (158)

Vblank callbacks reach nvidia-drm through the `nvidia-modeset/kthread_q`
thread, which runs the NVKMS timer of the RG semaphore event under the NVKMS
lock. Both that thread and the nvidia-drm vblank worker were normal tasks
with nice 0, competing with all other tasks and scheduled by sched_ext like
any other task when a scheduler such as scx_lavd is loaded. Compositors run
their commit path at RT priority (KWin: `SCHED_RR` 1 for its main and
per-output threads); the thread delivering the events they wait for did not.

Observed: one message of patch 4 in a whole boot of the series at
7ab1b2c6, during a parallel build with all cores busy, after the game
session of the [CP77 evidence](#evidence-unmap-counters-under-video-memory-pressure):

```
[nvidia-drm] [GPU ID 0x00000100] Head 1: sent 1 flip event(s) after 50 ms without a vblank callback
```

158 runs both threads at `sched_set_fifo_low()`, the lowest `SCHED_FIFO`
priority, the same level as the compositor threads; RT tasks are not
handled by sched_ext. Both threads only take locks shared with process
context, so waiting for them does not change. NVKMS polls hardware in some
timer callbacks with short waits, which no longer let normal tasks onto
that CPU meanwhile; the fair and sched_ext deadline servers still leave
them their share of each period.

Measured after booting cee76fcb: `nvidia-modeset/kthread_q` and
`nvidia-drm-vblank-notification` run as `FF` with RT priority 1. Whether
the late callbacks are gone is not shown yet: the message was rare before.

## Evidence: unmap counters under video memory pressure

[evidence/2026-11-19-cp77-unmap-counters](../evidence/2026-11-19-cp77-unmap-counters/):
a 44 minute Cyberpunk 2077 session on the series at 7ab1b2c6, which already
contained 153 to 156 without the changes from the second review.

- 116 failed VA space maps (`_gvaspaceMappingInsert()` returns
  `NV_ERR_INVALID_ARGUMENT` at `gpu_vaspace.c:1804`, then
  `gpu_vaspace.c:4088` and "can't update VA space"), all in the last eight
  minutes of the session, at 49 distinct VAs.
- `dma_unmap_unregistered` 0, no "Freeing leftover DMA mapping", no
  "Duplicate inter mapping".
- `dma_unmap_fail` 6036, `vidmem_alloc_fail` 4088.

So the VAs occupied at the failed maps do not come from the unmap cases 153
to 155 handle; those would have logged or counted. The 6036 failing unmaps
have another cause, not identified yet.

## Open suspicions

Each needs a check on hardware.

- 115 (112): the raster register mapping is only re-queried on a DRM modeset,
  while KAPI also runs NVKMS modesets for HDR metadata, colorspace and bpc
  changes. Check: `drm.debug=0x20` while toggling HDR in the compositor, look
  for vblank counter jumps.
- 80 (78): the fence context destructor treats every failed unregister as an
  in-flight callback; while RM is suspended the closing thread waits 5 s.
  Check: kernel log of suspend cycles for "Semaphore surface fence callbacks
  did not finish".
- 136 (130): static importers without `peer2peer` get `-ENOTSUPP` for
  page-less RM dma-bufs; i915 attaches statically. Check: OBS capture with
  QSV encoding, look for "dma-buf attach failed".

## Upstream issue 1364

Related: upstream issue [#1364][issue-1364].

The known signature ("can't update VA space", stale VA in the user space
driver) is not changed or silenced by any patch. It fails in
`serverInterUnmapInternal()` with `NV_ERR_OBJECT_NOT_FOUND` and never reaches
the function patch 152 changed. The evidence above points the same way: the
map failures under video memory pressure remain with 153 to 156 in place,
while their counters and log lines stay silent.

[issue-1364]: https://github.com/NVIDIA/open-gpu-kernel-modules/issues/1364
[issue-1540]: https://github.com/NVIDIA/open-gpu-kernel-modules/issues/1540
[pr-1506]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1506
