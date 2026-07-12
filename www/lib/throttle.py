"""認証失敗の試行回数制限。

対象（キャラクター＝編集キー／イベント＝ホストパスワード）ごとに、
直近 AUTH_LOCK_SECS 秒間の失敗が AUTH_MAX_FAILS 回に達するとロックする。
ロック中は正しいキーでも受け付けない（先に locked_secs で判定すること）。
失敗履歴は対象の JSON レコード内 auth_fails に保存する。
ロック発生（＝閾値到達）は異常事象として DATA_DIR/auth.log と stderr に記録する。
"""
import os
import sys
import time

from lib import config, store


def _recent(rec, now):
    return [t for t in rec.get("auth_fails", [])
            if t > now - config.AUTH_LOCK_SECS]


def locked_secs(rec):
    """ロック中なら残り秒数（1以上）、そうでなければ 0 を返す。"""
    now = time.time()
    recent = _recent(rec, now)
    if len(recent) >= config.AUTH_MAX_FAILS:
        return max(1, int(max(recent) + config.AUTH_LOCK_SECS - now))
    return 0


def locked_message(rec):
    secs = locked_secs(rec)
    if not secs:
        return ""
    return ("試行回数が多いため一時的にロックされています"
            "（約%d分後に再試行できます）" % max(1, (secs + 59) // 60))


def _log_lock(kind, srv, xid, ip):
    line = "%s LOCK %s %s/%s fails=%d ip=%s" % (
        time.strftime("%Y-%m-%d %H:%M:%S"), kind, srv, xid,
        config.AUTH_MAX_FAILS, ip or "-")
    try:
        with open(os.path.join(config.DATA_DIR, "auth.log"),
                  "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    print("[pnsg] auth " + line, file=sys.stderr)  # Apacheのエラーログにも残す


def _note(get, save, srv, xid, kind, ip):
    with store.lock(srv):
        rec = get(srv, xid)
        if rec:
            now = time.time()
            fails = _recent(rec, now)
            fails.append(int(now))
            rec["auth_fails"] = fails
            save(srv, rec)
            if len(fails) == config.AUTH_MAX_FAILS:  # 閾値到達＝ロック発生時のみ
                _log_lock(kind, srv, xid, ip)


def _clear(get, save, srv, xid):
    with store.lock(srv):
        rec = get(srv, xid)
        if rec and rec.get("auth_fails"):
            rec["auth_fails"] = []
            save(srv, rec)


def note_char_fail(srv, cid, ip=None):
    _note(store.get_character, store.save_character, srv, cid, "character", ip)


def clear_char_fails(srv, cid):
    _clear(store.get_character, store.save_character, srv, cid)


def note_event_fail(srv, eid, ip=None):
    _note(store.get_event, store.save_event, srv, eid, "event-host", ip)


def clear_event_fails(srv, eid):
    _clear(store.get_event, store.save_event, srv, eid)
