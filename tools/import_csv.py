#!/usr/bin/env python3
"""スプレッドシート(CSV)からキャラクターを一括登録する運用ツール。

使い方:
    python3 tools/import_csv.py <CSVファイル> <サーバー4桁> [共通編集キー]

想定ヘッダー（Google スプレッドシートのエクスポート形式）:
    Alliance → ギルド名 / User Name → キャラクター名 / Unit Type → 特化兵種
    Troop Size → 部隊規模 / Rally Size → ギャザー規模
名前が空の行は読み飛ばす。編集キーは全員同じ値で登録される（省略時 test1234）。
"""
import csv
import os
import re
import sys
import time

# lib の場所: 開発環境ではリポジトリの www/、サーバー上では
# カレントディレクトリ（~/www/pns で実行する想定）から探す
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _cand in (os.path.join(ROOT, "www"), os.getcwd()):
    if os.path.isdir(os.path.join(_cand, "lib")):
        sys.path.insert(0, _cand)
        break

from lib import auth, config, store


def num(s):
    s = (s or "").replace(",", "").replace(" ", "").replace("　", "").strip()
    return int(s) if s.isdigit() else None


def main():
    if len(sys.argv) < 3 or not re.fullmatch(r"\d{4}", sys.argv[2]):
        print(__doc__)
        sys.exit(1)
    path, srv = sys.argv[1], sys.argv[2]
    key = sys.argv[3] if len(sys.argv) > 3 else "test1234"

    with store.lock():
        servers = store.load_servers()
        if srv not in servers:
            servers[srv] = {"name": "s" + srv,
                            "created": time.strftime("%Y-%m-%d")}
            store.save_servers(servers)
            print("サーバー #%s を新規登録" % srv)

    count = 0
    skipped = 0
    with open(path, newline="", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            name = (row.get("User Name") or "").strip()[:30]
            if not name:
                skipped += 1
                continue
            troop = (row.get("Unit Type") or "").strip().capitalize()
            if troop not in config.TROOP_TYPES:
                troop = "Fighter"
            salt = auth.new_salt()
            now = time.strftime("%Y-%m-%dT%H:%M:%S")
            with store.lock(srv):
                cid = store.new_char_id(srv)
                store.save_character(srv, dict(
                    id=cid, name=name,
                    guild=(row.get("Alliance") or "").strip()[:30],
                    troop_type=troop,
                    march_size=num(row.get("Troop Size")),
                    gather_size=num(row.get("Rally Size")),
                    tier=num(row.get("Tier")),
                    shelter="", has_profile_img=False, album=[],
                    upload_log=[], key_salt=salt,
                    key_hash=auth.hash_key(salt, key),
                    created=now, updated=now))
            count += 1
    print("登録 %d件 / 読み飛ばし %d行（サーバー #%s、編集キー: %s）"
          % (count, skipped, srv, key))


if __name__ == "__main__":
    main()
