#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
NasOC UPK 免 UI 安装/升级（在 DXP4800 本机运行）。

逆向自 UGOS Pro 1.19 appmgr 前端（com.ugreen.appmgr www/assets/*.js）：
  1. 分片上传:  POST /ugreen/v1/app/info/upload   multipart: file/chunks/chunk
     - 最后一片响应 data.appId 确认包已解析登记
  2. 手动安装:  POST /ugreen/v1/app/inst/manual
     {"installPath": <upk绝对路径>, "id": <appId>, "as_default": false,
      "parameters": [{"key": "PATH", "value": "/volume1"}], "version": 1}
  3. 鉴权: ?token=<api_token> 查询参数（token 取自已登录客户端的会话；
     127.0.0.1 直连部分 GET 免鉴权，写操作必须带）

用法（NAS 上）:
  python3 ugos_install.py <upk绝对路径> [--token XXX] [--param KEY=VALUE]...

token 获取：Mac 上已登录的 UGREEN NAS 桌面应用，其 Local Storage
  (~/Library/Application Support/com.ugreen.desktop/Local Storage/leveldb)
  中 accessInfo.api_token 即是。或用 --token 传入。
"""
import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:9999/ugreen/v1"
CHUNK = 8 * 1024 * 1024
APP_ID = "com.firewell.nasoc"


def req(path, data=None, headers=None, token="", timeout=300, method="POST"):
    url = BASE + path + ("?token=" + urllib.parse.quote(token) if token else "")
    r = urllib.request.Request(url, data=data, method=method,
                               headers=dict(headers or {}))
    with urllib.request.urlopen(r, timeout=timeout) as resp:
        return json.loads(resp.read().decode())


def upload(upk, token):
    size = os.path.getsize(upk)
    chunks = (size + CHUNK - 1) // CHUNK
    name = os.path.basename(upk)
    print("上传 %s（%d 分片）" % (name, chunks))
    boundary = uuid_hex()
    last = None
    with open(upk, "rb") as f:
        for i in range(chunks):
            data = f.read(CHUNK)
            body = ("--%s\r\n" % boundary).encode()
            body += ('Content-Disposition: form-data; name="file"; filename="%s"\r\n'
                     % name).encode()
            body += b"Content-Type: application/octet-stream\r\n\r\n" + data + b"\r\n"
            for k, v in (("chunks", str(chunks)), ("chunk", str(i))):
                body += ("--%s\r\n" % boundary).encode()
                body += ('Content-Disposition: form-data; name="%s"\r\n\r\n%s\r\n'
                         % (k, v)).encode()
            body += ("--%s--\r\n" % boundary).encode()
            last = req("/app/info/upload", body,
                       {"Content-Type": "multipart/form-data; boundary=%s" % boundary},
                       token=token)
            if last.get("code") not in (0, 200, None):
                sys.exit("上传失败: " + json.dumps(last, ensure_ascii=False))
    info = (last or {}).get("data", {})
    print("上传完成: appId=%s version=%s" % (info.get("appId"), info.get("version", {}).get("version")))
    return info


def uuid_hex():
    import uuid
    return uuid.uuid4().hex


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("upk")
    ap.add_argument("--token", default=os.environ.get("UGNAS_TOKEN", ""))
    ap.add_argument("--param", action="append", default=[],
                    help="安装参数 KEY=VALUE，可多次")
    args = ap.parse_args()
    if not args.token:
        sys.exit("需要 --token 或 UGNAS_TOKEN（见文件头注释）")

    info = upload(args.upk, args.token)

    parameters = []
    for kv in args.param:
        k, _, v = kv.partition("=")
        parameters.append({"key": k, "value": v})

    payload = {
        "installPath": os.path.abspath(args.upk),
        "id": info.get("appId", APP_ID),
        "as_default": False,
        "parameters": parameters,
        "version": 1,
    }
    r = req("/app/inst/manual", json.dumps(payload).encode(),
            {"Content-Type": "application/json"}, token=args.token)
    print("安装请求:", json.dumps(r, ensure_ascii=False)[:200])
    if r.get("code") not in (0, 200, None):
        sys.exit(1)
    print("已受理。容器就绪后访问 http://<NAS>:12703（约 1-3 分钟）")


if __name__ == "__main__":
    main()
