# nasoc: UGOS Pro / fnOS 通用编程终端镜像
# 构建上下文 = 仓库根目录（含 core/ 与 vendor/），在 DXP4800 上构建：
#   docker build -f core/Dockerfile -t nasoc:<ver> .
# 国内镜像源默认中科大，换清华: --build-arg APT_MIRROR=mirrors.tuna.tsinghua.edu.cn
ARG APT_MIRROR=mirrors.ustc.edu.cn
FROM debian:12-slim

ARG APT_MIRROR

# 中文支持：locales 生成 zh_CN.UTF-8（vim/emacs/less 等的编码与本地化行为）
# 编辑器：vim（完整版）+ emacs-nox（纯终端版，无 X 依赖）
# nodejs/npm：opencode MCP 服务器（npx）运行时需要
# 中文字体不需要装 —— 渲染在浏览器端（xterm.js）；中文输入走浏览器输入法，
# 经 WebSocket 传 UTF-8 字节，服务端只保证 locale 正确。
RUN sed -i "s|deb.debian.org|${APT_MIRROR}|g" /etc/apt/sources.list.d/debian.sources \
    && apt-get update && apt-get install -y --no-install-recommends \
        tmux python3 git curl ca-certificates procps less vim nano \
        emacs-nox man-db bash-completion lsof locales nodejs npm \
    && sed -i 's/^# *\(zh_CN.UTF-8 UTF-8\)\s*$/\1/' /etc/locale.gen \
    && locale-gen \
    && rm -rf /var/lib/apt/lists/*

# opencode 1.18.30（linux-x64 glibc 版，与 Debian 12 兼容）
COPY vendor/bin/opencode /usr/local/bin/opencode
RUN chmod 0755 /usr/local/bin/opencode

# sessiond（tab UI + 会话 API + WebSocket→tmux 桥）与前端
COPY core/sessiond.py /srv/sessiond.py
COPY core/www /srv/www

# 环境配置
COPY core/tmux.conf /etc/tmux.conf
COPY core/vimrc.local /etc/vim/vimrc.local
COPY core/profile.d/10-opencode-hint.sh /etc/profile.d/10-opencode-hint.sh
COPY core/entrypoint.sh /entrypoint.sh
RUN chmod 0755 /entrypoint.sh /etc/profile.d/10-opencode-hint.sh \
    && chmod 0644 /etc/tmux.conf /etc/vim/vimrc.local /srv/sessiond.py \
    && mkdir -p /data

ENV LANG=zh_CN.UTF-8 \
    LC_CTYPE=zh_CN.UTF-8 \
    TERM=xterm-256color

EXPOSE 8080

ENTRYPOINT ["/entrypoint.sh"]
