"""WSGIベースの極小フレームワーク。

CGI（index.cgi / admin.cgi）からも開発サーバー（devserver.py）からも
同じアプリケーションを動かすための共通層。
"""
import re
import sys
import traceback
import urllib.parse
from http.cookies import SimpleCookie

from lib import config, formdata, tpl


class Request:
    def __init__(self, environ):
        self.environ = environ
        self.method = environ.get("REQUEST_METHOD", "GET")
        self.path = environ.get("PATH_INFO") or "/"
        self.query = urllib.parse.parse_qs(environ.get("QUERY_STRING", ""),
                                           keep_blank_values=True)
        self.cookies = SimpleCookie(environ.get("HTTP_COOKIE", ""))
        self._form = None

    def q(self, name, default=""):
        return self.query.get(name, [default])[0]

    def form(self):
        if self._form is None:
            self._form = formdata.parse(self.environ)
        return self._form

    def field(self, name, default=""):
        fields, _ = self.form()
        return fields.get(name, [default])[0].strip()

    def fieldlist(self, name):
        fields, _ = self.form()
        return fields.get(name, [])

    def file(self, name):
        """選択されたファイルの (filename, bytes) を返す。未選択なら None。"""
        _, files = self.form()
        for fn, data in files.get(name, []):
            if fn and data:
                return fn, data
        return None

    def cookie(self, name):
        m = self.cookies.get(name)
        return m.value if m else None


class Response:
    def __init__(self, body=b"", status="200 OK",
                 ctype="text/html; charset=utf-8"):
        if isinstance(body, str):
            body = body.encode("utf-8")
        self.body = body
        self.status = status
        self.headers = [("Content-Type", ctype)]

    def set_cookie(self, name, value, max_age):
        path = config.BASE or "/"
        self.headers.append(
            ("Set-Cookie", "%s=%s; Path=%s; Max-Age=%d; HttpOnly; SameSite=Lax"
             % (name, value, path, max_age)))
        return self


def html_page(title, body, back=None, status="200 OK", wide=False):
    return Response(tpl.page(title, body, back=back, wide=wide), status=status)


def redirect(path):
    r = Response(b"", status="303 See Other")
    r.headers = [("Location", config.BASE + path)]
    return r


def not_found(msg="ページが見つかりません"):
    return html_page("Not Found", "<p>%s</p>" % tpl.h(msg),
                     status="404 Not Found")


def make_app(routes):
    compiled = [(m, re.compile(p), f) for m, p, f in routes]

    def app(environ, start_response):
        req = Request(environ)
        try:
            resp = None
            for method, pat, fn in compiled:
                m = pat.fullmatch(req.path)
                if m and req.method == method:
                    resp = fn(req, *m.groups())
                    break
            if resp is None:
                resp = not_found()
        except formdata.FormError as e:
            resp = html_page("エラー", "<p>%s</p>" % tpl.h(str(e)),
                             status="413 Content Too Large")
        except Exception:
            traceback.print_exc(file=sys.stderr)
            resp = html_page("エラー", "<p>内部エラーが発生しました。</p>",
                             status="500 Internal Server Error")
        headers = resp.headers
        if environ.get("wsgi.url_scheme") == "https":
            # https配信時のみCookieにSecureを付ける（ローカルhttp開発に影響しない）
            headers = [(k, v + "; Secure") if k == "Set-Cookie" else (k, v)
                       for k, v in headers]
        start_response(resp.status, headers)
        return [resp.body]

    return app
