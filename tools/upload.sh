#!/bin/bash
# ============================================================================
# 上传源码到 DXP4800（Mac 上执行；NAS 的 SFTP 残缺，全程走 SSH exec + 流）
# 只传源码，构建/打包全部在 NAS 上进行。
# 用法: bash upload.sh
# ============================================================================
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$HERE")"                       # ugos_opencode/
# 目标机：OC_HOST（ssh 别名或 IP），默认 dxp4800；也可指向 eq14 等备用打包机
DEST_HOST="${OC_HOST:-dxp4800}"
DEST_DIR='${HOME}/nasoc-src'
PASS="${OC_PASS:-${DXP4800_PASS:?需要 OC_PASS（或 DXP4800_PASS）环境变量（SSH 密码）}}"

run_ssh() { sshpass -p "$PASS" ssh "$DEST_HOST" "$@"; }

echo "==> 打包 core/ + src/（tar 流，排除垃圾文件）"
cd "$ROOT"
# COPYFILE_DISABLE=1 防 macOS bsdtar 把 AppleDouble(._*) 打进包（会污染 rootfs_common，
# 导致 ugcli check 失败——--exclude='._*' 按全路径匹配不可靠，远端仍需兜底删除）
COPYFILE_DISABLE=1 tar czf /tmp/oc-src.tgz --exclude='.DS_Store' \
        --exclude='__pycache__' --exclude='build_dir' \
        core src

echo "==> 传输源码 → $DEST_HOST:nasoc-src/"
run_ssh "mkdir -p nasoc-src"
cat /tmp/oc-src.tgz | run_ssh "cat > nasoc-src/src.tgz"
run_ssh "cd nasoc-src && rm -rf core src && tar xzf src.tgz && rm src.tgz && \
         find . -name '._*' -delete 2>/dev/null; true"

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
