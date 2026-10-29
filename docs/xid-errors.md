# Xid errors on the test system

Every NVIDIA Xid seen on the test system, what NVIDIA documents about it,
where it most likely comes from, and whether the series can do anything
about it.

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
plus the traces and evidence of this repository. The older Xid 154 comes
from a post in the NVIDIA developer forum (user hurikhan77).

| Date (CET) | Xid | Process | Channel, Info | Boot uptime | Driver | Data |
|---|---|---|---|---|---|---|
| 2026-10-26 01:06:45 | 109 | `GameThread` (Cyberpunk 2077, vkd3d-proton) | `0x00000028`, `0x23c030` | ~12 min | 615.78.08 with the series at 41 patches | [analysis][xid109-cp], `evidence/2026-10-26-gotg-explicit-pagesize/kernel-boot.log.xz` |
| 2026-10-29 03:48:09 | 109 | `witcher3.exe` (The Witcher 3, `bin/x64_dx12`, so vkd3d-proton) | `0x00000028`, `0x15c030` | ~8 h 43 min | 615.78.08 with the series at 73 patches (`ogkm/615.78.08` @ `9debc031`) | local trace, not in this repository yet |
| 2025-10-22 (post date) | 154, recovery action 0x2 "Node Reboot Required" (after `uvm encountered global fatal error 0x60`) | – | – | ~65 s | not stated, posted in the 580 thread, stock | [forum post][f580-652] |

The Xid 154 lines are not in the journal (it starts 2026-09-14); they are
only preserved in the forum post.

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

**Observation here.** Posted in the NVIDIA developer forum (GPU UUID line
left out):

```
[   65.245612] NVRM: nvGpuOpsReportFatalError: uvm encountered global fatal error 0x60, requiring os reboot to recover.
[   65.248736] NVRM: Xid (PCI:0000:01:00): 154, GPU recovery action changed from 0x0 (None) to 0x2 (Node Reboot Required)
```

2025-10-22, [580 release thread][f580-652], 65 s after boot. It went away
when booting with `init_on_alloc=1`. The same post reports that with this
driver no Proton game found a D3D adapter, and CUDA error -999.

Unverified assumption: that `NVreg_InitializeSystemMemoryAllocations=0` was
set at the time. The forum post only mentions `init_on_alloc=1`; the option
was found later in the local modprobe configuration (now commented out), and
whether it was set with 580 is not known.

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
([analysis][vaspace]). **[Inference]** The journal shows the 4502 blocks since 2026-09-26, before
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

### Not found in the documentation

Nothing about HairWorks, ray tracing or DLSS hangs, system memory
fragmentation, the PAT memtype flood, lock stalls, or the `Info` field of an
Xid.

[xid-guide]: https://docs.nvidia.com/deploy/xid-errors/index.html
[xid-catalog]: https://docs.nvidia.com/deploy/xid-errors/analyzing-xid-catalog.html
[issue-1282]: https://github.com/NVIDIA/open-gpu-kernel-modules/issues/1282
[xid109-cp]: ../analysis/2026-10-26-xid109-cyberpunk.md
[vaspace]: ../analysis/2026-10-28-vaspace-overlap.md
[f580-652]: https://forums.developer.nvidia.com/t/580-release-feedback-discussion/341205/652
