#!/bin/bash
# ============================================================================
# 上传源码到 DXP4800（Mac 上执行；NAS 的 SFTP 残缺，全程走 SSH exec + 流）
# 只传源码，构建/打包全部在 NAS 上进行。
# 用法: bash upload.sh
# ============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"                       # ugos_opencode/
DEST_HOST="${OC_HOST:-dxp4800}"
DEST_DIR='${HOME}/nasoc-src'
PASS="${DXP4800_PASS:?需要 DXP4800_PASS 环境变量（SSH 密码）}"

run_ssh() { sshpass -p "$PASS" ssh "$DEST_HOST" "$@"; }

echo "==> 打包 core/ + src/（tar 流，排除垃圾文件）"
cd "$ROOT"
tar czf /tmp/oc-src.tgz --exclude='.DS_Store' --exclude='._*' \
        --exclude='__pycache__' --exclude='build_dir' \
        core src

echo "==> 传输源码 → $DEST_HOST:nasoc-src/"
run_ssh "mkdir -p nasoc-src"
cat /tmp/oc-src.tgz | run_ssh "cat > nasoc-src/src.tgz"
run_ssh "cd nasoc-src && rm -rf core src && tar xzf src.tgz && rm src.tgz"

echo "==> 传输 opencode 二进制（~176MB gzip 流）"
gzip -c vendor/bin/opencode | run_ssh "cat > nasoc-src/opencode.gz"
run_ssh "mkdir -p nasoc-src/vendor/bin && \
         gunzip -f nasoc-src/opencode.gz && \
         mv nasoc-src/opencode nasoc-src/vendor/bin/opencode && \
         chmod 0755 nasoc-src/vendor/bin/opencode"

echo "==> md5 校验"
LOCAL_MD5=$(md5 -q vendor/bin/opencode)
REMOTE_MD5=$(run_ssh "md5sum nasoc-src/vendor/bin/opencode | awk '{print \$1}'")
echo "  local : $LOCAL_MD5"
echo "  remote: $REMOTE_MD5"
[ "$LOCAL_MD5" = "$REMOTE_MD5" ] || { echo "❌ md5 不一致"; exit 1; }

echo "==> 上传完成。下一步（SSH 到 NAS）："
echo "    cd ~/nasoc-src/src && bash build.sh <build号>"
