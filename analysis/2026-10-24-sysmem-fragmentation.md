# Sysmem allocation failures under memory fragmentation

- **Status:** partly fixed in the series; the fallback for explicit page
  sizes is verified in one session, the fail-fast changes are built and
  running but their latency effect is not measured
- **Patches:** series patches 36 to 39 (fail-fast), 42 (explicit page size
  fallback), 43 (`os_alloc_mem()`); related: 7 and 19 from Tom Englund's set
- **Evidence:** `evidence/2026-10-18-007-sysmem-pat-flood/`,
  `evidence/2026-10-26-gotg-explicit-pagesize/`,
  `evidence/2026-10-27-lock-stall-remeasure/`

## Summary

On a desktop with a few days of uptime, the page allocator often has no free
block of order 8 or higher, even with gigabytes of free memory. The NVIDIA
driver asks for such blocks in two situations, with very different
consequences:

- **Class A, harmless but slow:** a first attempt with big pages that the
  caller retries with small pages (UVM, the client shadow fault buffer,
  `sysmemConstruct()` with the default page size). It fails, but only after
  direct reclaim and compaction, and logs errors that look fatal.
- **Class B, fatal:** an allocation from the user-space driver with an
  explicit big page size. `sysmemConstruct()` did not retry these, the
  allocation failed and the game exited or crashed in `vkAllocateMemory`.

The user-space driver only falls back to sysmem when VRAM is full, so VRAM
pressure and RAM fragmentation have to coincide. Games that fill the 12 GiB of
VRAM at 4K (Guardians of the Galaxy, 007 First Light) hit it reliably after
about a day of uptime; with `dxgi.maxDeviceMemory` limiting their VRAM budget
they ran longer but still failed eventually.

## Class A: big-page attempts with a fallback

Typical kernel log, at every start of a UVM client (game start, every Steam
Fossilize process):

```
NVRM: ... Out of memory [NV_ERR_NO_MEMORY] ... _memdescAllocInternal(pMemDesc) @ mem_desc.c:1348
NVRM: ... Out of memory [NV_ERR_NO_MEMORY] ... rmStatus @ system_mem.c:448
NVRM: nvAssertOkFailedNoLog: ... pRmApi->Alloc(...) @ nv_gpu_ops.c:5071
```

- `nv_gpu_ops.c:5071` is `nvGpuOpsAllocPhysical()`, called from
  `uvm_rm_mem_alloc()` (`kernel-open/nvidia-uvm/uvm_rm_mem.c`). For sysmem of
  2 MB or more UVM asks for 2 MB pages (order 9) and retries with the default
  page size on `NV_ERR_NO_MEMORY`. The retry message is a `UVM_ERR_PRINT`,
  hidden unless `uvm_debug_prints=1`.
- `_kgmmuClientShadowFaultBufferPagesAllocate()` asks for huge pages and
  retries with 4 KB pages (comment: Bug 5042223).
- The cost: `nv_compute_gfp_mask()` sets `__GFP_RETRY_MAYFAIL` for every
  order. For costly orders this does not protect against the OOM killer (it is
  never invoked there), it only makes the allocator retry reclaim and
  compaction up to `MAX_COMPACT_RETRIES` times before giving up. The caller
  stalls, often under RM locks.

Fix in the series: `MEMDESC_FLAGS_ALLOC_FAIL_FAST` → `nv_alloc_t` →
`__GFP_NORETRY` instead of `__GFP_RETRY_MAYFAIL` for order > 0. Set by
`sysmemConstruct()`'s own page size walk, the shadow fault buffer, and UVM's
first attempt (new `UvmGpuAllocInfo.bFailFast` → `NVOS32_ATTR2_FAIL_FAST`,
bit 28 of ATTR2, unused in this release). Order-0 allocations keep
`__GFP_RETRY_MAYFAIL`. Failures of fail-fast attempts are logged at
LEVEL_INFO, which release builds do not print, so the three lines above no
longer appear for an expected fallback.

The same pattern exists in `os_alloc_mem()`: `kmalloc()` with
`__GFP_RETRY_MAYFAIL` for 8 to 128 KB (order 1 to 5) before the vmalloc
fallback, for page arrays and other RM structures, often under RM locks.
Patch 43 uses `__GFP_NORETRY | __GFP_NOWARN` above `PAGE_SIZE`, like
`kvmalloc()`.

## Class B: explicit page sizes from user space

Recognizable by `system_mem.c` **without** an `nv_gpu_ops.c` line; stack
`rm_ioctl` → `RmDeprecatedVidHeapControl` → `sysmemConstruct_IMPL`.

- `sysmemConstruct()` walks down the page sizes only for
  `NVOS32_ATTR_PAGE_SIZE_DEFAULT`. On GA102,
  `bSysmemPageSizeDefaultAllowLargePages` is false, so default requests use
  4 KB pages anyway, and only explicit `PAGE_SIZE_BIG`/`_HUGE` requests use
  large pages. The CPU order follows the GPU page size
  (`memdescGetAdjustedPageSize`).
- 2026-10-11 (Guardians of the Galaxy, stock driver): the game crashed with a
  segfault in `libnvidia-glcore.so` inside `vkAllocateMemory`, 0.4 s after
  vkd3d-proton logged "Memory allocation failed, falling back to system
  memory" and the kernel logged `system_mem.c:448`, with about 19 GB of RAM
  free. The driver crashed instead of returning
  `VK_ERROR_OUT_OF_DEVICE_MEMORY`.
- 2026-10-26 (same game, series at 41 patches, no VRAM workaround): four
  failures at `system_mem.c:460` within 60 ms, the game exited one second
  later. No free order-9 block in any zone, MemAvailable 13.5 GB.

Fix in the series (patch 42): `sysmemConstruct()` also walks down the page
sizes for explicit BIG/HUGE requests that are not physically contiguous. This
is safe for the GPU mappings: `dmaAllocMapping_GM107()` maps memory at its
physical page size when a larger mapping page size is requested for
non-contiguous memory, and the client gets the resulting page size back in
`attr`/`attr2`, as on the default path. The attempts before the last one are
fail-fast. Each fallback is logged at LEVEL_ERROR:

```
NVRM: GPU0 sysmemConstruct_IMPL: Sysmem alloc of 0x1000000 bytes with page size 0x10000 failed, retrying with page size 0x1000.
```

Result 2026-10-27 (same game, same missing workaround): 8 such fallbacks, all
for 16 MB with 64 KB pages, all succeeded with 4 KB pages; no failure, no Xid,
the game kept running. So the failing class B requests use 64 KB pages
(order 4), not 2 MB.

## Why order 4 and 9 blocks are missing

- After about a day: Normal zone order 6 and up practically empty; manual
  compaction reaches order 8 but never order 9.
- `pagetypeinfo`: 4130 Unmovable vs. 11017 Movable pageblocks after 20 h,
  about 2.8 GB of free memory inside Unmovable pageblocks, which compaction
  does not touch. 22 % Unmovable pageblocks already 10 minutes after boot.
- `compact_fail` is 80 to 93 % of `compact_stall` in every capture.
- Sysmem pages of the driver are `GFP_KERNEL`, unmovable. Games allocate
  gigabytes of 4 KB sysmem this way, and every 4 KB page can steal and mix a
  Movable pageblock. Whether the driver is the main source of Unmovable
  pageblocks is not measured (`page_owner=on` would show it).

## Ideas not implemented

| Idea | Effect | Risk |
|---|---|---|
| Reserved floor in the driver's per-order page pools (`nv_mem_pool_*`), filled at module load while memory is unfragmented | high for class B | low, fixed RAM cost |
| Allocate 4 KB sysmem opportunistically in order-4 chunks to concentrate unmovable pages in fewer pageblocks | medium, long term | large change in `nv_alloc_system_pages()` |
| Compact memory before a game starts (gamemode hook) | limited, compaction stops at order 8 | none |
| `compaction_proactiveness` 60 to 80 | low | CPU |
| Measure who does direct compaction (`compaction:mm_compaction_begin`) and who creates Unmovable pageblocks | prerequisite for the above | none |

`movablecore=` would shrink the space for the driver's unmovable allocations,
and CMA does not help (the driver uses `alloc_pages()`).
