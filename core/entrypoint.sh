#!/bin/bash
# nasoc 容器入口：准备数据目录后启动 sessiond（前台）
set -e

DATA=/data
mkdir -p "$DATA/opencode-config" "$DATA/opencode-data" "$DATA/home" "$DATA/bin"
# 容器内 uid 1000 无 passwd 条目，HOME 默认不可写；opencode 等工具需要可写 HOME
export HOME="$DATA/home"

# ── 存储位置判定：/data 必须是挂载卷（持久），不能落在容器内部层 ──
DATA_MNT=$(df -P "$DATA" 2>/dev/null | awk 'NR==2{print $6}')
ROOT_MNT=$(df -P / 2>/dev/null | awk 'NR==2{print $6}')
if [ "$DATA_MNT" = "$ROOT_MNT" ]; then
  echo "[nasoc] ⚠️ 警告: /data 未挂载独立卷（与容器根同一文件系统）——"
  echo "[nasoc] ⚠️ 数据在应用升级/重建时会丢失！请检查安装参数 DATA_PATH 指向 NAS 数据卷"
  echo "[nasoc] ⚠️ （建议 SSD 卷，如 /volume2/docker/nasoc；勿使用系统盘/eMMC）"
fi

# opencode 状态持久化到 /data（随应用升级/重装保留）
export XDG_CONFIG_HOME="$DATA/opencode-config"
export XDG_DATA_HOME="$DATA/opencode-data"
export XDG_CACHE_HOME="$DATA/opencode-cache"
mkdir -p "$XDG_CACHE_HOME"

# opencode 自升级：/usr/local/bin/opencode 包装脚本自动优先 /data/bin/opencode
if [ -x "$DATA/bin/opencode" ]; then
  echo "[nasoc] 使用持久层 opencode: $("$DATA/bin/opencode" --version 2>/dev/null | head -1)"
fi

# 可选出网代理 / npm 镜像：编辑宿主 <DATA_PATH>/proxy.env 后重启应用生效
if [ -f "$DATA/proxy.env" ]; then
  set -a
  . "$DATA/proxy.env"
  set +a
  echo "[nasoc] 已加载 proxy.env (HTTP_PROXY=${HTTP_PROXY:-无})"
fi
# 插件/MCP 依赖安装走国内镜像（未在 proxy.env 指定时生效）
export NPM_CONFIG_REGISTRY="${NPM_CONFIG_REGISTRY:-https://registry.npmmirror.com}"

# ── 访问口令迁出环境变量（安全修复 2026-11-02：env 明文凭据）──
# 安装参数经 compose 以 TERM_PIN 环境变量进入容器；这里把口令落到
# /data/.term_pin（0600，仅属主可读）后从环境中清除，sessiond 只读文件。
if [ -n "${TERM_PIN:-}" ]; then
  printf '%s' "$TERM_PIN" > "$DATA/.term_pin"
  chmod 600 "$DATA/.term_pin"
  unset TERM_PIN
  echo "[nasoc] 访问口令已写入 $DATA/.term_pin（0600），已从环境变量清除"
fi

# opencode.json 不存在时生成默认配置（BigModel/GLM Coding Plan 端点）
if [ ! -f "$XDG_CONFIG_HOME/opencode/opencode.json" ]; then
  mkdir -p "$XDG_CONFIG_HOME/opencode"
  cat > "$XDG_CONFIG_HOME/opencode/opencode.json" <<'EOF'
{
  "$schema": "https://opencode.ai/config.json",
  "theme": "opencode",
  "autoupdate": false,
  "provider": {
    "zhipu": {
      "npm": "@ai-sdk/openai-compatible",
      "name": "Zhipu BigModel (Coding Plan)",
      "options": {
        "baseURL": "https://open.bigmodel.cn/api/coding/paas/v4"
      },
      "models": {
        "glm-5.2": { "name": "GLM-5.2 (1M ctx)" },
        "glm-5.1": { "name": "GLM-5.1 (200K ctx)" }
      }
    }
  }
}
EOF
fi

echo "[nasoc] starting sessiond on :8080 (opencode $(opencode --version 2>/dev/null || echo 'n/a'))"

# ── 降权运行：Docker 自动创建的挂载目录属 root，容器用户 1000 不可写 ──
# 以 root 进入时先校正 /data 属主，再以 1000:10 运行 sessiond（tmux/终端同 uid）
if [ "$(id -u)" = "0" ]; then
  chown -R 1000:10 "$DATA" 2>/dev/null || true
  echo "[nasoc] 已校正 $DATA 属主（1000:10），降权运行"
  exec setpriv --reuid=1000 --regid=10 --clear-groups python3 /srv/sessiond.py
fi
exec python3 /srv/sessiond.py
