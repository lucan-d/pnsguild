"""設定。設置環境ごとの上書きは lib/localconfig.py に書く（sample 参照）。"""
import os

_here = os.path.dirname(os.path.abspath(__file__))

SITE_NAME = "PNSキャラクターリスト"

# 公開URLのベースパス。サブドメイン直下に置くなら ""
BASE = ""

# トップページに出すGitHubリポジトリへのリンク先
GITHUB_URL = "https://github.com/lucan-d/pnsguild"

# データ保存先（ドキュメントルート外に置くこと）。未設定なら開発用に ../data
DATA_DIR = os.environ.get("PNSG_DATA") or os.path.normpath(
    os.path.join(_here, "..", "..", "data"))

# アップロード画像の保存先（公開領域 www/img）
IMG_DIR = os.path.normpath(os.path.join(_here, "..", "img"))

MAX_UPLOAD_BYTES = 5 * 1024 * 1024   # 1ファイルの受付上限
MAX_BODY_BYTES = 8 * 1024 * 1024     # リクエストボディ全体の上限
MAX_ALBUM = 10                       # アルバム最大枚数
UPLOAD_RATE = 10                     # 1キャラクターの画像投稿上限（枚/時間）
IMG_MAX_EDGE = 1280                  # 保存画像の長辺
THUMB_MAX_EDGE = 320                 # サムネイルの長辺
SESSION_DAYS = 30                    # 編集キー認証の有効日数
MIN_KEY_LEN = 4                      # 編集キー最短文字数
AUTH_MAX_FAILS = 5                   # 認証失敗の許容回数
AUTH_LOCK_SECS = 15 * 60             # ロック時間（秒）＝失敗カウント窓

TROOP_TYPES = ("Fighter", "Shooter", "Rider")

# イベントのシフト対象デフォルト（名称, 兵種）
SHIFT_TARGETS = (
    ("中央基地", "Fighter"),
    ("北砲台", "Fighter"),
    ("東砲台", "Shooter"),
    ("南砲台", "Rider"),
    ("西砲台", "Rider"),
)

try:
    from lib.localconfig import *  # noqa: F401,F403
except ImportError:
    pass
