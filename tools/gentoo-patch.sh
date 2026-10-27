#!/bin/bash
# Write the series of the current release as one patch for Gentoo's
# x11-drivers/nvidia-drivers to stdout.
#
# Usage: tools/gentoo-patch.sh [<release>] | sudo tee \
#            /etc/portage/patches/x11-drivers/nvidia-drivers/ogkm.patch
#
# The ebuild unpacks the open module sources into kernel-module-source/ next
# to the .run package's own kernel-open/, so the paths need that prefix.

source "$(dirname "$0")/lib.sh"

check_release "${1-}"
check_driver

git -C "$DRIVER" format-patch --stdout --zero-commit --no-signature \
	--src-prefix=a/kernel-module-source/ --dst-prefix=b/kernel-module-source/ \
	"refs/tags/$RELEASE..HEAD"
