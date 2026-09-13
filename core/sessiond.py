#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sessiond —— nasoc 的后端服务（纯标准库）。

职责：
  1. 提供 tab 管理界面与静态资源（/srv/www）
  2. 会话管理 API（tmux 会话 = 一个项目 tab）
  3. WebSocket → tmux 桥：每个 WS 连接 fork 一个 PTY 跑 `tmux new -A -s <name>`，
     浏览器断开只杀 tmux client，会话本身保留（关窗续连）；exit 结束会话；
     容器/设备重启后全部消失。

约定：
  - 会话名：[A-Za-z0-9._-]{1,40}
  - 工作目录：必须位于 /volume* 或 /home 下（compose 已按原路径挂载）
  - 可选访问口令：环境变量 TERM_PIN，非空时 WS 与写操作要求 ?pin= 或 X-OC-PIN
"""

import base64
import errno
import fcntl
import hashlib
import json
import os
import pty
import re
import select
import signal
import socket
import struct
import subprocess
import sys
import threading
import termios
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

WWW_DIR = "/srv/www"
PORT = 8080
TERM_PIN = os.environ.get("TERM_PIN", "").strip()
NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,39}$")
WS_GUID = "258EAFA5-E914-47DA-95CA-C5AB0DC85B11"

ALLOWED_ROOTS = []


def _resolve_roots():
    roots = []
    for name in os.listdir("/"):
        if re.match(r"^volume\d+$", name):
            roots.append("/" + name)
    if os.path.isdir("/home"):
        roots.append("/home")
    # 开发调试可覆盖：OC_ROOTS="/tmp:/path"（生产不受影响）
    override = [p for p in os.environ.get("OC_ROOTS", "").split(":") if p]
    return override or roots


ALLOWED_ROOTS = _resolve_roots()
PATH_RE = re.compile(
    r"^/(" + "|".join(sorted((r.strip("/") for r in ALLOWED_ROOTS),
                             reverse=True)) + r")(/|$)") if ALLOWED_ROOTS else re.compile(r"$^")


class ClientError(Exception):
    pass


# ----------------------------------------------------------------------------
# tmux 封装
# ----------------------------------------------------------------------------

def tmux(*args, timeout=10):
    """执行 tmux 命令，返回 (rc, stdout)"""
    try:
        p = subprocess.run(["tmux", *args], capture_output=True, timeout=timeout)
        return p.returncode, p.stdout.decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return 1, ""


def list_sessions():
    rc, out = tmux("list-sessions", "-F",
                   "#{session_name}\t#{session_path}\t#{session_created}\t"
                   "#{session_attached}\t#{session_windows}")
    sessions = []
    if rc == 0:
        for line in out.splitlines():
            parts = line.split("\t")
            if len(parts) >= 5:
                name, path, created, attached, windows = parts[:5]
                sessions.append({
                    "name": name,
                    "path": path,
                    "created": int(created) if created.isdigit() else 0,
                    "attached": attached not in ("0", ""),
                    "windows": int(windows) if windows.isdigit() else 1,
                })
    return sessions


def session_exists(name):
    return any(s["name"] == name for s in list_sessions())


def create_session(name, path):
    rc, out = tmux("new-session", "-d", "-s", name, "-c", path)
    if rc != 0:
        raise ClientError("tmux new-session 失败: %s" % out.strip())


def kill_session(name):
    tmux("kill-session", "-t", name)


def capture_pane(name, lines=300):
    """回放最近输出（带颜色转义），会话不存在时返回空"""
    if not session_exists(name):
        return ""
    rc, out = tmux("capture-pane", "-p", "-e", "-S", "-%d" % lines, "-t", name,
                   timeout=5)
    return out if rc == 0 else ""


def validate_name(name):
    if not NAME_RE.match(name):
        raise ClientError("会话名只能包含字母/数字/./_/-，且以字母或数字开头")
    # 避免与 tmux 目标语法冲突
    if name.startswith("."):
        raise ClientError("会话名不能以 . 开头")


def validate_path(path):
    path = os.path.realpath(path)
    if not PATH_RE.match(path):
        raise ClientError("目录必须在 %s 下" % "、".join(ALLOWED_ROOTS))
    if not os.path.isdir(path):
        raise ClientError("目录不存在: %s" % path)
    return path


def list_dirs(path):
    path = validate_path(path)
    dirs = []
    try:
        for entry in sorted(os.scandir(path), key=lambda e: e.name.lower()):
            try:
                if entry.is_dir(follow_symlinks=True) and not entry.name.startswith("."):
                    dirs.append(entry.name)
            except OSError:
                continue
    except OSError:
        pass
    return {"path": path, "dirs": dirs[:500]}


# ----------------------------------------------------------------------------
# WebSocket（RFC6455 服务端，够用实现）
# ----------------------------------------------------------------------------

class WebSocket:
    def __init__(self, sock):
        self.sock = sock
        self._send_lock = threading.Lock()
        self.closed = False

    @staticmethod
    def handshake(handler):
        key = handler.headers.get("Sec-WebSocket-Key", "")
        if not key:
            raise ClientError("缺少 Sec-WebSocket-Key")
        accept = base64.b64encode(
            hashlib.sha1((key + WS_GUID).encode()).digest()).decode()
        handler.send_response_only(101, "Switching Protocols")
        handler.send_header("Upgrade", "websocket")
        handler.send_header("Connection", "Upgrade")
        handler.send_header("Sec-WebSocket-Accept", accept)
        handler.end_headers()
        handler.wfile.flush()

    def recv_frame(self):
        """返回 (opcode, payload)；连接关闭返回 (None, b'')"""
        hdr = self._read_exact(2)
        if hdr is None:
            return None, b""
        fin = hdr[0] & 0x80
        opcode = hdr[0] & 0x0F
        masked = hdr[1] & 0x80
        length = hdr[1] & 0x7F
        if length == 126:
            ext = self._read_exact(2)
            if ext is None:
                return None, b""
            length = struct.unpack(">H", ext)[0]
        elif length == 127:
            ext = self._read_exact(8)
            if ext is None:
                return None, b""
            length = struct.unpack(">Q", ext)[0]
        mask = self._read_exact(4) if masked else b"\x00\x00\x00\x00"
        if mask is None:
            return None, b""
        payload = self._read_exact(length) if length else b""
        if payload is None:
            return None, b""
        if masked:
            payload = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        if not fin:
            # 分片：循环收后续帧
            while True:
                op2, p2 = self.recv_frame()
                if op2 is None:
                    return None, b""
                if op2 == 0:  # continuation
                    payload += p2
                    if len(payload) > 1 << 20:
                        return None, b""
                    continue
                if op2 in (8, 9):  # 控制帧可出现在分片间
                    return op2, p2
                return op2, p2  # 不规范流，直接返回
        return opcode, payload

    def _read_exact(self, n):
        data = b""
        while len(data) < n:
            try:
                chunk = self.sock.recv(n - len(data))
            except OSError:
                return None
            if not chunk:
                return None
            data += chunk
        return data

    def send_frame(self, opcode, payload):
        if self.closed:
            return False
        header = bytes([0x80 | opcode])
        n = len(payload)
        if n < 126:
            header += bytes([n])
        elif n < 1 << 16:
            header += bytes([126]) + struct.pack(">H", n)
        else:
            header += bytes([127]) + struct.pack(">Q", n)
        try:
            with self._send_lock:
                self.sock.sendall(header + payload)
            return True
        except OSError:
            self.closed = True
            return False

    def send_text(self, text):
        return self.send_frame(0x1, text.encode("utf-8"))

    def send_binary(self, data):
        return self.send_frame(0x2, data)

    def send_ping(self, data=b""):
        return self.send_frame(0x9, data)

    def close(self):
        if not self.closed:
            self.closed = True
            try:
                self.send_frame(0x8, b"")
            except Exception:
                pass
            try:
                self.sock.close()
            except Exception:
                pass


# ----------------------------------------------------------------------------
# PTY 会话桥
# ----------------------------------------------------------------------------

class PtyBridge(threading.Thread):
    """一个 WS 连接 ↔ 一个 tmux client PTY"""

    def __init__(self, ws, name, path):
        super().__init__(daemon=True)
        self.ws = ws
        self.name = name
        self.path = path
        self.master_fd = None
        self.pid = None

    def spawn(self, cols, rows):
        pid, fd = pty.fork()
        if pid == 0:  # 子进程：tmux attach-or-create
            try:
                os.environ["TERM"] = "xterm-256color"
                os.environ["COLORTERM"] = "truecolor"
                os.chdir(self.path)
                os.execvp("tmux", ["tmux", "new-session", "-A", "-s",
                                   self.name, "-c", self.path])
            except Exception:
                os._exit(127)
        self.pid, self.master_fd = pid, fd
        self.set_size(cols, rows)

    def set_size(self, cols, rows):
        if self.master_fd is None:
            return
        try:
            winsize = struct.pack("HHHH", max(rows, 2), max(cols, 2), 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
        except OSError:
            pass

    def run(self):
        stop = threading.Event()

        def pump_output():
            while not stop.is_set():
                try:
                    r, _, _ = select.select([self.master_fd], [], [], 0.5)
                except OSError:
                    break
                if self.master_fd not in r:
                    continue
                try:
                    data = os.read(self.master_fd, 65536)
                except OSError:
                    break
                if not data:
                    break
                if not self.ws.send_binary(data):
                    break
            stop.set()
            try:
                self.ws.close()
            except Exception:
                pass

        out_thread = threading.Thread(target=pump_output, daemon=True)
        out_thread.start()

        try:
            while not stop.is_set():
                opcode, payload = self.ws.recv_frame()
                if opcode is None:
                    break
                if opcode == 0x8:  # close
                    break
                if opcode == 0x9:  # ping
                    self.ws.send_frame(0xA, payload)
                    continue
                if opcode not in (0x1, 0x2):
                    continue
                if opcode == 0x1:
                    # 文本帧 = 控制消息（resize / ping）；普通键盘输入走二进制帧
                    text = payload.decode("utf-8", "replace")
                    if text.startswith('{"resize"'):
                        try:
                            msg = json.loads(text)
                            self.set_size(msg["resize"][0], msg["resize"][1])
                            continue
                        except (ValueError, KeyError, TypeError):
                            pass
                    if text.startswith('{"ping"'):
                        continue
                    continue
                try:
                    os.write(self.master_fd, payload)
                except OSError:
                    break
        except Exception:
            pass
        finally:
            stop.set()
            try:
                self.ws.close()
            except Exception:
                pass
            # 关闭 PTY：只结束 tmux client，会话保留
            if self.master_fd is not None:
                try:
                    os.close(self.master_fd)
                except OSError:
                    pass
            if self.pid:
                try:
                    os.kill(self.pid, signal.SIGHUP)
                except OSError:
                    pass
                try:
                    os.waitpid(self.pid, os.WNOHANG)
                except OSError:
                    pass
            out_thread.join(timeout=2)


# ----------------------------------------------------------------------------
# HTTP 服务
# ----------------------------------------------------------------------------

CONTENT_TYPES = {
    ".html": "text/html; charset=utf-8",
    ".js": "application/javascript; charset=utf-8",
    ".css": "text/css; charset=utf-8",
    ".png": "image/png",
    ".svg": "image/svg+xml",
    ".json": "application/json; charset=utf-8",
    ".woff2": "font/woff2",
}


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "nasoc/0.1"

    def log_message(self, fmt, *args):
        sys.stderr.write("[%s] %s\n" % (time.strftime("%H:%M:%S"), fmt % args))

    # -- 工具 --

    def check_pin(self, query=None):
        if not TERM_PIN:
            return True
        given = ""
        if query:
            given = (query.get("pin") or [""])[0]
        if not given:
            given = self.headers.get("X-OC-PIN", "")
        return given == TERM_PIN

    def send_json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, rel):
        path = os.path.realpath(os.path.join(WWW_DIR, rel))
        if not path.startswith(os.path.realpath(WWW_DIR) + os.sep) and \
                path != os.path.realpath(WWW_DIR):
            self.send_json({"error": "forbidden"}, 403)
            return
        if not os.path.isfile(path):
            self.send_json({"error": "not found"}, 404)
            return
        ctype = CONTENT_TYPES.get(os.path.splitext(path)[1], "application/octet-stream")
        size = os.path.getsize(path)
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(size))
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        if self.command != "HEAD":
            with open(path, "rb") as f:
                while True:
                    chunk = f.read(65536)
                    if not chunk:
                        break
                    self.wfile.write(chunk)

    def read_body_json(self):
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > 1 << 20:
            return {}
        raw = self.rfile.read(length)
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError:
            raise ClientError("请求体不是合法 JSON")

    # -- 路由 --

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if path == "/api/health":
                self.send_json({"ok": True, "ts": int(time.time())})
            elif path == "/api/info":
                valid = self.check_pin(query) if TERM_PIN else None
                self.send_json({"pinRequired": bool(TERM_PIN), "valid": valid})
            elif path == "/api/sessions":
                self.send_json({"sessions": list_sessions()})
            elif path == "/api/browse":
                if not self.check_pin(query):
                    self.send_json({"error": "需要访问口令"}, 401)
                    return
                target = (query.get("path") or [""])[0] or _default_root()
                self.send_json(list_dirs(target))
            elif path.startswith("/ws/"):
                self.handle_ws(path[len("/ws/"):], query)
            elif path == "/" or path == "/index.html":
                self.send_file("index.html")
            elif path == "/term.html":
                self.send_file("term.html")
            elif path.startswith("/vendor/") or path.startswith("/app/"):
                self.send_file(path.lstrip("/"))
            else:
                self.send_json({"error": "not found"}, 404)
        except ClientError as e:
            try:
                self.send_json({"error": str(e)}, 400)
            except OSError:
                pass
        except (BrokenPipeError, ConnectionResetError):
            pass

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        try:
            if parsed.path == "/api/sessions":
                if not self.check_pin(query):
                    self.send_json({"error": "需要访问口令"}, 401)
                    return
                body = self.read_body_json()
                name = str(body.get("name", "")).strip()
                path = str(body.get("path", "")).strip()
                validate_name(name)
                path = validate_path(path)
                if session_exists(name):
                    raise ClientError("会话已存在: %s" % name)
                create_session(name, path)
                self.send_json({"ok": True, "name": name, "path": path})
            else:
                self.send_json({"error": "not found"}, 404)
        except ClientError as e:
            self.send_json({"error": str(e)}, 400)

    def do_DELETE(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if parsed.path.startswith("/api/sessions/"):
            if not self.check_pin(query):
                self.send_json({"error": "需要访问口令"}, 401)
                return
            name = urllib.parse.unquote(parsed.path.rsplit("/", 1)[-1])
            validate_name(name)
            kill_session(name)
            self.send_json({"ok": True})
        else:
            self.send_json({"error": "not found"}, 404)

    # -- WebSocket --

    def handle_ws(self, encoded, query):
        if not self.check_pin(query):
            try:
                self.send_json({"error": "需要访问口令"}, 401)
            except OSError:
                pass
            return
        name = urllib.parse.unquote(encoded.split("/")[0])
        try:
            validate_name(name)
        except ClientError as e:
            self.send_json({"error": str(e)}, 400)
            return
        path = (query.get("path") or [""])[0]
        try:
            # 空 path：已有会话时 tmux 自带工作目录；新会话落到默认根
            path = validate_path(path) if path else _default_root()
        except ClientError:
            path = _default_root()

        if not hasattr(self, "connection"):
            return
        self.close_connection = True
        WebSocket.handshake(self)

        raw = self.connection  # 升级后原始 socket
        ws = WebSocket(raw)
        cols = int((query.get("cols") or ["120"])[0]) 
        rows = int((query.get("rows") or ["32"])[0])
        bridge = PtyBridge(ws, name, path)
        bridge.spawn(cols, rows)
        # 回放最近输出（新会话为空串）
        replay = capture_pane(name, lines=200)
        if replay:
            ws.send_binary(replay.encode("utf-8"))
        bridge.run()


def _default_root():
    for root in ALLOWED_ROOTS:
        if os.path.isdir(root):
            return root
    return "/"


def main():
    # 转发 SIGTERM → 优雅退出（tmux server 会随容器一起结束）
    signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
    srv = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    srv.daemon_threads = True
    print("[sessiond] listening on :%d (pin=%s)" % (PORT, "on" if TERM_PIN else "off"),
          flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
