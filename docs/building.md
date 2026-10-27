# Building and installing

Developer notes for the test system. For integrating a series into a
distribution package, see [installing.md](installing.md).

The series applies to a clone of the upstream repository at the tag of the
same driver release. The modules must be used with the GSP firmware and the
user-space driver of exactly that release.

## From the fork branch or an exported series

```sh
git clone https://github.com/NVIDIA/open-gpu-kernel-modules.git
cd open-gpu-kernel-modules
git checkout -b ogkm 615.78.08
git am /path/to/ogkm-experimental/patches/615.78.08/*.patch
make modules -j$(nproc)
sudo make modules_install -j$(nproc)
```

Install the user-space driver of the same release without its kernel modules,
e.g. `sh NVIDIA-Linux-x86_64-615.78.08.run --no-kernel-modules`, or let the
distribution package provide it.

To check that a series applies and builds without touching the system:

```sh
tools/check-series.sh --build
```

## Gentoo

`x11-drivers/nvidia-drivers` always builds the open modules (`USE=kernel-open`
was removed). It unpacks them
into `kernel-module-source/` and applies user patches from
`/etc/portage/patches/x11-drivers/nvidia-drivers/`. The paths need that
prefix, so use the combined patch:

```sh
tools/gentoo-patch.sh | sudo tee /etc/portage/patches/x11-drivers/nvidia-drivers/ogkm.patch
sudo emerge -1 x11-drivers/nvidia-drivers
```

Reboot (or unload and reload all nvidia modules) afterwards.

## Checking which modules are loaded

```sh
cat /sys/module/nvidia/version
ls /sys/module/nvidia_drm/parameters/   # deadline_boost* only exists with the series
```
