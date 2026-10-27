# x86/PAT memtype flood after failed sysmem allocations

- **Status:** fixed in the series, verified (no flood since)
- **Patch:** "nvidia: don't restore caching type after a failed sysmem
  allocation" (series patch 33); upstream PR [#1278][pr-1278] addresses the
  same bug differently
- **Evidence:** `evidence/2026-10-18-007-sysmem-pat-flood/`

## Symptom

Every crash of 007 First Light on the stock 615.78.08 driver came with
thousands of kernel messages in the same second:

```
x86/PAT: 007FirstLight.e:<pid> freeing invalid memtype [mem 0x00000000-0x00000fff]
```

up to 20224 within 0.1 s, overrunning the kmsg buffer.

## Cause

1. VRAM is nearly full. The user-space driver moves allocations to system
   memory through `RmDeprecatedVidHeapControl` → `sysmemConstruct_IMPL` →
   `nv_alloc_pages` → `nv_alloc_system_pages`.
2. Memory is fragmented, a page of the requested order cannot be allocated,
   and `nv_alloc_system_pages()` jumps to its error path with a
   partially filled `page_table`.
3. The error path calls `nv_free_system_pages()`, which for non-cached
   allocations unconditionally resets the caching type with
   `nv_set_memory_type(at, NV_MEMORY_WRITEBACK)`, although the type is only
   changed to UC/WC after all pages were allocated, so it was never changed.
   `nv_set_memory_type()` walks all `num_pages` entries, and the unfilled ones
   have physical address 0.
4. `set_pages_array_wb()` → `memtype_free()` finds no memtype for page 0 and
   logs the message, once per unfilled slot.

The trace rules out the alternatives: no `remap_pfn_range()` of pfn 0 and no
`pfnmap_track_ctx` released with pfn 0, so neither a mapping of physical page 0
nor a use-after-free.

## Effect

The flood itself is cosmetic for the memory state, but it runs under the RM
locks, costs time in the failing allocation, and hides other kernel messages
(the 04:08 crash lost more than 25000 lines). The crash itself is the failed
allocation (see `2026-10-24-sysmem-fragmentation.md`).

## Fix

Track with a new `memtype_set` flag whether the caching type was changed, and
restore it only in that case. Since the patch was installed (2026-10-23), the
flood has not appeared again, although sysmem allocations have failed several
times (`evidence/2026-10-26-gotg-explicit-pagesize/`).

[pr-1278]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1278
