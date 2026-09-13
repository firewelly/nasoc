# shellcheck shell=bash
# NasOC 新会话提示（仅交互式 shell 显示）
case $- in
  *i*) ;;
  *) return ;;
esac

if [ "$SHLVL" = "1" ] && [ -z "$OC_HINT_SHOWN" ]; then
  export OC_HINT_SHOWN=1
  echo "┌──────────────────────────────────────────────────────────┐"
  echo "│ NasOC 编程终端（内置 OpenCode）zh_CN.UTF-8               │"
  echo "│   opencode            启动 AI 编程助手 (GLM-5.2/5.1)     │"
  echo "│   vim / emacs         编辑器（中文支持已就绪）           │"
  echo "│   首次使用: opencode auth login 配置 API Key             │"
  echo "│   关闭浏览器页面会话保留；输入 exit 结束本会话           │"
  echo "└──────────────────────────────────────────────────────────┘"
fi
