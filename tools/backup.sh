#!/bin/sh
# 本番データのバックアップ（pull型・手元マシンで実行）。
# 使い方: SSH_DEST=<接続先(user@host または ssh エイリアス)> tools/backup.sh
#   1. サーバーの ~/pnsg-data と ~/www/<DIR>/img を backup/mirror/ に rsync
#   2. 日付付き tar.gz を backup/ に作成（14世代より古いものは削除）
set -eu

DEST=${SSH_DEST:?接続先を SSH_DEST で指定してください}
DIR=${PNSG_REMOTE_DIR:-pns}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
BK="$ROOT/backup"

mkdir -p "$BK/mirror"
echo "== ミラー同期 =="
rsync -a --delete "$DEST:pnsg-data/" "$BK/mirror/pnsg-data/"
rsync -a --delete "$DEST:www/$DIR/img/" "$BK/mirror/img/"

STAMP=$(date +%Y%m%d-%H%M)
tar czf "$BK/pnsg-$STAMP.tar.gz" -C "$BK/mirror" .
echo "== 作成: backup/pnsg-$STAMP.tar.gz =="

# 古い世代の削除（新しい14個を残す）
ls -1t "$BK"/pnsg-*.tar.gz 2>/dev/null | tail -n +15 | xargs -r rm --
ls -lh "$BK"/pnsg-*.tar.gz | tail -3
