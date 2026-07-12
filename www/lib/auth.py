"""編集キーの検証・セッション（HMAC署名付きCookie）・CSRFトークン。"""
import hashlib
import hmac
import secrets
import time

from lib import config, store


def new_salt():
    return secrets.token_hex(16)


def hash_key(salt, key):
    return hashlib.sha256((salt + key).encode("utf-8")).hexdigest()


def verify_key(char, key):
    return hmac.compare_digest(char["key_hash"], hash_key(char["key_salt"], key))


def _sign(msg):
    return hmac.new(store.secret_key().encode("ascii"),
                    msg.encode("utf-8"), hashlib.sha256).hexdigest()[:40]


def cookie_name(srv, cid):
    return "pnsg_%s_%s" % (srv, cid)


def make_session(srv, cid):
    exp = int(time.time()) + config.SESSION_DAYS * 86400
    payload = "%s.%s.%d" % (srv, cid, exp)
    return payload + "." + _sign(payload)


def check_session(token, srv, cid):
    parts = (token or "").split(".")
    if len(parts) != 4:
        return False
    s, c, exp, sig = parts
    if s != srv or c != cid or not exp.isdigit():
        return False
    if not hmac.compare_digest(sig, _sign("%s.%s.%s" % (s, c, exp))):
        return False
    return int(exp) > time.time()


def verify_host(ev, pw):
    """イベントのホストパスワードを検証。未設定なら常に False。"""
    if not ev.get("host_hash"):
        return False
    return hmac.compare_digest(ev["host_hash"],
                               hash_key(ev.get("host_salt") or "", pw))


def host_cookie_name(srv, eid):
    return "pnsgh_%s_%s" % (srv, eid)


def make_host_session(srv, eid):
    exp = int(time.time()) + config.SESSION_DAYS * 86400
    payload = "host.%s.%s.%d" % (srv, eid, exp)
    return payload + "." + _sign(payload)


def check_host_session(token, srv, eid):
    parts = (token or "").split(".")
    if len(parts) != 5 or parts[0] != "host":
        return False
    _, s, e, exp, sig = parts
    if s != srv or e != eid or not exp.isdigit():
        return False
    if not hmac.compare_digest(sig, _sign("host.%s.%s.%s" % (s, e, exp))):
        return False
    return int(exp) > time.time()


def csrf_token(session_token):
    return _sign("csrf." + session_token)


def admin_csrf():
    return _sign("admin." + time.strftime("%Y%m%d"))


def check_admin_csrf(token):
    # 日付をまたいで送信されたフォームも許容するため前日分も有効とする
    now = time.time()
    for t in (now, now - 86400):
        day = time.strftime("%Y%m%d", time.localtime(t))
        if hmac.compare_digest(token or "", _sign("admin." + day)):
            return True
    return False
