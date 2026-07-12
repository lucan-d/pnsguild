"""イベントの開催日時・受付締切まわりの共通処理。

date_at / deadline_at は datetime-local 入力の文字列（YYYY-MM-DDTHH:MM）を
そのまま保存する。旧イベントの自由テキスト date は表示のみ対応し、
締切の自動計算は行わない（手動の「締め切る」のみ有効）。
"""
import time

FMT = "%Y-%m-%dT%H:%M"
DEADLINE_HOURS = 48


def parse_dt(s):
    """日時文字列 → epoch秒。解釈できなければ None。"""
    try:
        return time.mktime(time.strptime(s, FMT))
    except (ValueError, TypeError):
        return None


def fmt_disp(s):
    t = parse_dt(s)
    if t is None:
        return s or ""
    return time.strftime("%Y-%m-%d %H:%M", time.localtime(t))


def date_str(ev):
    return fmt_disp(ev.get("date_at") or ev.get("date") or "")


def deadline_str(ev):
    return fmt_disp(ev.get("deadline_at") or "")


def is_closed(ev):
    """参加受付が終了しているか（手動締切 or 締切日時超過）。"""
    if ev.get("closed"):
        return True
    t = parse_dt(ev.get("deadline_at") or "")
    return t is not None and time.time() > t


def default_deadline(date_at):
    """開催日時から既定の受付締切（48時間前）を計算。"""
    t = parse_dt(date_at)
    if t is None:
        return ""
    return time.strftime(FMT, time.localtime(t - DEADLINE_HOURS * 3600))
