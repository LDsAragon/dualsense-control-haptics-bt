#!/usr/bin/env bash
# Clona vDS en el commit fijado, le aplica vds-mods/*.patch y corre test_vds_mods.cc.
# Necesita: git, g++ (C++20), libopus-dev, zlib1g-dev, python3 con numpy.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
WORK="${1:-$(mktemp -d)}"
COMMIT="$(head -1 "$ROOT/vds-mods/VDS_COMMIT" | tr -d '[:space:]')"
SRC="$WORK/vds"
if [ ! -d "$SRC/.git" ]; then
  git -c core.autocrlf=false clone -q https://github.com/hurryman2212/vds.git "$SRC"
fi
git -C "$SRC" -c advice.detachedHead=false checkout -q --force "$COMMIT"
git -C "$SRC" reset -q --hard "$COMMIT"
git -C "$SRC" clean -q -fd
for p in "$ROOT"/vds-mods/*.patch; do
  git -C "$SRC" apply --check "$p"
  git -C "$SRC" apply "$p"
  echo "aplicado: $(basename "$p")"
done
# reportes de salida generados por dshaptics
python3 - "$WORK" "$ROOT/app" <<'PY'
import sys; sys.path.insert(0, sys.argv[2]); import dshaptics as d
w = sys.argv[1]
st = d.trigger_state(right=d.trigger_feedback(), left=d.trigger_weapon())
open(f"{w}/usb_triggers.bin", "wb").write(d.trigger_report(st, False))
open(f"{w}/usb_off.bin", "wb").write(d.trigger_report(d.trigger_state(right=d.trigger_off(), left=d.trigger_off()), False))
open(f"{w}/usb_light.bin", "wb").write(d.output_report(d.light_state((0xFF, 0x40, 0x00), 2), False))
PY
g++ -std=c++20 -O1 -I"$SRC/include" -I"$SRC/src" -I/usr/include/opus \
    "$SRC/src/vds_protocol.cc" "$ROOT/tests/vds/test_vds_mods.cc" -lopus -lz -o "$WORK/test_vds_mods"
VDS_SPEAKER_MUTE_FLAG="$WORK/speaker-muted" "$WORK/test_vds_mods" "$WORK" \
    "$WORK/usb_triggers.bin" "$WORK/usb_off.bin" "$WORK/usb_light.bin"
