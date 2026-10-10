#!/usr/bin/env bash
# Preview tap bootstrap. Never changes a dirty tap or replaces a different remote.
set -euo pipefail

if ! command -v brew >/dev/null || ! command -v git >/dev/null; then
  echo "Install Homebrew and Git first, then run this installer again." >&2
  exit 1
fi
brew tap devesh36/pulse https://github.com/Devesh36/Pulse.git
pulse_tap_root="$(brew --repository devesh36/pulse)"
pulse_tap_remote="$(git -C "$pulse_tap_root" remote get-url origin)"
case "$pulse_tap_remote" in
  https://github.com/Devesh36/Pulse|https://github.com/Devesh36/Pulse.git) ;;
  *) echo "The existing tap points to another repository; it was left unchanged." >&2; exit 1 ;;
esac
if [ -n "$(git -C "$pulse_tap_root" status --porcelain)" ]; then
  echo "The existing tap has local changes; preserve them before installing Pulse." >&2
  exit 1
fi
git -C "$pulse_tap_root" fetch origin main:refs/remotes/origin/main
git -C "$pulse_tap_root" switch --detach refs/remotes/origin/main
# Keep auto-update from changing the selected checkout mid-install.
HOMEBREW_NO_AUTO_UPDATE=1 brew install --HEAD devesh36/pulse/pulse
echo "Pulse installed. Run: pulse repl"
