#!/bin/sh
# さくらのレンタルサーバーへのデプロイ。
# 使い方: tools/deploy.sh <アカウント名> [公開ディレクトリ名(既定 pnsg)]
# 例:     tools/deploy.sh myaccount pnsg
# 前提:   コントロールパネルでサブドメインを ~/www/<公開ディレクトリ名>/ に
#         マッピング済みであること。SSH はパスワードまたは鍵で接続できること。
set -eu

ACCOUNT=${1:?アカウント名を指定してください}
DIR=${2:-pnsg}
HOST="$ACCOUNT.sakura.ne.jp"
# ~/.ssh/config のエイリアスを使う場合は SSH_DEST=エイリアス名 で上書き
DEST=${SSH_DEST:-"$ACCOUNT@$HOST"}
ROOT=$(cd "$(dirname "$0")/.." && pwd)

echo "== 1/4 ディレクトリ準備 =="
ssh "$DEST" "mkdir -p ~/pnsg-data ~/www/$DIR/img"

echo "== 2/4 ファイル転送 =="
# さくらの suEXEC はグループ書き込み可(775/664)を拒否するため、
# 転送時にディレクトリ755・ファイル644へ正規化する
rsync -av \
  --chmod=Du=rwx,Dgo=rx,Fu=rw,Fgo=r \
  --exclude 'img/*' \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  --exclude 'localconfig.py' \
  "$ROOT/www/" "$DEST:~/www/$DIR/"

echo "== 3/4 サーバー側設定 =="
ssh "$DEST" "
  chmod 755 ~/www/$DIR/index.cgi ~/www/$DIR/admin/admin.cgi
  # localconfig.py（無ければ生成）
  if [ ! -f ~/www/$DIR/lib/localconfig.py ]; then
    printf 'DATA_DIR = \"/home/$ACCOUNT/pnsg-data\"\n' > ~/www/$DIR/lib/localconfig.py
    echo 'localconfig.py を生成しました'
  fi
  # Basic認証のパスワードファイルパスを実パスに書き換え
  sed -i.bak 's|/home/YOUR_ACCOUNT/pnsg-data/.htpasswd|/home/$ACCOUNT/pnsg-data/.htpasswd|' \
    ~/www/$DIR/admin/.htaccess && rm -f ~/www/$DIR/admin/.htaccess.bak
  echo 'python3: ' \$(which python3 || echo '見つかりません → CGIのシバン要修正')
  python3 --version 2>/dev/null || true
"

echo "== 4/4 残作業（手動） =="
echo "  1. 管理者パスワード（初回のみ）:"
echo "       ssh $DEST 'htpasswd -c ~/pnsg-data/.htpasswd 管理ユーザー名'"
echo "  2. ブラウザ確認: https://サブドメイン/ と https://サブドメイン/admin/"
