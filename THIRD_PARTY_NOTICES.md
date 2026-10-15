# 第三方组件授权声明（THIRD PARTY NOTICES）

本应用（NasOC）分发的安装包/容器镜像聚合包含以下第三方组件。各组件均以
**独立进程或独立静态文件**形式运行，不与本应用代码产生链接；所列许可均为
宽松许可（MIT / ISC / BSD 系），**无 copyleft 传染**。

## 1. OpenCode（内置 AI 编程助手）

- 来源：https://github.com/sst/opencode （npm 平台包 `opencode-linux-x64` / 元包 `opencode-ai`）
- 许可：**MIT License**，Copyright (c) 2025 opencode
- 说明：本应用以「应用内升级」机制（`update` 命令）安装其官方发布二进制，未做任何修改；
  MIT 允许再分发与自用修改，需保留版权与许可声明（随二进制/本声明保留）
- 注意："OpenCode" 名称/商标归其项目方所有；本应用显示名为 **NasOC**，仅在
  描述中说明「内置 OpenCode」

## 2. xterm.js / @xterm/addon-fit（前端终端模拟）

- 来源：https://github.com/xtermjs/xterm.js
- 许可：**MIT License**
- 许可文本副本：`core/www/vendor/xterm.LICENSE`、`core/www/vendor/fit.LICENSE`

## 3. tmux（会话持久化，容器内 apt 安装）

- 来源：Debian 12 官方仓库，上游 https://github.com/tmux/tmux
- 许可：**ISC 风格（BSD 家族，宽松）**，Copyright © Nicholas Marriott 等
- 版权声明由 Debian 包（`/usr/share/doc/tmux/copyright`）保留于镜像内

## 4. Debian 基础镜像及 apt 软件包

- 来源：`debian:12-slim`；git、bash、python3、curl、nodejs 等经 apt 安装
- 许可：多种，含 GPL-2.0/3.0、BSD、MIT、PSF-2.0 等
- 说明：均以独立进程形式运行，与本应用为聚合关系，不构成衍生作品；
  对应源码可经 Debian 官方仓库获取（https://sources.debian.org/ ）

## 5. 本应用自研部分

- `core/sessiond.py`、`core/www/*`、`core/bin/*`、`core/Dockerfile`、
  `src/*`、`tools/*` 等
- 许可：**MIT**（见根目录 `LICENSE`）
