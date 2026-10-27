# Installing a series on your system

This guide is written for people and for AI coding agents that help someone
install the patches. Agents: read the rules first and follow the steps in
order; stop and ask whenever a check fails.

Read the disclaimer in the [README](../README.md#disclaimer) first: there is
no support, and recovering a system that no longer boots is the user's own
job.

## Rules for agents

- Before anything else, show the user the disclaimer from the README (quote
  the whole "Disclaimer" section verbatim, both paragraphs) and ask them to confirm explicitly that they have read and
  accept it. Do not continue without a clear yes, and do not treat silence,
  a general "go ahead" or an earlier request as acceptance. Ask once per
  conversation, before the first step of this guide.
- Every command that needs root, changes the package manager state, the
  initramfs or the boot setup is the user's decision. Show the exact command
  and why, and wait for approval.
- Never mix versions. The series, the kernel modules and the user-space driver
  must all be the same driver release. There are no backports: if the
  installed driver is a different release than a series in `patches/`, say so
  and stop, unless the user explicitly wants to port the series themselves.
- Keep a way back. Before replacing modules, note how to restore the
  distribution's package (reinstall command or the previous package file) and
  tell the user. Make sure the user knows how to boot without the patched
  modules (another kernel entry, a rescue system) before they reboot.
- Prefer integrating the patches into the distribution's own package build
  over installing modules by hand: the package manager then knows about them,
  rebuilds them for new kernels, and can roll back.
- Verify after installing (last section), and report what was verified and
  what was not.

## 1. Collect facts

```sh
cat /sys/module/nvidia/version                 # running driver release
uname -r                                        # running kernel
modinfo -F license nvidia                       # "Dual MIT/GPL" = open modules
ls /sys/firmware/efi/efivars >/dev/null 2>&1 && mokutil --sb-state  # Secure Boot
```

Then find out which package provides the kernel modules and how it builds
them (distribution package, DKMS, akmods, prebuilt for a specific kernel).

- The series needs the **open** kernel modules. GPUs before Turing are not
  supported by them.
- Compare the release with `README.md` (current release) and
  `patches/<release>/`.

## 2. Check what the package builds from

The series touches both `kernel-open/` and `src/`. The `kernel-open/`
directory of the `.run` installer and of most DKMS packages built from it
ships RM and NVKMS only as prebuilt objects (`nv-kernel.o_binary`,
`nv-modeset-kernel.o_binary`), so patches to `src/` cannot be built there.

```sh
# Which patches need the full source?
grep -l '^diff --git a/src/' patches/<release>/*.patch
```

- Package builds from `NVIDIA-kernel-module-source-<release>.tar.xz` or from
  the GitHub tag (full tree with `src/`): the whole series can be integrated.
- Package builds from a `kernel-open/` tree with `.o_binary` files: only the
  patches without `src/` changes would apply. Do not install a partial series
  without telling the user which fixes are missing; prefer building from the
  full source (section 4).

Test the series against a scratch copy of the tree the package uses, to find
the right `-p` level and path prefix. Apply the patches for real and in order:
later patches build on earlier ones, so a `--dry-run` of each patch against
the pristine tree reports false failures.

```sh
cp -a <source tree> <scratch dir>
for p in patches/<release>/*.patch; do patch -p1 -s -d <scratch dir> < "$p" || { echo "FAILED: $p"; break; }; done
```

## 3. Integrate into the distribution package

### Gentoo (`x11-drivers/nvidia-drivers`)

Verified on the test system. The ebuild unpacks the full module source as
`kernel-module-source/` and applies every file in
`/etc/portage/patches/x11-drivers/nvidia-drivers/`. Look at that directory
first: an older export of the series (under any name) must be replaced, not
kept next to the new one, or the patches are applied twice and the build
fails.

```sh
tools/gentoo-patch.sh | sudo tee /etc/portage/patches/x11-drivers/nvidia-drivers/ogkm.patch
sudo emerge -1 x11-drivers/nvidia-drivers
```

Rollback: remove the patch file and run the same `emerge` again.

### Arch Linux (`nvidia-open`, `nvidia-open-dkms`)

Not tested here. Get the package build files (`pkgctl repo clone --protocol=https nvidia-open`),
check in the `PKGBUILD` that the source is the open-gpu-kernel-modules tag of
the same release, then add the patches to `source=()` (with `SKIP` or real
checksums), apply them in `prepare()` with `patch -Np1 -i`, raise `pkgrel`
and build with `makepkg`. Install the result with `pacman -U`; rollback by
reinstalling the repository package.

### DKMS based packages (Debian, Ubuntu, Fedora/RPM Fusion and others)

Not tested here. Look at `/usr/src/nvidia-<release>/` (or the akmods source
RPM). If it contains only `kernel-open`-style directories with `.o_binary`
files, see section 2. Patching files below `/usr/src` by hand works until the
next package update overwrites them; a local rebuild of the source package
with the patches added is the clean way.

### NixOS

Not tested here. The open modules are built from the GitHub source; an
override of the open package with additional `patches` in the NVIDIA package
set selected by `hardware.nvidia.package` is the expected way. Check the
attribute names of the nixpkgs version in use.

## 4. Building from the full source by hand

When the package cannot be patched:

```sh
git clone https://github.com/kakra/open-gpu-kernel-modules.git
cd open-gpu-kernel-modules
git checkout ogkm/<release>
make modules -j$(nproc)
sudo make modules_install -j$(nproc)
sudo depmod -a
```

Then make sure these modules win over the distribution's: the distribution
package may install its own into a directory with higher priority, and the
initramfs may contain a copy. Regenerate the initramfs if the nvidia modules
are in it (`lsinitrd`/`lsinitramfs`). With Secure Boot, the modules must be
signed with an enrolled key. The user-space driver must stay at the same
release. This setup has to be repeated for every kernel update; tell the
user.

## 5. Verify

After a reboot (or after unloading all nvidia modules and the display
server):

```sh
cat /sys/module/nvidia/version                       # expected release
ls /sys/module/nvidia_drm/parameters/ | grep deadline_boost   # only with the series
journalctl -k -b | grep -E 'NVRM|nvidia' | head -50   # load messages, errors
```

Report any regression with the bug or regression issue template.
