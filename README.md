# NasOC — NAS 编程终端（内置 OpenCode）

在浏览器 / 绿联 UGOS Pro 远程 App 中打开 NAS 终端进行 AI 编程。每个 Tab 一个项目，
**关窗会话保留、重开即续**；只有 `exit` 或设备重启才结束会话。内置
[OpenCode](https://opencode.ai) AI 编程助手、vim / emacs、中文 locale。

> 已上架形态：UGOS Pro Docker 应用（`com.firewell.nasoc`），桌面图标点击即用，
> 支持 UGREENlink 远程访问。

## 功能

- **多项目多 Tab**：每个 Tab 绑定一个项目目录（tmux 会话），Tab 栏随时切换
- **会话持久**：浏览器关掉会话不死，重开自动恢复并回放最近输出
- **AI 编程**：内置 opencode（默认配置 GLM-5.2 / GLM-5.1，可自行改 provider）
- **全中文**：zh_CN.UTF-8 locale，中文输入靠浏览器输入法、渲染靠 xterm.js
- **编辑器齐全**：vim / emacs / nano，git / curl 等常用工具链
- **Web 终端**：xterm.js + WebSocket，断线自动重连

## 仓库结构

```
├── core/          # 平台无关核心：Dockerfile、sessiond.py、前端、tmux 配置
├── src/           # UGOS Pro 打包工程（project.yaml / docker-compose / build.sh）
├── tools/         # 上传、E2E 测试、免 UI 安装脚本
└── vendor/        # （不入库）构建前下载的 opencode 二进制
```

## 构建（需在 Linux/Debian 12 环境执行）

```bash
# 1. 下载 opencode 二进制（linux-x64 glibc 版）
mkdir -p vendor/bin
curl -L https://registry.npmmirror.com/opencode-linux-x64/-/opencode-linux-x64-1.18.30.tgz \
  | tar xz -C /tmp && cp /tmp/package/bin/opencode vendor/bin/opencode

# 2. 构建镜像并打包 UPK
cd src && bash build.sh 1        # 产物在 src/build_dir/pkgs/upk/
```

安装：UGOS Pro 应用中心 → 手动安装（需开发者授权），或参照
`tools/ugos_install.py`（本机 API 安装）。

## 架构

单容器 `debian:12-slim`：**tmux（会话持久化）+ opencode + sessiond**
（Python 标准库单进程：Tab 管理 UI + 会话 REST API + WebSocket↔PTY↔tmux 桥）。
会话语义：关窗=detach 保留；`exit`=结束；容器/设备重启=清空。

## 授权

MIT（见 LICENSE）。聚合组件：OpenCode（MIT）、xterm.js（MIT）、tmux（ISC）、
Debian 基础镜像（多许可）。注意 "OpenCode" 名称商标归其项目方，本应用显示名
为 NasOC。
