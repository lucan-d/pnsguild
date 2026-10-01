"""JSONテキストファイルによる永続化。データベースは使わない。

書き込みは一時ファイル + os.replace のアトミック置換。
複数リクエストの競合は lock()（flock）で防ぐ。
"""
import fcntl
import json
import os
import secrets
import string
from contextlib import contextmanager

from lib import config

_ID_CHARS = string.ascii_lowercase + string.digits


def _read_json(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return default


def _write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)
    os.replace(tmp, path)


@contextmanager
def lock(name="global"):
    """書き込みを伴う一連の処理を包む排他ロック。"""
    os.makedirs(config.DATA_DIR, exist_ok=True)
    path = os.path.join(config.DATA_DIR, ".lock_" + name)
    with open(path, "a+") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def secret_key():
    """Cookie署名用の秘密鍵。初回に自動生成して data 直下に保存。"""
    path = os.path.join(config.DATA_DIR, "secret.txt")
    try:
        with open(path, encoding="ascii") as f:
            s = f.read().strip()
        if s:
            return s
    except FileNotFoundError:
        pass
    with lock():
        try:
            with open(path, encoding="ascii") as f:
                s = f.read().strip()
            if s:
                return s
        except FileNotFoundError:
            pass
        s = secrets.token_hex(32)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as f:
            f.write(s + "\n")
    return s


def _new_id(exists):
    while True:
        i = "".join(secrets.choice(_ID_CHARS) for _ in range(8))
        if not exists(i):
            return i


# ---------- サーバー（数字4桁のグループ） ----------

def _servers_path():
    return os.path.join(config.DATA_DIR, "servers.json")


def load_servers():
    return _read_json(_servers_path(), {})


def save_servers(d):
    _write_json(_servers_path(), d)


def server_exists(srv):
    return srv in load_servers()


# ---------- キャラクター ----------

def _char_dir(srv):
    return os.path.join(config.DATA_DIR, srv, "characters")


def _char_path(srv, cid):
    return os.path.join(_char_dir(srv), cid + ".json")


def get_character(srv, cid):
    return _read_json(_char_path(srv, cid), None)


def save_character(srv, char):
    _write_json(_char_path(srv, char["id"]), char)


def delete_character(srv, cid):
    try:
        os.remove(_char_path(srv, cid))
    except FileNotFoundError:
        pass


def list_characters(srv):
    chars = []
    d = _char_dir(srv)
    try:
        names = os.listdir(d)
    except FileNotFoundError:
        return chars
    for fn in names:
        if fn.endswith(".json"):
            c = _read_json(os.path.join(d, fn), None)
            if c:
                chars.append(c)
    chars.sort(key=lambda c: (c.get("guild") == config.ARCHIVED_GUILD,
                              c.get("guild") or "", c.get("name") or ""))
    return chars


def new_char_id(srv):
    return _new_id(lambda i: os.path.exists(_char_path(srv, i)))


# ---------- イベント ----------

def _event_dir(srv):
    return os.path.join(config.DATA_DIR, srv, "events")


def _event_path(srv, eid):
    return os.path.join(_event_dir(srv), eid + ".json")


def get_event(srv, eid):
    return _read_json(_event_path(srv, eid), None)


def save_event(srv, ev):
    _write_json(_event_path(srv, ev["id"]), ev)


def delete_event(srv, eid):
    try:
        os.remove(_event_path(srv, eid))
    except FileNotFoundError:
        pass


def list_events(srv):
    evs = []
    d = _event_dir(srv)
    try:
        names = os.listdir(d)
    except FileNotFoundError:
        return evs
    for fn in names:
        if fn.endswith(".json"):
            e = _read_json(os.path.join(d, fn), None)
            if e:
                evs.append(e)
    evs.sort(key=lambda e: e.get("created") or "", reverse=True)
    return evs


def new_event_id(srv):
    return _new_id(lambda i: os.path.exists(_event_path(srv, i)))
