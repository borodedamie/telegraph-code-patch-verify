#!/usr/bin/env bash
# Put the adapter package and a static Linux build of the kit's executor in public/ (served by the Worker),
# check the package against the adapterbuild manifest, and write ../space/config.json for the Space.
#   KIT=~/Documents/codes/telegraph-wasm-baseline RUN=CODE_PATCH_VERIFY_r3 \
#   BASE_URL=https://cpv-adapter.<subdomain>.workers.dev bash adapter-host/prepare.sh
set -euo pipefail
KIT=${KIT:-$HOME/Documents/codes/telegraph-wasm-baseline}
RUN=${RUN:-CODE_PATCH_VERIFY_r3}
BASE_URL=${BASE_URL:-https://cpv-adapter.CHANGE-ME.workers.dev}
here=$(cd "$(dirname "$0")" && pwd)
pkg="$KIT/work/runs/$RUN/CODE_PATCH_VERIFY.safetensors"
manifest="$pkg.manifest.json"
mkdir -p "$here/public"
cp "$pkg" "$here/public/CODE_PATCH_VERIFY.safetensors"
sha=$(shasum -a 256 "$here/public/CODE_PATCH_VERIFY.safetensors" | cut -d' ' -f1)
want=$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['package']['sha256'])" "$manifest")
[ "$sha" = "$want" ] || { echo "sha256 $sha does not match the adapterbuild manifest ($want)"; exit 1; }
(cd "$KIT" && CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -trimpath -o "$here/public/adapterexec-linux-amd64" ./cmd/adapterexec)
exe=$(shasum -a 256 "$here/public/adapterexec-linux-amd64" | cut -d' ' -f1)
printf '{\n  "base_url": "%s",\n  "adapter_sha256": "%s",\n  "executor_sha256": "%s"\n}\n' \
  "$BASE_URL" "$sha" "$exe" > "$here/../space/config.json"
echo "package   sha256 $sha (matches the adapterbuild manifest)"
echo "executor  sha256 $exe (kit $(git -C "$KIT" rev-parse --short HEAD))"
echo "keccak256 $(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['keccak256'])" "$manifest")  <- wasmHash to register"
echo "wrote space/config.json with base_url $BASE_URL"
