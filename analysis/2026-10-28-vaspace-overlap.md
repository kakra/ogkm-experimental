# "can't update VA space": stale VA in the user space driver

- **Status:** cause found in the closed user space driver, nothing to fix in
  the kernel modules
- **Evidence:** `evidence/2026-10-28-gotg-vaspace-overlap/`, earlier kernel
  logs in `evidence/2026-10-26-gotg-explicit-pagesize/`

## Symptom

During D3D12 games (Guardians of the Galaxy via vkd3d-proton) the kernel log
shows blocks like:

```
NVRM: nvCheckFailedNoLog: Check failed: 0 == (pMapNode->gpuMask & gpuMask) @ gpu_vaspace.c:4502
NVRM: nvCheckOkFailedNoLog: Check failed: Invalid argument to call [NV_ERR_INVALID_ARGUMENT] (0x0000001F) returned from _gvaspaceMappingInsert(pGVAS, pGpu, pVASBlock, vaLo, vaHi, flags) @ gpu_vaspace.c:2035
NVRM: nvCheckFailedNoLog: Check failed: NV_OK == status @ virt_mem_allocator_gm107.c:2585
NVRM: dmaAllocMapping_GM107: can't update VA space for mapping @vaddr=0x28720000
```

29 blocks in a 32 h boot, 14 in a 24 minute session and 65 in 3 h after
upstream PR [#1483][pr-1483] was added to the series, 6 in about 1 h on
2026-10-28. No process name is logged.

## Code path

`NV_ESC_RM_MAP_MEMORY_DMA` → `virtmemMapTo_IMPL()` → `dmaAllocMap()` →
`dmaAllocMapping_GM107()`. For a map into an existing virtual object
(`NV50_MEMORY_VIRTUAL`, no new VA allocation) RM only checks for overlaps in
`dmaUpdateVASpace_GF100()` → `gvaspaceMap_IMPL()` →
`_gvaspaceMappingInsert()`: `btreeSearch(vaLo)` finds a mapping node of the
same GPU that covers `vaLo`, and the insert fails. RM then returns
`NV_ERR_INVALID_ARGUMENT` to the client; nothing is changed. With a freshly
allocated VA range an overlap cannot happen, because the mapping tree belongs
to the VA block.

In the sessions with these errors there were no unmap failures in RM
(`gpu_vaspace.c:4586/4594`) and no `intermapRegisterDmaMapping` failures, so
the mapping tree and the client mapping list agreed. The bookkeeping bug that
PR [#1483][pr-1483] fixes (partial unmaps) is not involved.

## Tracing

The RM functions in `nv-kernel.o` cannot be probed (built without fentry:
"trace_kprobe: Could not probe notrace function gvaspaceMap_IMPL"), and
`nvidia_unlocked_ioctl` is not in kallsyms. `tools/trace/nv-vaspace-ioctl.bt`
hooks the ioctl syscall tracepoints instead and logs every map/unmap ioctl
with its handles, VA, length, flags and status;
`tools/trace/nv-vaspace-analyze.py` replays the log per client.

## Cause

The failing calls come from gotg.exe, on the game threads
`DeferedReleaseThread` and `ZRenderManager`, i.e. from the NVIDIA user space
driver below vkd3d-proton. It moves a backing allocation `M` into a virtual
object `A` through a temporary virtual object `T`:

```
map    T <- M  flags 0x208          T at its own VA
unmap  A at VA(A)
unmap  T at VA(T)
map    A <- M  flags 0x0            A at VA(A)
unmap  T at <a VA that is not T's>  -> NV_ERR_OBJECT_NOT_FOUND
```

The next operation on `A` unmaps `A` at the VA that `T` had during the move.
That unmap fails with `NV_ERR_OBJECT_NOT_FOUND`, `A` keeps its mapping, and
the following map into `A` (same memory, flags `0x40000208`:
`ENABLE_FORCE_COMPRESSED_MAP`, `PAGE_KIND_VIRTUAL`, big pages) collides with it
at `gpu_vaspace.c:4502`. Both failures in the trace follow this pattern; one
of them comes 2.7 s after the move, so it is stale state in the driver and
not a race between the two threads. The exact sequences are in the evidence
README.

RM behaves correctly in every step. The kernel modules cannot fix this; it
is a bug in the closed user space driver (presumably `libnvidia-glcore` /
the Vulkan driver; the library was not identified).

## Effect

Not verified: after the failure `A` stays mapped to the right memory, but
with the kind of the plain map instead of the requested forced-compressed
one. No crash in the traced session. The earlier sessions with these errors
had VRAM full, so the moves may be the driver's compaction or eviction under
VRAM pressure; this was not checked.

open-gpu-kernel-modules issue [#1282][issue-1282] reports the same "can't
update VA space" errors together with Xid 109 hangs in Cyberpunk 2077
(`analysis/2026-10-26-xid109-cyberpunk.md`); whether those come from the same
sequence is unknown.

## Next steps

- Report to NVIDIA (developer forum, Linux section): the bug is in the
  closed user space driver, not in the open kernel modules.
- Check whether the errors only appear with VRAM full, and whether other
  D3D12 games show the same sequence.

[pr-1483]: https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1483
[issue-1282]: https://github.com/NVIDIA/open-gpu-kernel-modules/issues/1282
