# セットアップ手順

## ローカル開発（実装テスト）

```
python3 devserver.py [ポート番号]   # 既定 8080
```

- 一般側: http://127.0.0.1:8080/
- 管理側: http://127.0.0.1:8080/admin/ （ローカルでは Basic 認証なし）
- データは `./data/`、画像は `./www/img/` に保存される。全消しすれば初期化。
- 画像縮小はローカルでは Pillow を使用（`pip install pillow`）。
  本番はさくら標準の ImageMagick を使うので Pillow は不要。

## さくらのレンタルサーバー（スタンダード）への設置

### 1. サブドメインの追加

コントロールパネルでドメイン設定を開き、使用中ドメインのサブドメイン
（例: `pns.example.com`）を追加。マッピング先を `/home/アカウント名/www/pnsg/`
に設定する。無料SSL（Let's Encrypt）も有効にしておく。

### 2. デプロイ（スクリプト使用）

```
tools/deploy.sh アカウント名 [公開ディレクトリ名]   # 既定 pnsg
```

スクリプトが行うこと:
- `~/pnsg-data/`（データ・非公開）と `~/www/pnsg/img/` の作成
- `www/` 一式の rsync 転送（ローカルのテスト画像・`__pycache__` は除外）
- CGI への実行権限付与（chmod 755）
- `lib/localconfig.py` の生成（`DATA_DIR` をサーバー実パスに設定）
- `admin/.htaccess` の `AuthUserFile` をサーバー実パスに書き換え
- サーバー側 `python3` の存在とバージョン表示

2回目以降も同じコマンドで差分デプロイできる（データ・画像・
localconfig.py は上書きされない）。

### 3. 管理者パスワード（初回のみ）

```
ssh アカウント名@アカウント名.sakura.ne.jp 'htpasswd -c ~/pnsg-data/.htpasswd 管理ユーザー名'
```

### 4. Python の確認

- deploy.sh の出力で `python3` が見つからない場合は、
  `www/index.cgi` と `www/admin/admin.cgi` の1行目（シバン）を
  サーバーの `which python3` の結果に書き換えて再デプロイ。
- Python 3.7 以上であること（cgi モジュールには依存していないので
  3.13 以降でも動く）。

### 5. 動作確認

1. `https://サブドメイン/` → サーバー選択ページが表示される
2. `https://サブドメイン/admin/` → Basic 認証 → 管理トップ
3. 管理画面でサーバー（4桁）を登録 → 一般側でキャラクター登録
4. 画像アップロードして縮小されることを確認（ImageMagick が呼ばれる）

### トラブル時

- 500 エラー: さくらのコントロールパネルのエラーログを確認。
  多くはシバンのパス違いか改行コード（必ず LF でアップロード）。
- 画像変換エラー: `which convert` で ImageMagick の有無を確認。
