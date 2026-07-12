#!/usr/bin/env python3
"""お試し（デモ）サーバー #0000 を作成・リセットする運用ツール。

誰でも触れる公開サンドボックスを用意する:
- ダミーキャラクター15体（共通編集キーは公開前提の demo1234）
- デモイベント2件（受付中の「参加登録編」と、締切・発表済みの「発表シフト編」。
  ホストパスワードは公開前提の demohost）

再実行するとデモサーバーのデータを全消しして作り直す（＝リセット）。

使い方:
  サーバー上:  cd ~/www/<公開ディレクトリ> && python3 ~/setup_demo.py
  ローカル  :  python3 tools/setup_demo.py
"""
import os
import random
import shutil
import sys
import time

_here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _cand in (os.path.join(_here, "www"), os.getcwd()):
    if os.path.isdir(os.path.join(_cand, "lib")):
        sys.path.insert(0, _cand)
        break

from lib import auth, config, host, store
from lib import shift as shiftmod

SRV = "0000"
EDIT_KEY = "demo1234"    # 公開デモ用（実サーバーでは使わないこと）
HOST_PASS = "demohost"   # 公開デモ用
CHOICES = ["前半参加", "後半参加", "フルタイム", "不参加"]


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def make_chars(rng):
    kinds = (("Fighter", "デモ戦士"), ("Shooter", "デモ射手"),
             ("Rider", "デモ騎兵"))
    chars = []
    n = 0
    for troop, base in kinds:
        for _ in range(5):
            n += 1
            salt = auth.new_salt()
            shelter = ""
            if n % 2:
                shelter = "%d,%d" % (rng.randrange(511), rng.randrange(1023))
            chars.append(dict(
                id=store.new_char_id(SRV),
                name="%s%02d" % (base, n),
                guild="DEMO-A" if n % 2 else "DEMO-B",
                troop_type=troop,
                tier=rng.randrange(7, 12),
                march_size=rng.randrange(80, 331) * 1000,
                gather_size=rng.randrange(400, 1801) * 1000,
                shelter=shelter,
                has_profile_img=False, album=[], upload_log=[],
                key_salt=salt, key_hash=auth.hash_key(salt, EDIT_KEY),
                created=_now(), updated=_now()))
    return chars


def _event(title, body, date_at, deadline_at):
    salt = auth.new_salt()
    return {"id": store.new_event_id(SRV), "title": title, "body": body,
            "date_at": date_at, "deadline_at": deadline_at,
            "choices": list(CHOICES),
            "shift": {"enabled": True,
                      "targets": shiftmod.default_targets(),
                      "slots": dict((c, shiftmod.guess_slot(c))
                                    for c in CHOICES)},
            "closed": False, "entries": {}, "created": _now(),
            "host_salt": salt, "host_hash": auth.hash_key(salt, HOST_PASS)}


def main():
    rng = random.Random(20260713)  # 毎回同じデモデータになるよう固定シード

    with store.lock():
        servers = store.load_servers()
        servers[SRV] = {"name": "お試し（デモ）",
                        "created": time.strftime("%Y-%m-%d")}
        store.save_servers(servers)

    # 既存のデモデータを全消しして作り直す
    shutil.rmtree(os.path.join(config.DATA_DIR, SRV), ignore_errors=True)
    shutil.rmtree(os.path.join(config.IMG_DIR, SRV), ignore_errors=True)

    chars = make_chars(rng)
    with store.lock(SRV):
        for c in chars:
            store.save_character(SRV, c)

    note = ("これは誰でも自由に触れるデモです。\n"
            "全キャラクター共通の編集キー: %s\n"
            "ホストパスワード: %s\n"
            "データは不定期にリセットされます。" % (EDIT_KEY, HOST_PASS))

    ev_a = _event("お試しイベント（参加登録編）",
                  note + "\nこちらは受付中です。参加登録をすると下の予想シフト表が変わります。",
                  "2026-12-31T21:00", "2026-12-29T21:00")

    ev_b = _event("お試しイベント（発表シフト編）",
                  note + "\nこちらは締切・発表済みです。「発表シフト」からホストパスワードで"
                         "認証すると、キャプテン任命・移動・報酬分配リストの操作を試せます。",
                  "2026-07-12T21:00", "2026-07-10T21:00")
    for i, c in enumerate(chars):
        choice = CHOICES[i % 4] if i != len(chars) - 1 else "不参加"
        ev_b["entries"][c["id"]] = {"choice": choice, "updated": _now()}
    ev_b["published"] = host.build_published(
        ev_b, dict((c["id"], c) for c in chars))

    with store.lock(SRV):
        store.save_event(SRV, ev_a)
        store.save_event(SRV, ev_b)

    print("デモサーバー #%s を作成/リセットしました" % SRV)
    print("  キャラクター: %d体（編集キー: %s）" % (len(chars), EDIT_KEY))
    print("  イベント: %s / %s（ホストパスワード: %s）"
          % (ev_a["id"], ev_b["id"], HOST_PASS))


if __name__ == "__main__":
    main()
