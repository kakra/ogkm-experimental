# How the driver works (the parts that matter here)

Notes from reading the 615.78.08 source while chasing the problems in
`analysis/`. File and line references are for 615.78.08 and drift between
releases; search for the function names.

## Components

| Part | Where | Notes |
|---|---|---|
| `nvidia.ko` glue | `kernel-open/nvidia/` | Linux interface: page allocation (`nv-vm.c`), `os_alloc_mem()` (`os-interface.c`), mmap, PAT |
| Resource Manager (RM) | `src/nvidia/` | Linked into `nvidia.ko`. Memory descriptors, sysmem/vidmem objects, VA spaces, locks, GSP RPCs |
| `nvidia-modeset.ko` glue + NVKMS | `kernel-open/nvidia-modeset/`, `src/nvidia-modeset/` | Display: heads, surfaces, flips, HDMI/DP link training |
| `nvidia-drm.ko` | `kernel-open/nvidia-drm/` | DRM/KMS interface for the compositor, GEM objects, fences |
| `nvidia-uvm.ko` | `kernel-open/nvidia-uvm/` | Unified memory (CUDA), but also started by every Vulkan process |
| GSP firmware | binary | Most GPU management runs on the GSP; RM sends RPCs to it |
| User-space driver | binary (`libnvidia-glcore`, Vulkan ICD) | Decides memory placement, talks to RM through ioctls |

**Important for patching:** the `kernel-open/` directory shipped in the
`NVIDIA-Linux-*.run` package (and in DKMS packages built from it) contains RM
and NVKMS only as prebuilt objects (`nvidia/nv-kernel.o_binary`,
`nvidia-modeset/nv-modeset-kernel.o_binary`). Patches that touch `src/` can
only be built from the full source: the git repository or the
`NVIDIA-kernel-module-source-<release>.tar.xz` tarball. In the 615.78.08
series, 29 of 45 patches touch `src/`.

## Where VRAM goes when it is full

- There is no TTM/GEM eviction in the kernel modules for graphics memory.
  The user-space driver decides placement and allocates system memory
  ("sysmem") for GPU resources itself when VRAM runs out. Vulkan exposes this
  as `VK_EXT_pageable_device_local_memory`.
- Such allocations go `rm_ioctl` → `RmDeprecatedVidHeapControl` →
  `sysmemConstruct_IMPL` → `nv_alloc_pages` → `nv_alloc_system_pages`. The
  same path is used by every graphics client: games, browsers, the
  compositor, the shell.
- Video memory allocations are charged to the dmem cgroup of the calling
  task; see `analysis/2026-10-23-dmemcg.md`.

## Sysmem allocation

- The GPU page size of a sysmem allocation becomes the CPU allocation order:
  4 KB → order 0, 64 KB → order 4, 2 MB → order 9
  (`memdescGetAdjustedPageSize`).
- `sysmemConstruct()` falls back to smaller page sizes only for
  `NVOS32_ATTR_PAGE_SIZE_DEFAULT` in stock drivers. Explicit BIG/HUGE requests
  fail as soon as no block of that order is free (patch 42 of the 615.78.08
  series changes this). On GA102, `bSysmemPageSizeDefaultAllowLargePages` is
  false, so only explicit requests use large pages.
- `nv_compute_gfp_mask()` sets `__GFP_RETRY_MAYFAIL` for every order. For
  order > 3 this does not avoid the OOM killer (it is never invoked there), it
  makes the page allocator retry reclaim and compaction before failing.
- Driver page pools per order (`nv_mem_pool_*` in `nv-vm.c`,
  `NVreg_EnableSystemMemoryPools`, default 0x211 = 4K, 64K and 2M) fill only
  when pages are freed, and a shrinker empties them under memory pressure, so
  they are empty exactly when memory is fragmented.
- Sysmem pages are `GFP_KERNEL`: unmovable for the page allocator.
- `NVreg_InitializeSystemMemoryAllocations` (default 1) adds `__GFP_ZERO` to
  sysmem allocations; pool pages are cleared before reuse. With 0, only the
  kernel's `init_on_alloc=1` zeroes them.
- The RM heap (`portMemAllocNonPaged()` → `os_alloc_mem()`, kmalloc or
  vmalloc) is not zeroed by stock drivers; with `init_on_alloc=0` it holds old
  data. Whether any RM code depends on zeroed heap memory is not known; the
  series zeroes it (patch 45) to be safe.

Fallbacks that already exist: UVM asks for 2 MB pages for its pushbuffers
and channels and retries with 4 KB (`uvm_rm_mem_alloc()`); the client shadow
fault buffer asks for huge pages and retries with 4 KB
(`_kgmmuClientShadowFaultBufferPagesAllocate`). Each start of a UVM client
(every game, every Steam Fossilize process) therefore logs three
`NV_ERR_NO_MEMORY` lines on a fragmented system, although nothing failed.

## Caching types and PAT

- Write-combined and uncached sysmem changes the PAT memtype of every page:
  `set_pages_array_uc/wc` on allocation (with a cache flush),
  `set_pages_array_wb` on free. Each call updates the memtype tree per page and
  flushes TLBs; for large allocations this takes milliseconds.
- Pages go back to write-back before they return to the page pool, so the
  pools do not save the PAT changes.
- `NVreg_UsePageAttributeTable` no longer exists ("unknown parameter ...
  ignored").

## Locks

- **RM API lock:** an rwsem. Alloc, free, map, unmap and controls take it for
  writing unless the class sets an RO flag. SystemMemory allocates under the
  RO lock (taken after the kernel allocation) but frees under the RW lock.
- **RM GPU lock:** also needed by the display interrupt bottom half. A long
  GPU lock holder delays vblank and flip events on all heads.
- **`nvkms_lock`:** one semaphore for nearly all of NVKMS: every KAPI ioctl
  (including ApplyModeSetConfig), all NVKMS timers and RM callbacks on the
  single `nvkms_kthread_q`, and with `nvidia_drm.vblank=1` the RG vblank
  callbacks. HDMI FRL link training (up to 7 attempts with GSP RPCs) runs under
  it during a modeset.

## Scanout memory

- Scanout GEM objects are physically contiguous VRAM
  (`nvKmsKapiAllocateVideoMemory`); compressed ones are also aligned to the
  compression page size. They have no sysmem fallback, because the display
  engine of a dGPU cannot scan out from system memory. Fragmented VRAM makes
  them fail even with enough free VRAM.

## Reading the kernel log

- Release builds print only LEVEL_ERROR (`_nvDbgPrintMsg()`); LEVEL_INFO and
  LEVEL_WARNING lines never appear.
- "Out of memory [NV_ERR_NO_MEMORY] ... @ system_mem.c:NNN" without an
  `nv_gpu_ops.c` line comes from a user-space client; with `nv_gpu_ops.c`
  it comes from UVM. The exact line numbers identify the case; see
  `evidence/2026-10-26-gotg-explicit-pagesize/README.md` for a mapping.
- "x86/PAT: ... freeing invalid memtype [mem 0x00000000-0x00000fff]" floods
  come from the error path of a failed sysmem allocation in stock drivers
  (`analysis/2026-10-18-pat-memtype-flood.md`).
- UVM hides its own fallback messages unless
  `echo 1 > /sys/module/nvidia_uvm/parameters/uvm_debug_prints`.
- `dmaAllocMapping_GM107: can't update VA space` with `gpu_vaspace.c`
  asserts: user space mapped an already mapped GPU VA range or unmapped part
  of one. RM rejects it; no process name is logged.

## Useful tracing points

Function names that kprobes can attach to in `nvidia.ko` (not inlined in
615.78.08): `nv_alloc_system_pages`, `nv_free_system_pages`. Struct offsets
for `nv_alloc_t` change between releases; check with
`pahole -C nv_alloc_s /sys/kernel/btf/nvidia` before using
`tools/trace/nv-sysmem-fail-trace.sh` on a new release.
