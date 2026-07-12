"""POSTフォームの解析。

標準の cgi モジュールは Python 3.13 で削除されたため、
urlencoded / multipart/form-data とも自前で解析する。
"""
import re
import urllib.parse

from lib import config


class FormError(Exception):
    pass


def parse(environ):
    """ボディを解析して (fields, files) を返す。

    fields: {name: [str, ...]}
    files:  {name: [(filename, bytes), ...]}
    """
    try:
        clen = int(environ.get("CONTENT_LENGTH") or 0)
    except ValueError:
        clen = 0
    if clen > config.MAX_BODY_BYTES:
        raise FormError("送信サイズが大きすぎます（合計 %dMB まで）"
                        % (config.MAX_BODY_BYTES // 1024 // 1024))
    body = environ["wsgi.input"].read(clen) if clen else b""
    ctype = environ.get("CONTENT_TYPE", "")
    fields, files = {}, {}
    if ctype.startswith("multipart/form-data"):
        m = re.search(r'boundary="?([^";,]+)"?', ctype)
        if not m:
            raise FormError("不正なフォームデータです")
        _parse_multipart(body, m.group(1).encode("ascii"), fields, files)
    elif body:
        qs = urllib.parse.parse_qs(body.decode("utf-8", "replace"),
                                   keep_blank_values=True)
        for k, vs in qs.items():
            fields[k] = vs
    return fields, files


def _parse_multipart(body, boundary, fields, files):
    parts = body.split(b"--" + boundary)
    for part in parts[1:-1]:  # 先頭は前文、末尾は終端 "--\r\n"
        if not part.startswith(b"\r\n"):
            continue
        head, sep, data = part[2:].partition(b"\r\n\r\n")
        if not sep:
            continue
        if data.endswith(b"\r\n"):
            data = data[:-2]
        hs = head.decode("utf-8", "replace")
        m = re.search(r'Content-Disposition:[^\r\n]*?\bname="([^"]*)"', hs, re.I)
        if not m:
            continue
        name = m.group(1)
        fm = re.search(r'\bfilename="([^"]*)"', hs)
        if fm is not None:
            if fm.group(1) or data:  # ファイル未選択の空パートは無視
                files.setdefault(name, []).append((fm.group(1), data))
        else:
            fields.setdefault(name, []).append(data.decode("utf-8", "replace"))
