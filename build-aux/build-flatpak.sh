#!/usr/bin/env bash
# Baut easyShell als Flatpak – ohne etwas ins (immutable) System zu installieren.
# Alles landet in der Benutzer-Installation (--user).
#
#   ./build-aux/build-flatpak.sh            # bauen und Bundle dist/easyshell.flatpak erzeugen
#   ./build-aux/build-flatpak.sh --install  # zusätzlich direkt installieren
set -euo pipefail

APP_ID=io.github.premaxim.EasyShell
GNOME=51
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# Aus einer Distrobox/Toolbox heraus laufen flatpak-Befehle auf dem Host.
if [ -f /run/.containerenv ] || [ -f /run/.toolboxenv ]; then
  if command -v distrobox-host-exec >/dev/null && ! command -v flatpak-builder >/dev/null; then
    HOST="distrobox-host-exec"
  elif command -v flatpak-spawn >/dev/null; then
    HOST="flatpak-spawn --host"
  fi
fi
HOST=${HOST:-}

run() { $HOST "$@"; }

run flatpak remote-add --user --if-not-exists flathub https://dl.flathub.org/repo/flathub.flatpakrepo

if run sh -c 'command -v flatpak-builder' >/dev/null 2>&1; then
  BUILDER=(flatpak-builder)
else
  echo "flatpak-builder fehlt – nutze org.flatpak.Builder aus Flathub."
  run flatpak install --user -y --noninteractive flathub org.flatpak.Builder
  BUILDER=(flatpak run org.flatpak.Builder)
fi

run flatpak install --user -y --noninteractive flathub "org.gnome.Platform//$GNOME" "org.gnome.Sdk//$GNOME"

run "${BUILDER[@]}" --user --force-clean --repo=repo --state-dir=.flatpak-builder build-dir "$APP_ID.json"

mkdir -p dist
run flatpak build-bundle repo dist/easyshell.flatpak "$APP_ID" --runtime-repo=https://dl.flathub.org/repo/flathub.flatpakrepo
echo "Bundle: dist/easyshell.flatpak"

if [ "${1:-}" = "--install" ]; then
  run flatpak install --user -y --reinstall dist/easyshell.flatpak
  echo "Installiert. Start: flatpak run $APP_ID"
fi
