# Shared helpers for the tools, sourced by the scripts in this directory.

set -euo pipefail

TOP=$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)
DRIVER="$TOP/driver"

die() {
	echo "${0##*/}: $*" >&2
	exit 1
}

# The current release is defined by the submodule branch ogkm/<release>.
BRANCH=$(git -C "$TOP" config -f .gitmodules submodule.driver.branch) ||
	die "no branch configured for submodule driver in .gitmodules"
[[ $BRANCH == ogkm/* ]] || die "submodule branch '$BRANCH' does not start with ogkm/"
RELEASE=${BRANCH#ogkm/}

# Refuse to work on anything but the current release.
check_release() {
	if [[ -n ${1-} && $1 != "$RELEASE" ]]; then
		die "only the current release $RELEASE is maintained, not $1"
	fi
}

# The driver checkout must be on the release branch, clean, and based on the
# upstream tag of the same name.
check_driver() {
	[[ -e $DRIVER/.git ]] || die "driver/ is not checked out (git submodule update --init driver)"
	local head
	head=$(git -C "$DRIVER" symbolic-ref --short -q HEAD) || die "driver/ has a detached HEAD, check out $BRANCH"
	[[ $head == "$BRANCH" ]] || die "driver/ is on $head, expected $BRANCH"
	git -C "$DRIVER" diff --quiet HEAD -- || die "driver/ has uncommitted changes"
	git -C "$DRIVER" rev-parse -q --verify "refs/tags/$RELEASE^{commit}" >/dev/null ||
		die "upstream tag $RELEASE is missing in driver/ (git -C driver fetch upstream tag $RELEASE)"
	git -C "$DRIVER" merge-base --is-ancestor "refs/tags/$RELEASE" HEAD ||
		die "$BRANCH is not based on the upstream tag $RELEASE"
}
