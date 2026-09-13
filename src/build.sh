#!/bin/bash
# ============================================================================
# nasoc 构建脚本（只在 DXP4800 NAS 上执行 —— 官方要求 Linux 打包保权限）
# 上传源码: Mac 上执行 tools/upload.sh → NAS ~/nasoc-src/
# 用法:     cd ~/nasoc-src/src && bash build.sh <build号>
# 流程:     docker build(core/) → docker save → ugcli pack
# ============================================================================
set -euo pipefail

BUILD="${1:?用法: bash build.sh <build号>}"
SRC_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SRC_DIR")"          # ~/nasoc-src/（含 core/ vendor/）
UGCLI="$HOME/bin/ugcli"
VERSION=$(grep -E '^version:' "$SRC_DIR/project.yaml" | awk '{print $2}' | tr -d '"')

echo "==> [1/4] docker build nasoc:${VERSION}（上下文=$ROOT）"
docker build -f "$ROOT/core/Dockerfile" -t "nasoc:${VERSION}" "$ROOT"

echo "==> 冒烟: opencode --version"
docker run --rm --entrypoint /usr/local/bin/opencode "nasoc:${VERSION}" --version

echo "==> [2/4] docker save → src/rootfs_amd64/images/"
mkdir -p "$SRC_DIR/rootfs_amd64/images"
rm -f "$SRC_DIR/rootfs_amd64/images/"*.tar
docker save -o "$SRC_DIR/rootfs_amd64/images/nasoc-${VERSION}-amd64.tar" \
  "nasoc:${VERSION}"
ls -lh "$SRC_DIR/rootfs_amd64/images/"

echo "==> [3/4] ugcli check"
cd "$SRC_DIR"
"$UGCLI" check

echo "==> [4/4] ugcli pack (build $BUILD)"
"$UGCLI" pack --arch amd64 --build "$BUILD"

echo "==> 完成。UPK:"
ls -lh "$SRC_DIR/build_dir/pkgs/upk/" 2>/dev/null || find "$SRC_DIR/build_dir" -name "*.upk" -exec ls -lh {} \;
