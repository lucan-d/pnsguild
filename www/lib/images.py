"""画像の検証・縮小保存とパス管理。

本番（さくら）は ImageMagick、開発機は Pillow にフォールバック。
再エンコードを必ず通すことで EXIF 除去とファイル偽装対策を兼ねる。
"""
import os
import shutil
import subprocess
import tempfile

from lib import config

_EXT = {"jpeg": ".jpg", "png": ".png", "webp": ".webp"}


def sniff(data):
    """マジックバイトで画像形式を判定。Content-Type は信用しない。"""
    if data[:3] == b"\xff\xd8\xff":
        return "jpeg"
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return None


def _im_bin():
    return shutil.which("convert") or shutil.which("magick")


def save_image(data, dest, thumb):
    """画像バイト列を縮小JPEGとして dest / thumb に保存。
    成功時 None、失敗時はユーザー向けエラーメッセージを返す。"""
    kind = sniff(data)
    if kind is None:
        return "JPEG / PNG / WebP の画像のみアップロードできます"
    if len(data) > config.MAX_UPLOAD_BYTES:
        return "画像は1枚 %dMB 以内にしてください" % (config.MAX_UPLOAD_BYTES // 1024 // 1024)
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=_EXT[kind], delete=False) as tf:
        tf.write(data)
        src = tf.name
    try:
        if _im_bin():
            return _save_im(src, dest, thumb)
        return _save_pillow(src, dest, thumb)
    finally:
        os.unlink(src)


def _save_im(src, dest, thumb):
    conv = _im_bin()
    for out, edge in ((dest, config.IMG_MAX_EDGE), (thumb, config.THUMB_MAX_EDGE)):
        r = subprocess.run(
            [conv, src + "[0]", "-auto-orient", "-strip",
             "-resize", "%dx%d>" % (edge, edge), "-quality", "85", "jpg:" + out],
            capture_output=True, timeout=30)
        if r.returncode != 0:
            return "画像の変換に失敗しました"
    return None


def _save_pillow(src, dest, thumb):
    try:
        from PIL import Image, ImageOps
    except ImportError:
        return "サーバーに画像変換ツールがありません（管理者に連絡してください）"
    try:
        for out, edge in ((dest, config.IMG_MAX_EDGE), (thumb, config.THUMB_MAX_EDGE)):
            with Image.open(src) as im:
                im = ImageOps.exif_transpose(im)
                im.thumbnail((edge, edge))
                im.convert("RGB").save(out, "JPEG", quality=85)
    except Exception:
        return "画像の変換に失敗しました"
    return None


# ---------- パス・URL ----------

def char_img_dir(srv, cid):
    return os.path.join(config.IMG_DIR, srv, cid)


def img_url(srv, cid, name):
    return "%s/img/%s/%s/%s" % (config.BASE, srv, cid, name)


def delete_image(srv, cid, name):
    for n in (name, "t_" + name):
        try:
            os.remove(os.path.join(char_img_dir(srv, cid), n))
        except FileNotFoundError:
            pass


def delete_char_images(srv, cid):
    shutil.rmtree(char_img_dir(srv, cid), ignore_errors=True)


def next_album_name(album):
    for i in range(1, config.MAX_ALBUM + 1):
        n = "a%02d.jpg" % i
        if n not in album:
            return n
    return None
