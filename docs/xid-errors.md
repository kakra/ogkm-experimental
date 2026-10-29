# Xid errors on the test system

Every NVIDIA Xid seen on the test system (and one on the previous system),
what NVIDIA documents about it, where it most likely comes from, and whether
the series can do anything about it.

Sources are marked:

- **[README]**: the driver README of 615.78.08 (`README.txt`, installed with
  the driver documentation).
- **[Changelog]**: `NVIDIA_Changelog` of 615.78.08.
- **[Catalog]**: NVIDIA's online [Xid catalog][xid-catalog] (the README links
  the [Xid errors guide][xid-guide]; page last updated 2026-09-09).
- **[Source]**: the open kernel module source of tag 615.78.08.
- **[Inference]**: our own reading, not confirmed by NVIDIA.

## What the driver documentation says

The 615.78.08 README has no Xid table. Its FAQ (chapter 7) only says that
Xid messages "indicate that a general GPU error occurred, most often due to
the driver misprogramming the GPU or to corruption of the commands sent to
the GPU", and points to the online guide **[README]**. Individual Xids appear
only in two places: Xid 81 (VGA console hang, FAQ) and Xid 79 (RHEL 8 init
failure, chapter 9 "Known Issues"). Neither was seen here.

The Changelog lists per-release fixes for Xids in specific games. For this
system the relevant entries are **[Changelog]**:

- 615.71.09: "Fixed an Xid 109 error when loading PRAGMATA on Wayland."
- 610.57.04: STALKER 2 crashing with `VK_DEVICE_LOST` and Xid 31 with
  `VKD3D_CONFIG=descriptor_heap`.
- 595.45.04: "GPU hangs and Xid errors in Black Myth: Wukong".

Several earlier entries fix Xid 13 and Xid 31 in DXVK or Vulkan games the
same way. These are fixes in the user space driver: the same Xid number is
used for unrelated application or driver bugs, and the fix for one game does
not tell anything about another.

## Observations

The journal starts on 2026-09-14 and covers 14 boots up to 2026-10-29.
Searched with `journalctl _TRANSPORT=kernel -g 'NVRM: Xid'` over all boots,
plus the traces and evidence of this repository. Older events come from
posts in the NVIDIA developer forum (user hurikhan77).

| Date (CET) | Xid | Process | Channel, Info | Boot uptime | Driver | Data |
|---|---|---|---|---|---|---|
| 2026-10-26 01:06:45 | 109 | `GameThread` (Cyberpunk 2077, vkd3d-proton) | `0x00000028`, `0x23c030` | ~12 min | 615.78.08 with the series at 41 patches | [analysis][xid109-cp], `evidence/2026-10-26-gotg-explicit-pagesize/kernel-boot.log.xz` |
| 2026-10-29 03:48:09 | 109 | `witcher3.exe` (The Witcher 3, `bin/x64_dx12`, so vkd3d-proton) | `0x00000028`, `0x15c030` | ~8 h 43 min | 615.78.08 with the series at 73 patches (`ogkm/615.78.08` @ `9debc031`) | local trace, not in this repository yet |
| 2025-10-05 (post date) | 154, recovery action 0x2 "Node Reboot Required" (after `uvm encountered global fatal error 0x60`) | – | – | ~2 h (7196 s) | not stated, posted in the 575 thread (most likely 575), stock | [forum post][f575-485] |
| 2025-10-22 (post date) | 154, same as above | – | – | ~65 s | not stated, posted in the 580 thread, stock | [forum post][f580-652] |
| 2021-11-30 (post date) | 69, Class Error, class `0x902d` | several pids | ChId `0x0040` | ~37 h (133683 s) and later | 470.62.13, kernel 5.15.5, stock, previous system | [forum thread][f470] |

The two Xid 154 lines and the Xid 69 lines are not in the journal (it starts
2026-09-14); they are only preserved in the forum posts.

No Xid in the boots with the stock 615.71.09 and 615.78.08 modules
(2026-10-05 to 2026-10-23). Two Xid 109 events are too few to tell anything
about the series either way.

The log lines:

```
Oct 26 01:06:45 kernel: NVRM: Xid (PCI:0000:01:00): 109, pid=22417, name=GameThread, channel 0x00000028, errorString CTX SWITCH TIMEOUT, Info 0x23c030
Oct 29 03:48:09 kernel: NVRM: Xid (PCI:0000:01:00): 109, pid=405848, name=witcher3.exe, channel 0x00000028, errorString CTX SWITCH TIMEOUT, Info 0x15c030
```

## Xid 109: context switch timeout

**Meaning.** Mnemonic `ROBUST_CHANNEL_CTXSW_TIMEOUT_ERROR`, "Context Switch
Timeout Error"; immediate action `RESET_GPU`, investigatory action
`CONTACT_SUPPORT`; no trigger conditions are given **[Catalog]**. The README
has no entry for it.

**In the source.** `nverror.h` has no define for 109 (gap between
`NVLINK_REMOTE_TRANSLATION_ERROR` (108) and `SEC_FAULT_ERROR` (110)). The Xid
is raised inside the GSP-RM firmware and only forwarded by
`_kgspRpcOsErrorLog()` (`src/nvidia/src/kernel/gpu/gsp/kernel_gsp.c`), which
prints the firmware's error string as is. The meaning of the `Info` value is
not visible in the open source. The default context switch timeout is
`NV_REG_STR_RM_CTXSW_TIMEOUT_DEFAULT` = `0x003fffff` µs, about 4.2 s
(`src/nvidia/interface/nvrm_registry.h`) **[Source]**.

**When it occurs.** A graphics or compute context did not yield within that
time, so the scheduler could not switch it out: in practice a GPU hang of
that context. On 615.x it is reported for many games under Proton (Monster
Hunter Wilds, God of War Ragnarök, Plague Tale Requiem, 007 First Light with
path tracing, Final Fantasy XV, Control Resonant), mostly with ray tracing,
path tracing or DLSS, several with internal NVIDIA bug numbers. One case
was traced to `VK_NV_raw_access_chains` (fixed in DXVK), one was fixed in
615.71.09 (PRAGMATA) **[Changelog]**, the others are open. Upstream issue
[#1282][issue-1282] shows the same signature for Cyberpunk 2077 with DLSS on
610.57.04, before this series existed.

**Observations here.** Both on channel `0x00000028` with the same low Info
word `c030`, both D3D12 games through vkd3d-proton. Cyberpunk: ray tracing
and DLSS Ultra Performance, Reflex boost, first start after the 2.5 game
update, hang right after the shader compile phase. Witcher 3: HairWorks on,
the DX12 executable (`bin/x64_dx12/witcher3.exe`), Proton Experimental,
Vulkan through an XWayland surface, MangoHud and obs-vkcapture layers; no
VA space error, page allocation failure, hung task or OOM before
the Xid. The VA space errors later in that boot came from Elite Dangerous,
not from Witcher 3.

**Likely source.** **[Inference]** The GSP firmware only detects and reports
the hang; it is not the cause. The context belongs to the game, so the cause
is in what the user space driver (shader compiler, Vulkan driver) submitted
for it, possibly triggered by a translation layer (DXVK, vkd3d-proton) or
the game itself. The kernel modules are not in that path: the open modules
neither build nor schedule the GPU work of a context. The same channel and
Info low word in two different games suggests a shared cause below the game
(vkd3d-proton or the NVIDIA user space driver), or simply the same channel
slot for the game's main graphics context; this is not proven.

**Can the series help?** No. The patches change display, flip, memory
allocation, PAT and lock paths. None changes context scheduling or the work
a context submits. A longer context switch timeout through the registry key
would only delay the reset of a context that is really hung, and is not
part of the series. To rule out the series, the Cyberpunk case should be
repeated on the stock modules ([analysis][xid109-cp]); the upstream report
on 610.57.04 already points away from it. Next capture:
`PROTON_LOG=1 VKD3D_DEBUG=warn` (both games run through
vkd3d-proton) to see the last pipeline before the hang.

## Xid 154: GPU recovery action changed

**Meaning.** Mnemonic `GPU_RECOVERY_ACTION_CHANGED`. "Xid 154 will be seen
in conjunction with other Xids and summarizes the recovery action required
for other Xids"; informational only **[Catalog]**. The recovery actions are
`NV2080_CTRL_GPU_RECOVERY_ACTION_*` in `ctrl2080gpu.h` (none, GPU reset, OS
reboot, drain P2P, drain and reset, ...) **[Source]**.

**Observations here.** At least twice, both on the stock driver, as posted in
the NVIDIA developer forum (GPU UUID lines left out):

- 2025-10-05, [575 release thread][f575-485] (driver version not stated,
  most likely 575), about 2 h after boot, "especially when running some
  heavier games" with DLSS or ray tracing. The fatal error was logged twice.
  Nothing visibly broke, but `nvidia-smi` showed about 1.2 GB more VRAM in
  use than the per-process sum.

  ```
  [ 7196.695178] NVRM: nvGpuOpsReportFatalError: uvm encountered global fatal error 0x60, requiring os reboot to recover.
  [ 7196.697697] NVRM: Xid (PCI:0000:01:00): 154, GPU recovery action changed from 0x0 (None) to 0x2 (Node Reboot Required)
  ```

- 2025-10-22, [580 release thread][f580-652], 65 s after boot. It went away
  when booting with `init_on_alloc=1`. The same post reports that with this
  driver no Proton game found a D3D adapter, and CUDA error -999.

  ```
  [   65.245612] NVRM: nvGpuOpsReportFatalError: uvm encountered global fatal error 0x60, requiring os reboot to recover.
  [   65.248736] NVRM: Xid (PCI:0000:01:00): 154, GPU recovery action changed from 0x0 (None) to 0x2 (Node Reboot Required)
  ```

Unverified assumption: that `NVreg_InitializeSystemMemoryAllocations=0` was
set at the time. The forum posts only mention `init_on_alloc=1`; the option
was found later in the local modprobe configuration (now commented out), and
whether it was set with 575 or 580 is not known.

**Likely source.** **[Inference]** from code reading, assuming the option
above was set: UVM's channel error notifier is system memory that is not
zeroed with that option, and `uvm_channel.c` treats any non-zero status as `NV_ERR_RC_ERROR`. The Xid 154
then only reports the recovery action for that UVM error. That
`init_on_alloc` made it go away fits this, since it zeroes the pages the
driver did not. If the option was not set, the cause is open.

**Can the series help?** If the assumption holds, not needed: the driver
default (`NVreg_InitializeSystemMemoryAllocations=1`) avoids it. Patch 45
zeroes the RM heap from `os_alloc_mem()`, which covers a related class of
uninitialized memory, but it does not change GPU system memory allocations;
the fix for this case is the default setting.
Not seen since 2026-09-14; the module now runs with the default
`NVreg_InitializeSystemMemoryAllocations=1` and without `init_on_alloc`.

## Xid 69: graphics engine class error (historical)

**Meaning.** `ROBUST_CHANNEL_GR_CLASS_ERROR` (69 in `nverror.h`)
**[Source]**, "Graphics Engine class error"; immediate action
`RESTART_APP`, investigatory action `CHECK_APP/CUDA`, no trigger conditions
given **[Catalog]**.

**Observation.** 2021, driver 470.62.13, kernel 5.15.5-gentoo, on the
previous system (other mainboard and GPU), reported in a
[forum thread][f470] that is mainly about an `nv_drm_exit` warning at boot:

```
[133683.658272] NVRM: Xid (PCI:0000:01:00): 69, pid=245483, Class Error: ChId 0040, Class 0000902d, Offset 00000250, Data ffffffff, ErrorCode 0000000c
```

Repeated with other pids on the same channel, class and offset. The
post links them to kwin crashes when starting Proton games,
and videos and Chrome pages going blank for short times while gaming.
Class `0x902d` is `FERMI_TWOD_A`, the 2D engine class
(`src/common/sdk/nvidia/inc/class/cl902d.h`) **[Source]**.

**Likely source.** **[Inference]** A method of the 2D class was rejected by
the graphics engine for one process's channel; with the same channel for
several pids this was probably a shared client such as the compositor or
X server. Not analyzed further at the time.

**Can the series help?** No; historical, on a driver branch and system that
are no longer in use. Not seen since.

## Other open topics

### "can't update VA space" (`gpu_vaspace.c:4502`)

**[README]**, **[Changelog]**, **[Catalog]**: nothing. The README does not
mention GPU virtual address space errors, and these messages are not Xids,
so the catalog does not cover them. The only Changelog entry near the topic
is in 595.104.02 (2026-09-22): "Fixed a failure that could occur when
allocating GPU page tables larger than 2 GiB (INT_MAX)". It is about page
table size, not overlapping mappings, and it is not clear from the Changelog
whether the 615 branch has it.

Our state: the overlap comes from a sequence of map/unmap calls of the
closed user space driver; RM rejects the map correctly
([analysis][vaspace]). Related mapping failures existed a year earlier on
the stock 575 branch: a [forum post][f575-486] of 2025-10-06 shows
`intermapRegisterDmaMapping: Failed to insert new mapping node` floods with
asserts at `gpu_vaspace.c:4838` and `:2272` (line numbers of that release).
**[Inference]** The journal shows the 4502 blocks since 2026-09-26, before
the first local series (2026-10-23), which agrees with that. They are not
followed by an Xid here: the 2026-10-29 blocks came from Elite Dangerous
minutes after the Witcher 3 Xid, and the Cyberpunk Xid had no such block
before it in its boot. Upstream issue [#1282][issue-1282] reports both
together for Cyberpunk; a link is still unproven.

### Watchdog

The README's `Interactive` X option (appendix B) describes the driver's
watchdog that "attempts to detect and terminate GPU programs that get
stuck" **[README]**. It is an X driver option and does not apply to a
Wayland session; **[Inference]** the Xid 109 detection in the GSP firmware
works independently of it.

### GSP firmware

Chapter 43 only describes how to query, enable and disable the GSP firmware
(`NVreg_EnableGpuFirmware`); chapter 44 lists slower initialization and
longer suspend latency as known limits of the open modules **[README]**.
Nothing on error reporting. Disabling GSP is not possible with the open
modules, so this is no way to tell firmware and kernel module apart.

### Earlier related reports

Not Xids, but memory problems reported in the NVIDIA developer forum on
stock drivers before this series. The sysmem side is analyzed in
[sysmem fragmentation][sysmem-frag].

- 2025-03-30, [570 thread][f570-454], kernel 6.12.20: plasmashell froze,
  `pagefault_out_of_memory` and `VM_FAULT_OOM leaked out to the #PF
  handler`, a shmem warning after killing the process, about 500 MB of
  VRAM in `nvidia-smi` not accounted to any process.
- 2025-09-28, [575 thread][f575-481]: after about 5 days of uptime games no
  longer started; `sysmemConstruct_IMPL: *** Cannot allocate sysmem through
  fb heap` and `Error allocating client shadow fault buffer for
  non-replayable faults`.
- 2025-11-03, [580 thread][f580-710]:
  `_kgmmuClientShadowFaultBufferPagesAllocate: Allocation failed with big
  page size, retrying with default page size` with `NV_ERR_NO_MEMORY` from
  `mem_desc.c:1359`, `system_mem.c:354` and `nv_gpu_ops.c:4922` after some
  uptime, earlier after ray traced games; suspected cause of Chrome and
  plasmashell crashes.
- 2025-12-11, [590 thread][f590-117], driver 590.44.01: the same shadow
  fault buffer messages while not gaming, at 1961 of 12288 MiB VRAM in use,
  without visible effect.

### Not found in the documentation

Nothing about HairWorks, ray tracing or DLSS hangs, system memory
fragmentation, the PAT memtype flood, lock stalls, or the `Info` field of an
Xid.

[xid-guide]: https://docs.nvidia.com/deploy/xid-errors/index.html
[xid-catalog]: https://docs.nvidia.com/deploy/xid-errors/analyzing-xid-catalog.html
[issue-1282]: https://github.com/NVIDIA/open-gpu-kernel-modules/issues/1282
[xid109-cp]: ../analysis/2026-10-26-xid109-cyberpunk.md
[vaspace]: ../analysis/2026-10-28-vaspace-overlap.md
[sysmem-frag]: ../analysis/2026-10-24-sysmem-fragmentation.md
[f470]: https://forums.developer.nvidia.com/t/current-nvidia-driver-470-62-13-sometimes-backtraces-on-boot-kernel-5-15/196600
[f570-454]: https://forums.developer.nvidia.com/t/570-release-feedback-discussion/321956/454
[f575-481]: https://forums.developer.nvidia.com/t/575-release-feedback-discussion/330513/481
[f575-485]: https://forums.developer.nvidia.com/t/575-release-feedback-discussion/330513/485
[f575-486]: https://forums.developer.nvidia.com/t/575-release-feedback-discussion/330513/486
[f580-652]: https://forums.developer.nvidia.com/t/580-release-feedback-discussion/341205/652
[f580-710]: https://forums.developer.nvidia.com/t/580-release-feedback-discussion/341205/710
[f590-117]: https://forums.developer.nvidia.com/t/590-release-feedback-discussion/353310/117
