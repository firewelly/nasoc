#!/bin/bash
# nasoc 容器入口：准备数据目录后启动 sessiond（前台）
set -e

DATA=/data
mkdir -p "$DATA/opencode-config" "$DATA/opencode-data" "$DATA/home"
# 容器内 uid 1000 无 passwd 条目，HOME 默认不可写；opencode 等工具需要可写 HOME
export HOME="$DATA/home"

# opencode 状态持久化到 /data（随应用升级/重装保留）
export XDG_CONFIG_HOME="$DATA/opencode-config"
export XDG_DATA_HOME="$DATA/opencode-data"
export XDG_CACHE_HOME="$DATA/opencode-cache"
mkdir -p "$XDG_CACHE_HOME"

# 可选出网代理 / npm 镜像：编辑宿主 /volume2/docker/nasoc/proxy.env 后重启应用生效
if [ -f "$DATA/proxy.env" ]; then
  set -a
  . "$DATA/proxy.env"
  set +a
  echo "[nasoc] 已加载 proxy.env (HTTP_PROXY=${HTTP_PROXY:-无})"
fi
# 插件/MCP 依赖安装走国内镜像（未在 proxy.env 指定时生效）
export NPM_CONFIG_REGISTRY="${NPM_CONFIG_REGISTRY:-https://registry.npmmirror.com}"

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
exec python3 /srv/sessiond.py
