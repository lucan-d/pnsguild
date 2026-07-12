#!/usr/bin/env python3
"""ローカル開発用サーバー。Apache + CGI の代わりに同じWSGIアプリを動かす。

使い方:  python3 devserver.py [ポート番号]   （既定 8080）
一般側:  http://127.0.0.1:8080/
管理側:  http://127.0.0.1:8080/admin/  （Basic認証はローカルでは省略）
"""
import mimetypes
import os
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
WWW = os.path.join(ROOT, "www")
sys.path.insert(0, WWW)

from wsgiref.simple_server import make_server

from lib.app import admin_app, public_app


def static_file(path, start_response):
    full = os.path.normpath(os.path.join(WWW, path.lstrip("/")))
    if not full.startswith(WWW + os.sep) or not os.path.isfile(full):
        start_response("404 Not Found",
                       [("Content-Type", "text/plain; charset=utf-8")])
        return [b"not found"]
    ctype = mimetypes.guess_type(full)[0] or "application/octet-stream"
    with open(full, "rb") as f:
        data = f.read()
    start_response("200 OK", [("Content-Type", ctype),
                              ("Content-Length", str(len(data)))])
    return [data]


def app(environ, start_response):
    path = environ.get("PATH_INFO", "")
    if path.startswith("/static/") or path.startswith("/img/"):
        return static_file(path, start_response)
    if path == "/admin" or path.startswith("/admin/"):
        # 本番では admin/.htaccess の rewrite が /admin を剥がすのと同じ扱い
        environ["PATH_INFO"] = path[len("/admin"):] or "/"
        return admin_app(environ, start_response)
    return public_app(environ, start_response)


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8080
    with make_server("127.0.0.1", port, app) as srv:
        print("一般側: http://127.0.0.1:%d/" % port)
        print("管理側: http://127.0.0.1:%d/admin/" % port)
        srv.serve_forever()


if __name__ == "__main__":
    main()
