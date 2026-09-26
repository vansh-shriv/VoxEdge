#!/usr/bin/env bash
# Fetch the header-only third-party dependencies of TFLite-Micro at the versions and MD5s pinned in
# third_party/tflite-micro/tensorflow/lite/micro/tools/make/third_party_downloads.inc, into
# third_party/tflm_deps/{flatbuffers,gemmlowp,ruy}, plus CMSIS-NN at the commit TFLM pins in
# tools/make/ext_libs/cmsis_nn_download.sh (git-ignored). Idempotent.
set -euo pipefail
cd "$(dirname "$0")/.."
DEST=third_party/tflm_deps
mkdir -p "$DEST"

fetch() {  # name url md5
  local name=$1 url=$2 md5=$3
  if [ -d "$DEST/$name" ]; then echo "$name: present"; return; fi
  local tmp; tmp=$(mktemp -d)
  curl -LsS --fail --retry 5 -o "$tmp/a.zip" "$url"
  local got; got=$(md5sum "$tmp/a.zip" | cut -d' ' -f1)
  if [ "$got" != "$md5" ]; then echo "$name: MD5 mismatch (got $got, want $md5)" >&2; exit 1; fi
  unzip -q "$tmp/a.zip" -d "$tmp/x"
  mv "$tmp"/x/* "$DEST/$name"
  rm -rf "$tmp"
  echo "$name: ok ($md5)"
}

fetch flatbuffers https://github.com/google/flatbuffers/archive/refs/tags/v25.9.23.zip 023eca1e211d64007124420cd6be29c7
fetch gemmlowp    https://github.com/google/gemmlowp/archive/719139ce755a0f31cbf1c37f7f98adcc7fc9f425.zip 7e8191b24853d75de2af87622ad293ba
fetch ruy         https://github.com/google/ruy/archive/d37128311b445e758136b8602d1bbd2a755e115d.zip abf7a91eb90d195f016ebe0be885bb6e
fetch cmsis_nn   https://github.com/ARM-software/CMSIS-NN/archive/4ab83cc3cc98fb85ed6dafb55e8ca02f1628dcae.zip c960031e7d10cf31c477fb34ef460106
