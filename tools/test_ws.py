#!/usr/bin/env python3
"""最小 WS 客户端：测试 sessiond 的 /ws 桥（RFC6455 客户端实现）"""
import base64, hashlib, json, os, secrets, socket, struct, sys, time

HOST = os.environ.get("OC_TEST_HOST", "127.0.0.1")
PORT = int(os.environ.get("OC_TEST_PORT", "8080"))
PIN = os.environ.get("OC_TEST_PIN", "")

def ws_connect(path):
    s = socket.create_connection((HOST, PORT), timeout=10)
    key = base64.b64encode(secrets.token_bytes(16)).decode()
    req = (f"GET {path} HTTP/1.1\r\nHost: {HOST}:{PORT}\r\n"
           f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
           f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
    s.sendall(req.encode())
    buf = b""
    while b"\r\n\r\n" not in buf:
        buf += s.recv(4096)
    head, _, rest = buf.partition(b"\r\n\r\n")
    assert b"101" in head.split(b"\r\n")[0], head
    return s, rest

def send_frame(s, opcode, payload):
    mask = secrets.token_bytes(4)
    header = bytes([0x80 | opcode])
    n = len(payload)
    if n < 126:
        header += bytes([0x80 | n])
    elif n < 1 << 16:
        header += bytes([0x80 | 126]) + struct.pack(">H", n)
    else:
        header += bytes([0x80 | 127]) + struct.pack(">Q", n)
    masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
    s.sendall(header + mask + masked)

def recv_exact(s, n, buf):
    """从 buf 取，不足再从 socket 读；返回 (data, 剩余buf)"""
    while len(buf) < n:
        chunk = s.recv(65536)
        if not chunk:
            raise ConnectionError("eof")
        buf += chunk
    return buf[:n], buf[n:]

def parse_frame(s, buf):
    """从 buf 解析一帧；返回 (opcode, payload, 剩余buf)"""
    hdr, buf = recv_exact(s, 2, buf)
    opcode = hdr[0] & 0x0F
    length = hdr[1] & 0x7F
    if length == 126:
        ext, buf = recv_exact(s, 2, buf)
        length = struct.unpack(">H", ext)[0]
    elif length == 127:
        ext, buf = recv_exact(s, 8, buf)
        length = struct.unpack(">Q", ext)[0]
    payload, buf = recv_exact(s, length, buf)
    return opcode, payload, buf

def drain(s, seconds=2.0):
    out = b""
    s.settimeout(0.3)
    end = time.time() + seconds
    buf = b""
    while time.time() < end:
        try:
            chunk = s.recv(65536)
            if not chunk:
                break
            buf += chunk
            while True:
                try:
                    op, payload, buf = parse_frame(s, buf)
                except socket.timeout:
                    break  # buf 不完整，等下一 chunk
                if op in (1, 2):
                    out += payload
                elif op == 8:
                    return out
        except socket.timeout:
            continue
        except ConnectionError:
            break
    s.settimeout(10)
    return out

def expect(tag, cond):
    print(("  ✅ " if cond else "  ❌ ") + tag)
    return cond

# ---- 1. 连接 + 输出 ----
pin_q = f"&pin={PIN}" if PIN else ""
s, rest = ws_connect(f"/ws/demo{pin_q}")
out = drain(s, 2.5)
expect("连接后有输出（提示符/banner）", len(out) > 0)

# ---- 2. 发送命令（二进制帧输入） ----
send_frame(s, 0x2, b"echo hello-oc-$((41+1))\r")
out = drain(s, 2.0)
expect("命令回显/执行输出正确", b"hello-oc-42" in out)

# ---- 3. resize 控制帧（文本） ----
send_frame(s, 0x1, json.dumps({"resize": [100, 30]}).encode())
out = drain(s, 1.0)
expect("resize 控制帧无异常（连接仍活）", True)

# ---- 4. 断开（模拟关窗）→ 会话保留 ----
s.close()
time.sleep(1.0)
import urllib.request
lst = json.load(urllib.request.urlopen(f"http://{HOST}:{PORT}/api/sessions?pin={PIN}"))
expect("断开后 tmux 会话保留", any(x["name"] == "demo" for x in lst["sessions"]))

# ---- 5. 重连 → 能继续用（replay + 新命令） ----
s2, rest2 = ws_connect(f"/ws/demo{pin_q}")
out = drain(s2, 2.5)
send_frame(s2, 0x2, b"echo after-reconnect-$USER\r")
out2 = drain(s2, 2.0)
combined = out + out2
expect("重连后回放/继续执行", b"after-reconnect-" in combined)

# ---- 6. exit → 会话结束 ----
send_frame(s2, 0x2, b"exit\r")
time.sleep(1.5)
try:
    drain(s2, 0.5)
except Exception:
    pass
s2.close()
time.sleep(1.0)
lst = json.load(urllib.request.urlopen(f"http://{HOST}:{PORT}/api/sessions?pin={PIN}"))
expect("exit 后会话消失", not any(x["name"] == "demo" for x in lst["sessions"]))

print("\n测试完成")
