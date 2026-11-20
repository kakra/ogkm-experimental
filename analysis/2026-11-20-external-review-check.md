# Check of an external review of the 620.73.04 series

An external review of the series at cee76fcb (158 patches on `620.73.04`),
done on the diffs alone without the full source tree, raised suspicions in
several patches. Each was checked against the full source at cee76fcb.
Patch numbers and file and line references are those of the series at
cee76fcb unless noted. The series at f1ec5d55 counts one higher from patch
25 on and two higher from patch 105 on: 105 there is 106, and its fix is
107. See also
[the review of the series](2026-11-19-series-review.md).

Result: none of the suspicions is a defect. One known limitation (12)
remains. One hardening of 105 came out of it and is in the series at
f1ec5d55 as patch 107.

## Verified, not changed

- 127 (return the display semaphores of a commit that failed): an already
  signaled in-fence does not leak a reference or a semaphore. On
  `-ENOENT` from `dma_fence_add_callback()` the callback is called by hand
  and the code falls through to `case 0`, which hands the fence reference to
  the fence data (`kernel-open/nvidia-drm/nvidia-drm-modeset.c:373-387`).
- 21 (let kernel clients release references during GPU removal): there is
  no unprotected window on `nv_linux_removing_devices`.
  `nv_pci_remove_helper()` holds `LOCK_NV_LINUX_DEVICES()` from
  `kernel-open/nvidia/nv-pci.c:1787` and drops it only around the 500 ms
  sleep (1840-1845); adding and removing an entry
  (`kernel-open/nvidia/nv.c:6102-6123`) and the lookups
  (`nv.c:1366-1409`) run under the same lock.
- 82, 83 (share map walk and display ISR callback lists under the low
  latency lock): no same-CPU deadlock with the display interrupt. The
  interrupt paths take the low latency lock only with
  `kdispAcquireLowLatencyLockConditional()`
  (`src/nvidia/arch/nvalloc/unix/src/unix_intr.c:64`, `:405`,
  `src/nvidia/src/kernel/core/locks.c:1513`) and skip the work when it is
  held. The event callbacks that `kdispNotifyEvent()` runs under the share
  map lock (`src/nvidia/src/kernel/gpu/disp/kern_disp.c:1121-1181`) do not
  take the low latency lock: the NVKMS display event callbacks only queue
  an NVKMS timer (`src/nvidia-modeset/src/nvkms-rm.c:1808-1858`).
- 37 (keep old cursor framebuffers): the check of `held_fbs` without
  `held_fbs_lock` before queueing the release work
  (`kernel-open/nvidia-drm/nvidia-drm-modeset.c:1020`) is a hint only, and
  `list_empty()` reads the list head with `READ_ONCE()`
  (`include/linux/list.h` of Linux 7.3.5).
- 105 (opt-in per-connector MST DDC adapters), teardown: an I2C request
  still in flight is detached cleanly in both orders. Deleting it runs
  `~Message()` for its read and write messages, which calls `clear()`:
  timer callbacks, both splitters, deferred completions and the message
  lists (`src/common/displayport/inc/dp_messages.h:335-362`). When the
  message manager goes first, `~MessageManager()` sets `parent = 0` on
  every pending message and calls `messageFailed()`
  (`src/common/displayport/src/dp_messages.cpp:810` ff.), whose handler
  in the request clears the message
  (`src/common/displayport/src/dp_deviceimpl.cpp:42-72`). All of it runs
  under the NVKMS lock.
- 119, 151 (GEM allocation back-off): the per-file back-off fields are
  read and written without a lock on purpose, as the comment at
  `struct nv_drm_file` says (`kernel-open/nvidia-drm/nvidia-drm-priv.h:446-457`).
  Parallel allocations on one file can lose an increment of the refused
  count, which only appears in a log line, or let one allocation through
  early or refuse one more; the `gem_backoff` counter itself is atomic.
  `READ_ONCE()`/`WRITE_ONCE()` or `data_race()` would only quiet KCSAN.
- 115 (raster position register): the bounds check of `regOffset` does not
  overflow. `info.regOffset + sizeof(u32)` is computed in `size_t`, not in
  32 bits (`kernel-open/nvidia-drm/nvidia-drm-crtc.c:4246-4249`).
- 144 (dmem cgroup uncharge use-after-free): `rcu_read_lock()` around the
  uncharge and the second check (`kernel-open/nvidia/os-interface.c:3716-3728`)
  is enough. The pool is freed with `call_rcu()`
  (`kernel/cgroup/dmem.c:144` of Linux 7.3.5), and the css after an RCU
  grace period by the cgroup core.
- 92 (don't take the modeset locks to revoke nothing): the lockless check
  in `nv_drm_filep_has_modeset_permission()`
  (`kernel-open/nvidia-drm/nvidia-drm-drv.c:1789-1818`) is formally a data
  race with a concurrent revoke, but it only compares pointers, and either
  outcome matches a valid order: a stale match takes the locks and finds
  nothing, a miss is the same as revoking after the other revoke.
- 158 (vblank delivery threads at RT priority): `sched_set_fifo_low()` is
  `EXPORT_SYMBOL_GPL` (`kernel/sched/syscalls.c:827` of Linux 7.3.5), and
  all open kernel modules declare `MODULE_LICENSE("Dual MIT/GPL")`
  (`kernel-open/nvidia-drm/nvidia-drm-linux.c:107`,
  `kernel-open/nvidia-modeset/nvidia-modeset-linux.c:2367`). On current
  kernels the fair and sched_ext deadline servers, not the RT throttling
  limit, keep normal tasks running next to RT tasks.

## Known limitation

12 (make surface registration RM calls without `nvkms_lock`): the
per-open device of a registering client can be freed while it waits for
RM.

- `RegisterSurfacePlanesUnlockedRm()` and `FreeSurfaceRmObjectsUnlocked()`
  drop the global NVKMS lock for their RM calls
  (`src/nvidia-modeset/src/nvkms-surface.c:584`, `:143`).
- In that window, `RestoreConsole()` can free the core channel, fail to
  allocate it again and call `nvRevokeDevice()`
  (`src/nvidia-modeset/src/nvkms.c:960-983`), which frees the per-open
  devices of all clients (`nvkms.c:5371` ff.).
- Only the failed reallocation of the core channel leads there, so the GPU
  is already in a bad state. Resume, the other caller of
  `nvRevokeDevice()` after a failed core channel allocation
  (`src/nvidia-modeset/src/nvkms-evo.c:5550-5553`), is excluded by the PM
  lock. Freeing the core channel alone is caught by
  `surfaceDescGeneration` (`nvkms-evo.c:5611`, checked at
  `nvkms-surface.c:643`), which makes the registration bind its
  descriptors again under the lock.
- Fix sketch: count unlocked RM calls in flight per open device and defer
  `nvFreePerOpenDev()` (`nvkms.c:1023`) until the count drops to zero.
- Minor: on failure, the caller frees the surface's RM objects also for
  handles that were only reserved and never allocated; RM returns an error
  for these, which is harmless.

## Changed: MST I2C transfers stop on a signal or freeze (105; fix 107 at f1ec5d55)

The poll loop of `MstI2cTransfer()`
(`src/nvidia-modeset/kapi/src/nvkms-kapi.c:4770-4783`) waits up to 5 s in
1 ms steps for a remote I2C request. Its caller is the i2c-dev ioctl of a
user space tool such as ddcutil, and the loop looked neither at pending
signals nor at the freezer, so a killed tool or a suspend waited for the
rest of the 5 s when the monitor didn't answer. The interface is opt-in
(`nvidia_drm.mst_ddc=1`).

107 adds `nvkms_wait_interrupted()` to the NVKMS OS interface (`nvkms-kapi.c`
is OS independent), true when a signal is pending or the task is being
frozen, and leaves the loop through the existing cancel path; the transfer
then fails with `-EIO`. Built, not tested: the test system has no MST
hardware.
