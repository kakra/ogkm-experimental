#!/bin/bash
# Apply the exported series of the current release to a clean checkout of
# the upstream tag, and optionally build it.
#
# Usage: tools/check-series.sh [--build] [<release>]
#
# Works in build/check-<release>, a temporary worktree of driver/. Verifies
# that the exported files match the fork branch exactly.

source "$(dirname "$0")/lib.sh"

build=
if [[ ${1-} == --build ]]; then
	build=1
	shift
fi
check_release "${1-}"
check_driver

SERIES="$TOP/patches/$RELEASE"
[[ -f $SERIES/series ]] || die "no exported series in ${SERIES#"$TOP"/}, run tools/export-series.sh"

WT="$TOP/build/check-$RELEASE"
mkdir -p "$TOP/build"
if [[ -e $WT ]]; then
	git -C "$DRIVER" worktree remove --force "$WT"
fi
git -C "$DRIVER" worktree add -q --detach "$WT" "refs/tags/$RELEASE"
trap 'git -C "$DRIVER" worktree remove --force "$WT"' EXIT

mapfile -t patches < <(sed "s|^|$SERIES/|" "$SERIES/series")
git -C "$WT" -c user.name=check -c user.email=check@invalid am -q --committer-date-is-author-date "${patches[@]}" ||
	die "series does not apply to $RELEASE"

if ! git -C "$WT" diff --quiet HEAD "$BRANCH" --; then
	git -C "$WT" diff --stat HEAD "$BRANCH" --
	die "applied series differs from $BRANCH, re-export"
fi
echo "Series applies cleanly to $RELEASE and matches $BRANCH (${#patches[@]} patches)"

if [[ -n $build ]]; then
	make -C "$WT" modules -j"$(nproc)"
	echo "Build of $RELEASE with the series succeeded"
fi
