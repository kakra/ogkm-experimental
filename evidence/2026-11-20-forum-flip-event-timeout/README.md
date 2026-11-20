# Flip event timeouts at boot with several displays, reported in the NVIDIA forum (2026-11-20)

External report, not reproduced on the test system. No raw files: the data
below is transcribed from the forum posts.

## Setup (as reported)

- System: RTX 4090, Arch Linux, Plasma 6.8.3 on Wayland, several displays.
- Driver: 620.73.04, stock; the series was not tested there.
- Kernel: 7.3.5.

## Steps

None beyond booting into the desktop. Reported in
[forum post #94][f388030-94] (2026-11-20).

## Result

Reported:

- Early in the boot, the kernel log shows "Flip event timeout on head 0"
  at 14.79 s and "Flip event timeout on head 1" at 17.80 s, followed by
  two "nv_flip == NULL" messages.
- On boots with these messages, SDDM starts late.

In [forum post #95][f388030-95], NVIDIA opened internal bug 7126445 for
"Flip event timeout" and "nv_flip == NULL" with several displays (on
620.70.06) and is trying to reproduce it.

Inferred, not verified:

- The messages match the case that patch 149 of the series at f1ec5d55,
  "nvidia-drm: handle display events off the NVKMS event thread"
  (VeilSilence, via gulafaran/patches), addresses: a blocking commit
  waits for its flip event while the NVKMS event thread that delivers it
  is held up by a display event handler waiting for DRM locks, runs into
  its timeout, and the late flip event then finds no queued flip. Whether
  the patch removes the timeouts on that system is not known.

## Open questions

- Whether the timeouts go away with the series, or with patch 149 alone,
  on an affected multi-display system.

[f388030-94]: https://forums.developer.nvidia.com/t/388030/94
[f388030-95]: https://forums.developer.nvidia.com/t/388030/95
