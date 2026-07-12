"""一般側（スマホ基準）の画面。"""
import os
import re
import time
import urllib.parse

from lib import auth, config, evutil, images, shift, store, throttle, tpl
from lib.forms import validate_char
from lib.tpl import h, url
from lib.web import html_page, not_found, redirect

_MSG = {
    "imgerr": "画像の保存に失敗しました（形式・サイズ・投稿回数を確認してください）",
    "saved": "保存しました",
    "keysaved": "保存しました（編集キーを変更しました）",
    "joined": "参加情報を更新しました",
}


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


# ---------- 認証まわり ----------

def _get_session(req, srv, cid):
    tok = req.cookie(auth.cookie_name(srv, cid))
    if tok and auth.check_session(tok, srv, cid):
        return tok
    return None


def _set_session(resp, srv, cid):
    resp.set_cookie(auth.cookie_name(srv, cid), auth.make_session(srv, cid),
                    config.SESSION_DAYS * 86400)
    return resp


def _my_sessions(req, srv, chars):
    """認証済みキャラクターの {cid: 有効期限} を返す。
    有効期限は認証時刻+一定日数なので、大きいほど最近認証したキャラ。"""
    out = {}
    for c in chars:
        tok = req.cookie(auth.cookie_name(srv, c["id"]))
        if tok and auth.check_session(tok, srv, c["id"]):
            out[c["id"]] = int(tok.split(".")[2])
    return out


def _login_page(srv, char, tpath, error=""):
    body = tpl.errors_html([error]) + """
<p>「%s」の操作には編集キーが必要です。</p>
<form method="post" action="%s" class="stack">
<input type="password" name="login_key" placeholder="編集キー" required>
<button class="btn primary">認証する</button>
</form>
<p class="hint">編集キーを忘れた場合は管理者に再設定を依頼してください。</p>
""" % (h(char["name"]), h(url(tpath)))
    return html_page("編集キーの確認", body,
                     back=url("/%s/c/%s" % (srv, char["id"])))


def _handle_login(req, srv, char, tpath):
    """POSTに login_key があれば認証を処理して Response を返す。なければ None。"""
    fields, _ = req.form()
    if "login_key" not in fields:
        return None
    lmsg = throttle.locked_message(char)
    if lmsg:
        return _login_page(srv, char, tpath, lmsg)
    if auth.verify_key(char, req.field("login_key")):
        throttle.clear_char_fails(srv, char["id"])
        return _set_session(redirect(tpath), srv, char["id"])
    throttle.note_char_fail(srv, char["id"],
                            req.environ.get("REMOTE_ADDR"))
    return _login_page(srv, char, tpath, "編集キーが違います")


def _csrf_ok(req, sess):
    return bool(sess) and req.field("csrf") == auth.csrf_token(sess)

_EXPIRED = "セッションの有効期限が切れました。編集キーを入力してください"


# ---------- 画像 ----------

def _rate_error(char):
    now = int(time.time())
    char["upload_log"] = [t for t in char.get("upload_log", []) if t > now - 3600]
    if len(char["upload_log"]) >= config.UPLOAD_RATE:
        return "画像の投稿が多すぎます。1時間ほど空けてからもう一度お試しください"
    return None


def _save_profile_img(srv, char, data):
    err = _rate_error(char)
    if err:
        return err
    d = images.char_img_dir(srv, char["id"])
    err = images.save_image(data, os.path.join(d, "profile.jpg"),
                            os.path.join(d, "t_profile.jpg"))
    if err:
        return err
    char["has_profile_img"] = True
    char["upload_log"].append(int(time.time()))
    return None


# ---------- 画面部品 ----------

def _shelter_map_html(shelter):
    """避難所座標の抽象マップ表示（左上が0,0）。details でポップアップ。

    実座標は 511×1023 だが、X軸を2倍に引き伸ばして 1022×1023 の
    ほぼ正方形で描画する。
    """
    try:
        xs, ys = shelter.split(",")
        x, y = int(xs), int(ys)
    except ValueError:
        return ""
    if not (0 <= x <= 510 and 0 <= y <= 1022):
        return ""
    px = x * 2  # X軸を2倍
    grid = ""
    for i in range(1, 10):
        gx = 1022.0 * i / 10
        grid += '<line x1="%.1f" y1="0" x2="%.1f" y2="1023"/>' % (gx, gx)
        gy = 1023.0 * i / 10
        grid += '<line x1="0" y1="%.1f" x2="1022" y2="%.1f"/>' % (gy, gy)
    tx = max(70, min(952, px))              # ラベルが端で切れないように寄せる
    ty = y - 30 if y > 80 else y + 62
    return """
<details class="mapbox"><summary class="btn small">避難所位置をマップ表示</summary>
<div class="mapwrap">
<svg viewBox="0 0 1022 1023" class="hexmap" role="img" aria-label="避難所位置">
<rect x="0" y="0" width="1022" height="1023" class="mapbg"/>
<g class="grid">%s</g>
<circle cx="%d" cy="%d" r="14" class="pt"/>
<text x="%d" y="%d" text-anchor="middle" class="ptlabel">%d,%d</text>
</svg>
<p class="hint">マップ全体 511×1023（左上が 0,0・横方向は2倍に拡大表示）</p>
</div></details>""" % (grid, px, y, tx, ty, x, y)


def _char_card(srv, c):
    cid = c["id"]
    if c.get("has_profile_img"):
        img = '<img src="%s" alt="" loading="lazy">' % h(
            images.img_url(srv, cid, "t_profile.jpg"))
    else:
        img = '<div class="noimg">%s</div>' % h((c.get("name") or "?")[:1])
    guild = c.get("guild") or "（無所属）"
    return """<a class="char" href="%s">%s<div class="char-body">
<div class="char-name">%s %s</div>
<div class="char-sub">%s</div>
<div class="char-nums">部隊 %s ／ ギャザー %s</div>
</div></a>""" % (
        h(url("/%s/c/%s" % (srv, cid))), img, h(c["name"]),
        tpl.troop_badge(c.get("troop_type")), h(guild),
        tpl.fmt_march(c.get("march_size"), c.get("tier")),
        tpl.fmt_num(c.get("gather_size")))


def _char_form(srv, tpath, c, csrf, is_new, submit_label):
    def v(k):
        x = c.get(k)
        return h("" if x is None else x)

    opts = "".join(
        '<option value="%s"%s>%s</option>'
        % (t, " selected" if c.get("troop_type") == t else "", t)
        for t in config.TROOP_TYPES)
    if is_new:
        keypart = """
<label>編集キー（%d文字以上・編集時に必要）<input type="password" name="edit_key" required></label>
<label>編集キー（確認）<input type="password" name="edit_key2" required></label>
""" % config.MIN_KEY_LEN
    else:
        keypart = """
<h2>編集キー変更</h2>
<label>新しい編集キー（変更する場合のみ・%d文字以上）<input type="password" name="new_key"></label>
<label>新しい編集キー（確認）<input type="password" name="new_key2"></label>
""" % config.MIN_KEY_LEN
    imglabel = "プロフィール画像（1枚・5MBまで）"
    if c.get("has_profile_img"):
        imglabel = "プロフィール画像（選択すると差し替え）"
    return """
<form method="post" action="%s" enctype="multipart/form-data" class="stack">
<input type="hidden" name="csrf" value="%s">
<label>キャラクター名 *<input type="text" name="name" maxlength="30" value="%s" required></label>
<label>ギルド名<input type="text" name="guild" maxlength="30" value="%s"></label>
<label>特化兵種 *<select name="troop_type">%s</select></label>
<label>Tier（兵種ティア）<input type="text" name="tier" inputmode="numeric" value="%s" placeholder="例: 8"></label>
<label>部隊規模<input type="text" name="march_size" inputmode="numeric" value="%s" placeholder="例: 1500000"></label>
<label>ギャザー規模<input type="text" name="gather_size" inputmode="numeric" value="%s"></label>
<label>避難所座標（xxx,yyy）<input type="text" name="shelter" value="%s" placeholder="例: 123,456"></label>
<label>%s<input type="file" name="profile_img" accept="image/jpeg,image/png,image/webp"></label>
%s
<button class="btn primary">%s</button>
</form>""" % (h(url(tpath)), h(csrf), v("name"), v("guild"), opts,
              v("tier"), v("march_size"), v("gather_size"), v("shelter"),
              imglabel, keypart, h(submit_label))


def _event_rows(srv, events):
    if not events:
        return '<p class="empty">イベントはありません</p>'
    out = '<ul class="events">'
    for e in events:
        mark = '<span class="tag closed">締切</span>' if evutil.is_closed(e) else ""
        out += ('<li><a href="%s"><span class="ev-date">%s</span> %s %s '
                '<span class="sub">（参加登録 %d件）</span></a></li>') % (
            h(url("/%s/e/%s" % (srv, e["id"]))), h(evutil.date_str(e)),
            h(e["title"]), mark, len(e.get("entries") or {}))
    return out + "</ul>"


# ---------- ハンドラ ----------

def home(req):
    s = req.q("s").strip()
    if s and store.server_exists(s):
        return redirect("/%s/" % s)
    errors = []
    if s:
        errors.append("サーバー #%s は未登録です。管理者に登録を依頼してください" % s)
    servers = store.load_servers()
    items = ""
    for num in sorted(servers):
        items += ('<li><a class="card-link" href="%s">#%s '
                  '<span class="sub">%s</span></a></li>') % (
            h(url("/%s/" % num)), h(num), h(servers[num].get("name") or ""))
    if not items:
        items = '<li class="empty">登録済みサーバーはまだありません</li>'
    body = tpl.errors_html(errors) + """
<form method="get" action="%s" class="jump">
<input type="text" name="s" inputmode="numeric" pattern="\\d{4}" maxlength="4" placeholder="サーバー番号（4桁）" required>
<button class="btn primary">移動</button>
</form>
<h2>サーバー一覧</h2>
<ul class="cards">%s</ul>""" % (h(url("/")), items)
    return html_page("サーバー選択", body)


def server_top(req, srv):
    if not store.server_exists(srv):
        return not_found("サーバー #%s は未登録です。管理者に登録を依頼してください" % srv)
    chars = store.list_characters(srv)
    guild = req.q("guild")
    counts = {}
    for c in chars:
        g = c.get("guild") or ""
        if g:
            counts[g] = counts.get(g, 0) + 1
    shown = [c for c in chars if not guild or (c.get("guild") or "") == guild]

    tags = ""
    for g in sorted(counts):
        cls = "tag on" if g == guild else "tag"
        href = url("/%s/" % srv) + "?guild=" + urllib.parse.quote(g)
        tags += '<a class="%s" href="%s">%s (%d)</a>' % (cls, h(href), h(g), counts[g])
    if guild:
        tags += '<a class="tag clear" href="%s">解除</a>' % h(url("/%s/" % srv))

    cards = "".join(_char_card(srv, c) for c in shown)
    if not cards:
        cards = '<p class="empty">キャラクターがまだ登録されていません</p>'

    body = """
<p><a class="btn primary" href="%s">＋ キャラクター新規登録</a></p>
<h2>イベント</h2>
%s
<h2>キャラクター（%d）</h2>
<div class="tags">%s</div>
<div class="charlist">%s</div>""" % (
        h(url("/%s/new" % srv)), _event_rows(srv, store.list_events(srv)),
        len(shown), tags, cards)
    return html_page("サーバー #%s" % srv, body, back=url("/"))


def char_new(req, srv):
    if not store.server_exists(srv):
        return not_found()
    tpath = "/%s/new" % srv
    back = url("/%s/" % srv)
    if req.method == "GET":
        return html_page("キャラクター新規登録",
                         _char_form(srv, tpath, {}, "", True, "登録する"),
                         back=back)
    data, errors = validate_char(req)
    key = req.field("edit_key")
    if len(key) < config.MIN_KEY_LEN:
        errors.append("編集キーは%d文字以上にしてください" % config.MIN_KEY_LEN)
    elif key != req.field("edit_key2"):
        errors.append("編集キー（確認）が一致しません")
    if errors:
        return html_page(
            "キャラクター新規登録",
            tpl.errors_html(errors) + _char_form(srv, tpath, data, "", True, "登録する"),
            back=back)
    salt = auth.new_salt()
    imgerr = None
    with store.lock(srv):
        cid = store.new_char_id(srv)
        now = _now()
        char = dict(data, id=cid, has_profile_img=False, album=[],
                    upload_log=[], key_salt=salt,
                    key_hash=auth.hash_key(salt, key), created=now, updated=now)
        f = req.file("profile_img")
        if f:
            imgerr = _save_profile_img(srv, char, f[1])
        store.save_character(srv, char)
    resp = redirect("/%s/c/%s%s" % (srv, cid, "?m=imgerr" if imgerr else ""))
    return _set_session(resp, srv, cid)


def char_detail(req, srv, cid):
    char = store.get_character(srv, cid)
    if not char:
        return not_found()
    note = tpl.notice(_MSG.get(req.q("m"), ""))

    if char.get("has_profile_img"):
        u = h(images.img_url(srv, cid, "profile.jpg"))
        pi = '<a href="%s"><img class="profile" src="%s" alt=""></a>' % (u, u)
    else:
        pi = '<div class="noimg big">%s</div>' % h(char["name"][:1])

    guild = char.get("guild") or ""
    if guild:
        gl = '<a href="%s?guild=%s">%s</a>' % (
            h(url("/%s/" % srv)), h(urllib.parse.quote(guild)), h(guild))
    else:
        gl = "（無所属）"
    rows = ""
    for label, val in (
            ("ギルド名", gl),
            ("特化兵種", tpl.troop_badge(char.get("troop_type"))),
            ("部隊規模", h(tpl.fmt_march(char.get("march_size"), char.get("tier")))),
            ("ギャザー規模", h(tpl.fmt_num(char.get("gather_size")))),
            ("避難所座標", h(char.get("shelter") or "-")),
            ("更新日", h((char.get("updated") or "").replace("T", " ")))):
        rows += "<tr><th>%s</th><td>%s</td></tr>" % (label, val)

    album = ""
    for name in char.get("album", []):
        album += '<a class="ph" href="%s"><img src="%s" alt="" loading="lazy"></a>' % (
            h(images.img_url(srv, cid, name)),
            h(images.img_url(srv, cid, "t_" + name)))
    if not album:
        album = '<p class="empty">アルバムは空です</p>'

    own = """
<div class="ownerbar">
<a class="btn" href="%s">編集</a>
<a class="btn" href="%s">アルバム管理</a>
</div>
<p class="hint">※本人（編集キーを知っている人）のみ操作できます。
キャラクターの削除は管理者に依頼してください。</p>""" % (
        h(url("/%s/c/%s/edit" % (srv, cid))),
        h(url("/%s/c/%s/album" % (srv, cid))))

    smap = _shelter_map_html(char.get("shelter") or "")
    body = (note + '<div class="profile-wrap">%s</div><table class="kv">%s</table>%s'
            '<h2>アルバム（%d/%d）</h2><div class="album">%s</div>%s') % (
        pi, rows, smap, len(char.get("album", [])), config.MAX_ALBUM, album, own)
    return html_page(char["name"], body, back=url("/%s/" % srv))


def char_edit(req, srv, cid):
    char = store.get_character(srv, cid)
    if not char:
        return not_found()
    tpath = "/%s/c/%s/edit" % (srv, cid)
    back = url("/%s/c/%s" % (srv, cid))
    sess = _get_session(req, srv, cid)
    if req.method == "POST":
        r = _handle_login(req, srv, char, tpath)
        if r:
            return r
        if not _csrf_ok(req, sess):
            return _login_page(srv, char, tpath, _EXPIRED)
        data, errors = validate_char(req)
        newkey = req.field("new_key")
        if newkey:
            if len(newkey) < config.MIN_KEY_LEN:
                errors.append("新しい編集キーは%d文字以上にしてください" % config.MIN_KEY_LEN)
            elif newkey != req.field("new_key2"):
                errors.append("新しい編集キー（確認）が一致しません")
        if errors:
            return html_page(
                "キャラクター編集",
                tpl.errors_html(errors) + _char_form(
                    srv, tpath, dict(char, **data),
                    auth.csrf_token(sess), False, "保存する"),
                back=back)
        imgerr = None
        with store.lock(srv):
            char = store.get_character(srv, cid)
            if not char:
                return not_found()
            char.update(data)
            if newkey:
                char["key_salt"] = auth.new_salt()
                char["key_hash"] = auth.hash_key(char["key_salt"], newkey)
            f = req.file("profile_img")
            if f:
                imgerr = _save_profile_img(srv, char, f[1])
            char["updated"] = _now()
            store.save_character(srv, char)
        m = "imgerr" if imgerr else ("keysaved" if newkey else "saved")
        return redirect("/%s/c/%s?m=%s" % (srv, cid, m))
    if not sess:
        return _login_page(srv, char, tpath)
    return html_page("キャラクター編集",
                     _char_form(srv, tpath, char, auth.csrf_token(sess),
                                False, "保存する"),
                     back=back)


def char_album(req, srv, cid):
    char = store.get_character(srv, cid)
    if not char:
        return not_found()
    tpath = "/%s/c/%s/album" % (srv, cid)
    back = url("/%s/c/%s" % (srv, cid))
    sess = _get_session(req, srv, cid)
    error = ""
    if req.method == "POST":
        r = _handle_login(req, srv, char, tpath)
        if r:
            return r
        if not _csrf_ok(req, sess):
            return _login_page(srv, char, tpath, _EXPIRED)
        act = req.field("act")
        with store.lock(srv):
            char = store.get_character(srv, cid)
            if not char:
                return not_found()
            if act == "del":
                name = req.field("img")
                if re.fullmatch(r"a\d{2}\.jpg", name) and name in char.get("album", []):
                    char["album"].remove(name)
                    store.save_character(srv, char)
                    images.delete_image(srv, cid, name)
            else:
                f = req.file("photo")
                if not f:
                    error = "ファイルを選択してください"
                elif len(char.get("album", [])) >= config.MAX_ALBUM:
                    error = "アルバムは最大%d枚までです" % config.MAX_ALBUM
                else:
                    error = _rate_error(char)
                    if not error:
                        name = images.next_album_name(char["album"])
                        d = images.char_img_dir(srv, cid)
                        error = images.save_image(
                            f[1], os.path.join(d, name), os.path.join(d, "t_" + name))
                        if not error:
                            char["album"].append(name)
                            char["album"].sort()
                            char["upload_log"].append(int(time.time()))
                            char["updated"] = _now()
                    store.save_character(srv, char)
        if not error:
            return redirect(tpath)
    if not sess:
        return _login_page(srv, char, tpath)
    csrf = auth.csrf_token(sess)
    items = ""
    for name in char.get("album", []):
        items += """<div class="ph-item"><a class="ph" href="%s"><img src="%s" alt=""></a>
<form method="post" action="%s"><input type="hidden" name="csrf" value="%s">
<input type="hidden" name="act" value="del"><input type="hidden" name="img" value="%s">
<button class="btn danger small">削除</button></form></div>""" % (
            h(images.img_url(srv, cid, name)),
            h(images.img_url(srv, cid, "t_" + name)),
            h(url(tpath)), h(csrf), h(name))
    if not items:
        items = '<p class="empty">アルバムは空です</p>'
    if len(char.get("album", [])) < config.MAX_ALBUM:
        up = """<form method="post" action="%s" enctype="multipart/form-data" class="stack">
<input type="hidden" name="csrf" value="%s"><input type="hidden" name="act" value="add">
<label>画像を追加（JPEG/PNG/WebP・5MBまで）<input type="file" name="photo" accept="image/jpeg,image/png,image/webp" required></label>
<button class="btn primary">アップロード</button></form>""" % (h(url(tpath)), h(csrf))
    else:
        up = ('<p class="hint">上限（%d枚）に達しています。'
              '追加するには既存の画像を削除してください。</p>') % config.MAX_ALBUM
    body = tpl.errors_html([error]) + \
        '<p>%d / %d 枚</p><div class="album manage">%s</div><h2>追加</h2>%s' % (
            len(char.get("album", [])), config.MAX_ALBUM, items, up)
    return html_page("アルバム管理 - %s" % char["name"], body, back=back)


def event_page(req, srv, eid):
    ev = store.get_event(srv, eid)
    if not ev:
        return not_found()
    chars = store.list_characters(srv)
    byid = dict((c["id"], c) for c in chars)
    tpath = "/%s/e/%s" % (srv, eid)
    errors = []
    if req.method == "POST":
        if evutil.is_closed(ev):
            errors.append("このイベントは締め切られています")
        cid = req.field("char_id")
        choice = req.field("choice")
        char = byid.get(cid)
        if not errors:
            if not char:
                errors.append("キャラクターを選択してください")
            elif choice != "__cancel__" and choice not in ev.get("choices", []):
                errors.append("参加区分を選択してください")
        newsession = False
        if not errors and not _get_session(req, srv, cid):
            key = req.field("edit_key")
            lmsg = throttle.locked_message(char)
            if lmsg:
                errors.append(lmsg)
            elif key and auth.verify_key(char, key):
                newsession = True
                throttle.clear_char_fails(srv, cid)
            else:
                if key:
                    throttle.note_char_fail(srv, cid,
                                            req.environ.get("REMOTE_ADDR"))
                errors.append("編集キーが違います（この端末で初めて操作するキャラクターは編集キーが必要です）")
        if not errors:
            with store.lock(srv):
                ev2 = store.get_event(srv, eid)
                if ev2:
                    ev2.setdefault("entries", {})
                    if choice == "__cancel__":
                        ev2["entries"].pop(cid, None)
                    else:
                        ev2["entries"][cid] = {"choice": choice, "updated": _now()}
                    store.save_event(srv, ev2)
            resp = redirect(tpath + "?m=joined&c=" + cid)
            if newsession:
                _set_session(resp, srv, cid)
            return resp
    return _event_view(req, srv, ev, chars, byid, errors)


def _event_view(req, srv, ev, chars, byid, errors):
    note = ""
    if not errors:
        msg = _MSG.get(req.q("m"), "")
        if req.q("m") == "joined":
            c = byid.get(req.q("c"))
            if c:
                msg = "「%s」の参加情報を更新しました" % c["name"]
        note = tpl.notice(msg)
    closed = evutil.is_closed(ev)
    state = ('<span class="tag closed">締切</span>' if closed
             else '<span class="tag open">受付中</span>')
    bodytext = "<br>".join(h(line) for line in (ev.get("body") or "").splitlines())
    entries = ev.get("entries") or {}

    groups = ""
    for choice in ev.get("choices", []):
        names = []
        for cid, ent in sorted(entries.items()):
            if ent.get("choice") == choice:
                c = byid.get(cid)
                if c:
                    names.append('<a href="%s">%s</a>' % (
                        h(url("/%s/c/%s" % (srv, cid))), h(c["name"])))
                else:
                    names.append("（削除済み）")
        groups += "<tr><th>%s（%d）</th><td>%s</td></tr>" % (
            h(choice), len(names), "、".join(names) or "-")

    shift_html = ""
    if (ev.get("shift") or {}).get("enabled"):
        def member_html(c, is_captain):
            return '<a href="%s">%s</a><span class="sub">(%s)</span>%s' % (
                h(url("/%s/c/%s" % (srv, c["id"]))), h(c["name"]),
                tpl.fmt_num(c.get("march_size") or 0),
                '<span class="cap">（キャプテン）</span>' if is_captain else "")

        shift_html = ('<h2>予想シフト表</h2>'
                      '<p class="hint">参加登録から自動で振り分けています'
                      '（登録が変わると振り分けも変わります）。各対象の合計は'
                      'キャプテンの部隊+ギャザー規模が上限で、入り切らない場合は'
                      '補欠になります。</p>')
        for label, buckets, reserves in shift.tables(ev, byid):
            srows = ""
            for b in buckets:
                mem = "、".join(member_html(c, c["id"] == b.get("captain"))
                                for c in b["members"]) or "-"
                cap = tpl.fmt_num(b["cap"]) if b["members"] else "-"
                srows += ('<tr><th>%s %s<br><span class="sub">%d人 ／ 合計 %s'
                          '<br>上限 %s</span></th><td>%s</td></tr>') % (
                    h(b["name"]), tpl.troop_badge(b["troop"]),
                    len(b["members"]), tpl.fmt_num(b["total"]), cap, mem)
            if reserves:
                mem = "、".join(member_html(c, False) for c in reserves)
                srows += ('<tr><th>補欠<br><span class="sub">%d人</span></th>'
                          '<td>%s</td></tr>') % (len(reserves), mem)
            if label:
                shift_html += '<h3 class="shift-slot">%s</h3>' % h(label)
            shift_html += '<table class="kv shift-table">%s</table>' % srows

    form = ""
    if not closed and chars:
        mine = _my_sessions(req, srv, chars)
        if req.method == "POST":
            sel_cid = req.field("char_id")
        elif mine:
            sel_cid = max(mine, key=mine.get)  # 最後に認証したキャラを初期選択
        else:
            sel_cid = ""

        def opt(c):
            cur = entries.get(c["id"], {}).get("choice")
            mark = "／現在: %s" % cur if cur else ""
            return '<option value="%s"%s>%s%s</option>' % (
                h(c["id"]), " selected" if c["id"] == sel_cid else "",
                h(c["name"]), h(mark))

        opts = '<option value="">選択してください</option>'
        authed = [c for c in chars if c["id"] in mine]
        others = [c for c in chars if c["id"] not in mine]
        if authed:
            opts += ('<optgroup label="認証済み（編集キー不要）">%s</optgroup>'
                     % "".join(opt(c) for c in authed))
            if others:
                opts += ('<optgroup label="その他（編集キーが必要）">%s</optgroup>'
                         % "".join(opt(c) for c in others))
        else:
            opts += "".join(opt(c) for c in others)
        radios = ""
        for ch in ev.get("choices", []):
            radios += ('<label class="radio"><input type="radio" name="choice" '
                       'value="%s" required> %s</label>') % (h(ch), h(ch))
        radios += ('<label class="radio"><input type="radio" name="choice" '
                   'value="__cancel__"> 参加登録を取り消す</label>')
        form = """<h2>参加登録</h2>
<form method="post" action="%s" class="stack">
<label>キャラクター<select name="char_id" required>%s</select></label>
<div class="radios">%s</div>
<label>編集キー<input type="password" name="edit_key" placeholder="認証済みの端末では不要"></label>
<button class="btn primary">登録する</button>
</form>""" % (h(url("/%s/e/%s" % (srv, ev["id"]))), opts, radios)
    elif not chars:
        form = '<p class="hint">参加登録にはまずキャラクター登録が必要です。</p>'

    info = '<p class="ev-head">%s <span class="ev-date">開催: %s</span>' % (
        state, h(evutil.date_str(ev) or "-"))
    if evutil.deadline_str(ev):
        info += ' <span class="ev-date">受付締切: %s</span>' % h(evutil.deadline_str(ev))
    info += "</p>"
    links = ""
    if ev.get("published") or closed:
        links = '<p><a class="btn" href="%s">発表シフト</a>' % h(
            url("/%s/e/%s/shift" % (srv, ev["id"])))
        if ev.get("published"):
            links += ' <a class="btn" href="%s">報酬分配リスト</a>' % h(
                url("/%s/e/%s/rewards" % (srv, ev["id"])))
        links += "</p>"

    body = note + tpl.errors_html(errors) + """
%s
<p>%s</p>
%s
<h2>参加状況（%d件）</h2>
<table class="kv">%s</table>
%s
%s""" % (info, bodytext, links, len(entries), groups, shift_html, form)
    return html_page(ev["title"], body, back=url("/%s/" % srv))


ROUTES = [
    ("GET", r"/", home),
    ("GET", r"/(\d{4})/?", server_top),
    ("GET", r"/(\d{4})/new", char_new),
    ("POST", r"/(\d{4})/new", char_new),
    ("GET", r"/(\d{4})/c/([a-z0-9]{8})", char_detail),
    ("GET", r"/(\d{4})/c/([a-z0-9]{8})/edit", char_edit),
    ("POST", r"/(\d{4})/c/([a-z0-9]{8})/edit", char_edit),
    ("GET", r"/(\d{4})/c/([a-z0-9]{8})/album", char_album),
    ("POST", r"/(\d{4})/c/([a-z0-9]{8})/album", char_album),
    ("GET", r"/(\d{4})/e/([a-z0-9]{8})", event_page),
    ("POST", r"/(\d{4})/e/([a-z0-9]{8})", event_page),
]
