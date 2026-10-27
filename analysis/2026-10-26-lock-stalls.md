# Lock stalls in the sysmem and display paths

- **Status:** two fixes in the series (patches 43 and 44); patch 44 verified
  by measurement, patch 43 built and running, effect not measured; allocation
  side still open
- **Evidence:** `evidence/2026-10-26-gotg-explicit-pagesize/` (before),
  `evidence/2026-10-27-lock-stall-remeasure/` (after)
- Static analysis of nvidia-drm, nvidia-modeset and the RM sysmem/VA space
  paths on the series at 41 patches, followed by measurements.

## Lock landscape

- **`nvkms_lock`** (a global semaphore) serializes almost everything in
  nvidia-modeset: every KAPI ioctl including ApplyModeSetConfig and
  GET_NEXT_EVENT(S), all NVKMS timers and RM callbacks on the single
  `nvkms_kthread_q`, and with `nvidia_drm.vblank=1` also the RG vblank
  callbacks. A long holder delays all heads.
- The **RM API lock** is an rwsem. A writer blocks new readers. Alloc, free,
  map, unmap and controls take it for writing unless the class sets an RO
  flag.
- The **RM GPU lock** is also needed by the display interrupt bottom half.
  Long GPU lock holders delay vblank and flip events.

## Finding 1 (high): non-cached sysmem free resets PAT under the GPU lock and the RW API lock

- `resource_list.h`: SystemMemory has
  `RS_FLAGS_ACQUIRE_GPUS_LOCK_ON_FREE | RS_FLAGS_ACQUIRE_RO_API_LOCK_ON_ALLOC`.
  Allocation runs under the RO API lock, free under the GPU lock **and** the
  RW API lock.
- `system_mem.c`: on allocation the lock is deliberately taken only after the
  kernel allocation. The free path has no counterpart; `memdescFree()` runs
  completely under the locks.
- `nv_free_system_pages()` calls `nv_set_memory_type(at,
  NV_MEMORY_WRITEBACK)` and then `__free_pages()` per page. The memtype change
  updates the PAT memtype tree for every page and sends TLB flush IPIs. If the
  page array for it cannot be allocated, the code falls back to per-page calls,
  about ten times slower.
- The page pools do not avoid this: write-back is restored before a page goes
  back to the pool.

Measured 2026-10-26 (`nv-pat-latency.bt`, 20 minutes of a game plus Chrome):
17 frees over 2 ms; Chrome 11 of 2.0 to 3.5 ms; the game 5 of 3.4 to 5.7 ms in
one second at exit. A frame at 144 Hz lasts 6.9 ms, so one such free under the
GPU lock can make a head miss a flip. Limitation: the measurement does not
show whether every one of these frees ran under the RM locks (a free with a
remaining mmap happens later at munmap).

**Fix (patch 44):** once the usage count of a non-cached allocation drops to
zero, no user mapping is left and RM no longer references the pages. Hand it
over to a new `nv_free_queue` kthread, which restores write-back, frees the
pages and the `nv_alloc_t`. Synchronous free if the queue is not running.
Cached and contiguous allocations are unchanged. The queue is stopped after the
other queues on unload, so pending frees complete before the pools are
destroyed.

**Result (2026-10-27):** all 5153 write-back resets ran in `nv_free_queue`;
136 frees over 2 ms (maximum 6.3 ms), all in the kthread.

## Finding 2 (high): `os_alloc_mem()` retries high-order kmalloc

- `os-interface.c`: `KMALLOC_LIMIT` 131072, `NV_KMALLOC_NO_OOM` first, the
  vmalloc fallback only afterwards. `NV_GFP_NO_OOM` is `NV_GFP_KERNEL |
  __GFP_RETRY_MAYFAIL`.
- Order 1 to 5 with `__GFP_RETRY_MAYFAIL` means hard reclaim and compaction on
  a fragmented system before the fallback. Callers include memdesc page arrays,
  the `nv_alloc_t` page table and the page array in `nv_set_memory_type()`,
  often under RM locks.

**Fix (patch 43):** `__GFP_NORETRY | __GFP_NOWARN` above `PAGE_SIZE`, the
semantics of `kvmalloc()`. Not measured separately; the remeasurement was on
a fresh boot with little fragmentation.

## Finding 3 (open): the allocation side

After patch 44, the slowest path is the allocation of non-cached sysmem
(2026-10-27): `set_pages_array_uc` 128 calls of 8 to 16 ms and 17 of 32 to
64 ms; `nv_alloc_system_pages` 152 of 8 to 16 ms, 17 of 32 to 64 ms, one of
256 to 512 ms. This runs synchronously in the allocating thread under the RO
API lock and holds off writers. It matches stutter while a game streams in
assets.

Idea, not implemented: a pool of pages that already carry the WC/UC memtype,
so neither allocation nor free changes PAT. Needs a size limit and a
shrinker.

## Finding 4 (medium): lazy ctxdma bind in the flip path

With `lazy_ctxdma_bind`, surface registration binds only the core channel.
The first flip of a new buffer per window does a GSP RPC
(BindSurfaceDescriptor) inside applyModeSetConfig under `nvkms_lock`
(`nvCtxDmaBindOnUse`, called from the evo3 HAL setters). This hits new
swapchains, direct scanout of games and Chrome's scanout buffers. Small per
bind (the comment mentions about 1 ms for all windows), but in the latency
critical path. Idea: with `unlocked_surface_rm`, bind the window channels at
registration, outside the lock. Not implemented.

## Finding 5 (medium, architecture): HDMI FRL link training under `nvkms_lock`

`nvHdmiFrlSetConfig()` tries `NvHdmi_SetFRLConfig` (an RM control to GSP) up
to 6 times, then once with fake link training, during a modeset under
`nvkms_lock`. "HDMI FRL link training failed" appears whenever the TV is
switched on or off; during that time all other heads get no flip events. Not
measured whether this causes visible stutter on the other displays.

## Minor

- `ClearSurfaceUsage` → `nvIdleLayerChannels`: yield loop of up to 2 s under
  the lock, only when a surface is unregistered while still displayed.
- Two frames of `usleep` per modeset; normal.
- Yield loops with 2 s timeouts in `nvkms-dma.c`/`nvkms-evo.c`; only when the
  hardware hangs.
- Deadline boost (`nvidia-drm-fence.c`): the last fence context reference may
  be dropped in a `system_highpri_wq` worker, which then runs RM frees there.

## Checked, no finding

- nvidia-drm lock order `fence_lock → deadline.lock` and `event_lock →
  vblank_time_lock` is consistent. `display_semaphores.lock` is a mutex; no
  sleeping under a spinlock found. Blocking commits wait up to 3 s, but KWin
  uses non-blocking commits.
- Already addressed by Tom Englund's set: rwsem trylock inversion, vmalloc for
  page tables of PMD_SIZE or more, unlocked surface RM calls and backlight,
  batched KAPI events, asynchronous perf boost, RO lock for
  GET_SURFACE_INFO, non-stall interrupt handling, push buffer wrap without
  yield.

Not recommended: the `RmRoApiLock` registry key (experimental, affects all of
RM).
