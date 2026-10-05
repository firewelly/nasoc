# NasOC — NAS 编程终端（内置 OpenCode）

在浏览器 / 绿联 UGOS Pro 远程 App 中打开 NAS 终端做开发。每个 Tab 一个项目，
**关窗会话保留、重开即续**；`exit` 或重启设备才结束。内置
[OpenCode](https://github.com/sst/opencode)（MIT 开源）AI 编程助手、
vim / emacs、中文环境。**opencode 支持应用内一键升级，不用重装本应用。**

> 已上架形态：UGOS Pro Docker 应用（`com.firewell.nasoc`），桌面图标点击即用，
> 支持 UGREENlink 远程访问。

## 背景与动机

平时偶尔想用 iPad 或临时写点代码，手边没有趁手的终端环境，很不方便。
于是用自己的 NAS（绿联 DXP4800 / UGOS Pro）搭了一个**简单、随手可用的开发环境**，
做轻量开发工作。

也用过一些体验不错的 AI 编程工具（比如 ZCode），但主流形态往往要求使用
**非开源客户端 / 云端服务**——代码、密钥都要交到第三方手里，安全性上始终有顾虑。
[OpenCode](https://github.com/sst/opencode) 是 **MIT 开源的**，可以完全自托管，
于是基于它重新构建了这套 NasOC：**所有数据（代码、凭据、会话）都留在自己的 NAS 里**，
API Key 由自己掌控。

> 适用场景：轻量开发、iPad 随手改代码、把 AI 编程能力装进自家 NAS。
> 不适合：重负载 CI/CD。

## 功能

- **应用内升级 opencode**：终端输入 `update`（或点页面右上角「⬆ 升级 opencode」
  按钮）即升级到最新版并同步插件依赖——**无需重新打包/安装 NasOC 整包**
- **多项目多 Tab**：每个 Tab 绑定一个项目目录（tmux 会话），Tab 栏随时切换
- **会话持久**：浏览器关掉会话不死，重开自动恢复并回放最近输出
- **AI 编程**：内置 OpenCode，模型服务商由你自配（如智谱 BigModel / 百炼 /
  DeepSeek），API Key 存在 NAS 本地
- **全中文**：zh_CN.UTF-8 locale，中文输入靠浏览器输入法、渲染靠 xterm.js
- **编辑器齐全**：vim / emacs / nano，git / curl / nodejs 等常用工具链
- **Web 终端**：xterm.js + WebSocket，断线自动重连；支持 UGREENlink 远程访问
- **隐私优先**：无开发者侧服务器，不收集任何数据（见 `PRIVACY.md`）

## 使用手册

### 安装（UGOS Pro）

1. 应用中心 → 设置 → 应用开发设置 → **手动安装**，选择 `.upk` 安装包
   （需开发者设备授权；或参考 `tools/ugos_install.py` 免 UI 安装）
2. 安装时填写两个参数：
   - **项目目录（PATH）**：你的代码目录，如 `/volume1/projects`
   - **数据目录（DATA_PATH）**：建议 **SSD 卷**所在路径，如
     `/volume2/docker/nasoc`；请勿使用系统盘 / eMMC
3. 安装完成后点桌面图标打开，或直接访问 `http://<NAS-IP>:12703`

### 日常使用

- **新建项目**：点 `＋` → 填 Tab 名称 → 在目录浏览器里选项目目录 → 创建
- **切换项目**：点 Tab 栏；**关闭 Tab = 断开会话（不杀进程）**，重开自动恢复
- **结束会话**：在终端里输入 `exit`（或在 Tab 上右键 → 结束会话）
- **恢复**：关浏览器、换设备、用 iPad 再打开，原来的会话都在

### 升级 opencode

```bash
update              # 升级到最新版（并同步插件依赖）
update 1.18.30      # 安装指定版本（回滚用）
```

或点页面右上角「⬆ 升级 opencode」按钮。新二进制存于
`<DATA_PATH>/bin/`，**升级 NasOC 整包不会丢**；正在运行的会话不受影响，
新开会话即用新版。

### 首次配置 AI 模型

在终端里运行 `opencode auth login` 按提示选服务商并粘贴 API Key；
或直接编辑 `<DATA_PATH>/opencode-config/opencode/opencode.json`
（支持任意 OpenAI 兼容 / Anthropic 兼容端点）。

### 常见问题

- **打不开 / 连不上**：确认端口 12703 未被占用；UGREENlink 远程访问需在
  绿联 App 内打开本应用
- **opencode 升级失败**：检查网络；脚本默认直连国内 npm 镜像，如需代理可配置
  `<DATA_PATH>/proxy.env` 后重启应用
- **数据会不会丢**：opencode 配置/凭据在 `DATA_PATH`（持久卷）；终端会话在
  容器内，设备重启会清空（符合预期：`exit`/重启才结束会话）

## 仓库结构

```
├── core/          # 平台无关核心：Dockerfile、sessiond.py、前端、update 脚本、tmux 配置
├── src/           # UGOS Pro 打包工程（project.yaml / docker-compose / build.sh）
├── tools/         # 上传、E2E 测试、免 UI 安装脚本
└── vendor/        # （不入库）构建前下载的 opencode 二进制
```

## 构建（需在 Linux / Debian 12 环境执行）

```bash
# 1. 下载 opencode 二进制（linux-x64 glibc 版）
mkdir -p vendor/bin
curl -L https://registry.npmmirror.com/opencode-linux-x64/-/opencode-linux-x64-1.18.34.tgz \
  | tar xz -C /tmp && cp /tmp/package/bin/opencode vendor/bin/opencode

# 2. 构建镜像并打包 UPK
cd src && bash build.sh 1        # 产物在 src/build_dir/pkgs/upk/
```

## 存储策略（勿落 eMMC）

- 安装参数 **DATA_PATH**（必填）：opencode 配置/凭据与应用状态的持久目录。
  **建议 SSD 卷**（如 `/volume2/docker/nasoc`），请勿选系统盘/eMMC；可选其他
  数据卷或自定义路径（建议独立子目录）。
- 容器入口会**自检**：若 /data 未挂载独立卷（与容器根同一文件系统）会打印警告，
  避免"数据落在临时层、升级即丢"。
- opencode 自升级的二进制存于 `<DATA_PATH>/bin/`（持久层），随应用升级保留。

## 授权

- 本应用自研代码：**MIT**（见 [LICENSE](LICENSE)）
- 聚合组件：OpenCode（MIT）、xterm.js / addon-fit（MIT）、tmux（ISC）、
  Debian 基础镜像（多许可）——均为独立进程/文件聚合，**无 copyleft 传染**，
  详见 [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)
- 隐私政策：[PRIVACY.md](PRIVACY.md)（无服务器、不收集数据）
- 商标说明："OpenCode" 名称归其项目方；本应用名为 **NasOC**
