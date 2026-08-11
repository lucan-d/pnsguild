"""一般側（スマホ基準）の画面。"""
import os
import re
import time
import urllib.parse

from lib import auth, config, evutil, i18n, images, shift, store, throttle, tpl
from lib.forms import validate_char
from lib.tpl import h, url
from lib.web import html_page, not_found, redirect

_MSG = {
    "imgerr": "msg_imgerr",
    "saved": "msg_saved",
    "keysaved": "msg_keysaved",
    "joined": "msg_joined",
}


def _msg_for(code):
    key = _MSG.get(code)
    return i18n.t(key) if key else ""


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
<p>%s</p>
<form method="post" action="%s" class="stack">
<input type="password" name="login_key" placeholder="%s" required>
<button class="btn primary">%s</button>
</form>
<p class="hint">%s</p>
""" % (i18n.t("login_required_for", name=h(char["name"])), h(url(tpath)),
       i18n.t("edit_key_placeholder"), i18n.t("btn_login"),
       i18n.t("login_forgot_hint"))
    return html_page(i18n.t("title_login_confirm"), body,
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
    return _login_page(srv, char, tpath, i18n.t("err_login_key_wrong"))


def _csrf_ok(req, sess):
    return bool(sess) and req.field("csrf") == auth.csrf_token(sess)


def _expired_msg():
    return i18n.t("err_session_expired")


# ---------- 画像 ----------

def _rate_error(char):
    now = int(time.time())
    char["upload_log"] = [t for t in char.get("upload_log", []) if t > now - 3600]
    if len(char["upload_log"]) >= config.UPLOAD_RATE:
        return i18n.t("err_upload_rate")
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
<details class="mapbox"><summary class="btn small">%s</summary>
<div class="mapwrap">
<svg viewBox="0 0 1022 1023" class="hexmap" role="img" aria-label="%s">
<rect x="0" y="0" width="1022" height="1023" class="mapbg"/>
<g class="grid">%s</g>
<circle cx="%d" cy="%d" r="14" class="pt"/>
<text x="%d" y="%d" text-anchor="middle" class="ptlabel">%d,%d</text>
</svg>
<p class="hint">%s</p>
</div></details>""" % (i18n.t("shelter_map_toggle"), i18n.t("shelter_map_aria"),
                       grid, px, y, tx, ty, x, y, i18n.t("shelter_map_hint"))


def _char_card(srv, c):
    cid = c["id"]
    if c.get("has_profile_img"):
        img = '<img src="%s" alt="" loading="lazy">' % h(
            images.img_url(srv, cid, "t_profile.jpg"))
    else:
        img = '<div class="noimg">%s</div>' % h((c.get("name") or "?")[:1])
    guild = c.get("guild") or i18n.t("guild_none")
    return """<a class="char" href="%s">%s<div class="char-body">
<div class="char-name">%s %s</div>
<div class="char-sub">%s</div>
<div class="char-nums">%s</div>
</div></a>""" % (
        h(url("/%s/c/%s" % (srv, cid))), img, h(c["name"]),
        tpl.troop_badge(c.get("troop_type")), h(guild),
        i18n.t("char_card_nums",
               march=tpl.fmt_march(c.get("march_size"), c.get("tier")),
               gather=tpl.fmt_num(c.get("gather_size"))))


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
<label>%s<input type="password" name="edit_key" required></label>
<label>%s<input type="password" name="edit_key2" required></label>
""" % (i18n.t("label_edit_key_new", min=config.MIN_KEY_LEN),
       i18n.t("label_edit_key_confirm"))
    else:
        keypart = """
<h2>%s</h2>
<label>%s<input type="password" name="new_key"></label>
<label>%s<input type="password" name="new_key2"></label>
""" % (i18n.t("heading_change_key"),
       i18n.t("label_new_key", min=config.MIN_KEY_LEN),
       i18n.t("label_new_key_confirm"))
    imglabel = i18n.t("img_label_new")
    if c.get("has_profile_img"):
        imglabel = i18n.t("img_label_replace")
    return """
<form method="post" action="%s" enctype="multipart/form-data" class="stack">
<input type="hidden" name="csrf" value="%s">
<label>%s<input type="text" name="name" maxlength="30" value="%s" required></label>
<label>%s<input type="text" name="guild" maxlength="30" value="%s"></label>
<label>%s<select name="troop_type">%s</select></label>
<label>%s<input type="text" name="tier" inputmode="numeric" value="%s" placeholder="%s"></label>
<label>%s<input type="text" name="march_size" inputmode="numeric" value="%s" placeholder="%s"></label>
<label>%s<input type="text" name="gather_size" inputmode="numeric" value="%s"></label>
<label>%s<input type="text" name="shelter" value="%s" placeholder="%s"></label>
<label>%s<input type="file" name="profile_img" accept="image/jpeg,image/png,image/webp"></label>
%s
<button class="btn primary">%s</button>
</form>""" % (h(url(tpath)), h(csrf),
              i18n.t("label_char_name"), v("name"),
              i18n.t("label_guild"), v("guild"),
              i18n.t("label_troop_type"), opts,
              i18n.t("label_tier"), v("tier"), i18n.t("placeholder_tier_example"),
              i18n.t("field_march_size"), v("march_size"),
              i18n.t("placeholder_march_example"),
              i18n.t("field_gather_size"), v("gather_size"),
              i18n.t("label_shelter"), v("shelter"),
              i18n.t("placeholder_shelter_example"),
              imglabel, keypart, h(submit_label))


def _event_rows(srv, events):
    if not events:
        return '<p class="empty">%s</p>' % i18n.t("empty_no_events")
    out = '<ul class="events">'
    for e in events:
        mark = ('<span class="tag closed">%s</span>' % i18n.t("tag_closed")
                if evutil.is_closed(e) else "")
        out += ('<li><a href="%s"><span class="ev-date">%s</span> %s %s '
                '<span class="sub">%s</span></a></li>') % (
            h(url("/%s/e/%s" % (srv, e["id"]))), h(evutil.date_str(e)),
            h(e["title"]), mark,
            i18n.t("event_entries_count", n=len(e.get("entries") or {})))
    return out + "</ul>"


# ---------- ハンドラ ----------

def home(req):
    s = req.q("s").strip()
    if s and store.server_exists(s):
        return redirect("/%s/" % s)
    errors = []
    if s:
        errors.append(i18n.t("err_server_not_registered", num=s))
    servers = store.load_servers()
    items = ""
    for num in sorted(servers):
        items += ('<li><a class="card-link" href="%s">#%s '
                  '<span class="sub">%s</span></a></li>') % (
            h(url("/%s/" % num)), h(num), h(servers[num].get("name") or ""))
    if not items:
        items = '<li class="empty">%s</li>' % i18n.t("empty_no_servers")
    body = tpl.errors_html(errors) + """
<form method="get" action="%s" class="jump">
<input type="text" name="s" inputmode="numeric" pattern="\\d{4}" maxlength="4" placeholder="%s" required>
<button class="btn primary">%s</button>
</form>
<h2>%s</h2>
<ul class="cards">%s</ul>
<p class="hint github-link"><a href="%s" target="_blank" rel="noopener">%s</a></p>""" % (
        h(url("/")), i18n.t("placeholder_server_num"),
        i18n.t("btn_go"), i18n.t("heading_server_list"), items,
        h(config.GITHUB_URL), i18n.t("github_link"))
    return html_page(i18n.t("title_server_select"), body)


def server_top(req, srv):
    if not store.server_exists(srv):
        return not_found(i18n.t("err_server_not_registered", num=srv))
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
        tags += '<a class="tag clear" href="%s">%s</a>' % (
            h(url("/%s/" % srv)), i18n.t("tag_clear"))

    cards = "".join(_char_card(srv, c) for c in shown)
    if not cards:
        cards = '<p class="empty">%s</p>' % i18n.t("empty_no_chars")

    body = """
<p><a class="btn primary" href="%s">%s</a></p>
<h2>%s</h2>
%s
<h2>%s</h2>
<div class="tags">%s</div>
<div class="charlist">%s</div>""" % (
        h(url("/%s/new" % srv)), i18n.t("btn_char_new"), i18n.t("heading_events"),
        _event_rows(srv, store.list_events(srv)),
        i18n.t("heading_chars", n=len(shown)), tags, cards)
    return html_page(i18n.t("title_server_num", num=srv), body, back=url("/"))


def char_new(req, srv):
    if not store.server_exists(srv):
        return not_found()
    tpath = "/%s/new" % srv
    back = url("/%s/" % srv)
    if req.method == "GET":
        return html_page(i18n.t("title_char_new"),
                         _char_form(srv, tpath, {}, "", True, i18n.t("btn_register")),
                         back=back)
    data, errors = validate_char(req)
    key = req.field("edit_key")
    if len(key) < config.MIN_KEY_LEN:
        errors.append(i18n.t("err_key_too_short", min=config.MIN_KEY_LEN))
    elif key != req.field("edit_key2"):
        errors.append(i18n.t("err_key_confirm_mismatch"))
    if errors:
        return html_page(
            i18n.t("title_char_new"),
            tpl.errors_html(errors) + _char_form(
                srv, tpath, data, "", True, i18n.t("btn_register")),
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
    note = tpl.notice(_msg_for(req.q("m")))

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
        gl = i18n.t("guild_none")
    rows = ""
    for label, val in (
            (i18n.t("kv_guild"), gl),
            (i18n.t("kv_troop_type"), tpl.troop_badge(char.get("troop_type"))),
            (i18n.t("field_march_size"),
             h(tpl.fmt_march(char.get("march_size"), char.get("tier")))),
            (i18n.t("field_gather_size"), h(tpl.fmt_num(char.get("gather_size")))),
            (i18n.t("kv_shelter"), h(char.get("shelter") or "-")),
            (i18n.t("kv_updated"), h((char.get("updated") or "").replace("T", " ")))):
        rows += "<tr><th>%s</th><td>%s</td></tr>" % (label, val)

    album = ""
    for name in char.get("album", []):
        album += '<a class="ph" href="%s"><img src="%s" alt="" loading="lazy"></a>' % (
            h(images.img_url(srv, cid, name)),
            h(images.img_url(srv, cid, "t_" + name)))
    if not album:
        album = '<p class="empty">%s</p>' % i18n.t("empty_album")

    own = """
<div class="ownerbar">
<a class="btn" href="%s">%s</a>
<a class="btn" href="%s">%s</a>
</div>
<p class="hint">%s</p>""" % (
        h(url("/%s/c/%s/edit" % (srv, cid))), i18n.t("own_edit"),
        h(url("/%s/c/%s/album" % (srv, cid))), i18n.t("own_album"),
        i18n.t("own_hint"))

    smap = _shelter_map_html(char.get("shelter") or "")
    body = (note + '<div class="profile-wrap">%s</div><table class="kv">%s</table>%s'
            '<h2>%s</h2><div class="album">%s</div>%s') % (
        pi, rows, smap,
        i18n.t("heading_album", cur=len(char.get("album", [])), max=config.MAX_ALBUM),
        album, own)
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
            return _login_page(srv, char, tpath, _expired_msg())
        data, errors = validate_char(req)
        newkey = req.field("new_key")
        if newkey:
            if len(newkey) < config.MIN_KEY_LEN:
                errors.append(i18n.t("err_newkey_too_short", min=config.MIN_KEY_LEN))
            elif newkey != req.field("new_key2"):
                errors.append(i18n.t("err_newkey_confirm_mismatch"))
        if errors:
            return html_page(
                i18n.t("title_char_edit"),
                tpl.errors_html(errors) + _char_form(
                    srv, tpath, dict(char, **data),
                    auth.csrf_token(sess), False, i18n.t("btn_save")),
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
    return html_page(i18n.t("title_char_edit"),
                     _char_form(srv, tpath, char, auth.csrf_token(sess),
                                False, i18n.t("btn_save")),
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
            return _login_page(srv, char, tpath, _expired_msg())
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
                    error = i18n.t("err_select_file")
                elif len(char.get("album", [])) >= config.MAX_ALBUM:
                    error = i18n.t("err_album_max", max=config.MAX_ALBUM)
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
<button class="btn danger small">%s</button></form></div>""" % (
            h(images.img_url(srv, cid, name)),
            h(images.img_url(srv, cid, "t_" + name)),
            h(url(tpath)), h(csrf), h(name), i18n.t("btn_delete"))
    if not items:
        items = '<p class="empty">%s</p>' % i18n.t("empty_album")
    if len(char.get("album", [])) < config.MAX_ALBUM:
        up = """<form method="post" action="%s" enctype="multipart/form-data" class="stack">
<input type="hidden" name="csrf" value="%s"><input type="hidden" name="act" value="add">
<label>%s<input type="file" name="photo" accept="image/jpeg,image/png,image/webp" required></label>
<button class="btn primary">%s</button></form>""" % (
            h(url(tpath)), h(csrf), i18n.t("label_add_photo"), i18n.t("btn_upload"))
    else:
        up = '<p class="hint">%s</p>' % i18n.t("hint_album_full", max=config.MAX_ALBUM)
    body = tpl.errors_html([error]) + \
        '<p>%s</p><div class="album manage">%s</div><h2>%s</h2>%s' % (
            i18n.t("count_of", cur=len(char.get("album", [])), max=config.MAX_ALBUM),
            items, i18n.t("heading_add"), up)
    return html_page(i18n.t("title_album_manage", name=char["name"]), body, back=back)


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
            errors.append(i18n.t("err_event_closed"))
        cid = req.field("char_id")
        choice = req.field("choice")
        char = byid.get(cid)
        if not errors:
            if not char:
                errors.append(i18n.t("err_select_char"))
            elif choice != "__cancel__" and choice not in ev.get("choices", []):
                errors.append(i18n.t("err_select_choice"))
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
                errors.append(i18n.t("err_login_key_wrong_event"))
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
        msg = _msg_for(req.q("m"))
        if req.q("m") == "joined":
            c = byid.get(req.q("c"))
            if c:
                msg = i18n.t("msg_joined_named", name=c["name"])
        note = tpl.notice(msg)
    closed = evutil.is_closed(ev)
    state = ('<span class="tag closed">%s</span>' % i18n.t("tag_closed") if closed
             else '<span class="tag open">%s</span>' % i18n.t("tag_open"))
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
                    names.append(i18n.t("deleted_char"))
        groups += "<tr><th>%s（%d）</th><td>%s</td></tr>" % (
            h(choice), len(names), "、".join(names) or "-")

    shift_html = ""
    if (ev.get("shift") or {}).get("enabled"):
        def member_html(c, is_captain):
            return '<a href="%s">%s</a><span class="sub">(%s)</span>%s' % (
                h(url("/%s/c/%s" % (srv, c["id"]))), h(c["name"]),
                tpl.fmt_num(c.get("march_size") or 0),
                '<span class="cap">%s</span>' % i18n.t("label_captain") if is_captain else "")

        shift_html = ('<h2>%s</h2><p class="hint">%s</p>'
                     % (i18n.t("heading_forecast_shift"), i18n.t("forecast_hint")))
        for label, buckets, reserves in shift.tables(ev, byid):
            srows = ""
            for b in buckets:
                mem = "、".join(member_html(c, c["id"] == b.get("captain"))
                                for c in b["members"]) or "-"
                cap = tpl.fmt_num(b["cap"]) if b["members"] else "-"
                srows += ('<tr><th>%s %s<br><span class="sub">%s'
                          '<br>%s</span></th><td>%s</td></tr>') % (
                    h(b["name"]), tpl.troop_badge(b["troop"]),
                    i18n.t("forecast_count_total", n=len(b["members"]),
                           total=tpl.fmt_num(b["total"])),
                    i18n.t("forecast_cap", cap=cap),
                    mem)
            if reserves:
                mem = "、".join(member_html(c, False) for c in reserves)
                srows += ('<tr><th>%s<br><span class="sub">%s</span></th>'
                          '<td>%s</td></tr>') % (
                    i18n.t("reserve_heading"), i18n.t("reserve_count", n=len(reserves)), mem)
            if label:
                shift_html += '<h3 class="shift-slot">%s</h3>' % i18n.t("slot_" + label)
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
            mark = i18n.t("current_choice_mark", cur=cur) if cur else ""
            return '<option value="%s"%s>%s%s</option>' % (
                h(c["id"]), " selected" if c["id"] == sel_cid else "",
                h(c["name"]), h(mark))

        opts = '<option value="">%s</option>' % i18n.t("select_placeholder")
        authed = [c for c in chars if c["id"] in mine]
        others = [c for c in chars if c["id"] not in mine]
        if authed:
            opts += ('<optgroup label="%s">%s</optgroup>'
                     % (i18n.t("optgroup_authed"), "".join(opt(c) for c in authed)))
            if others:
                opts += ('<optgroup label="%s">%s</optgroup>'
                         % (i18n.t("optgroup_others"), "".join(opt(c) for c in others)))
        else:
            opts += "".join(opt(c) for c in others)
        radios = ""
        for ch in ev.get("choices", []):
            radios += ('<label class="radio"><input type="radio" name="choice" '
                       'value="%s" required> %s</label>') % (h(ch), h(ch))
        radios += ('<label class="radio"><input type="radio" name="choice" '
                   'value="__cancel__"> %s</label>') % i18n.t("radio_cancel")
        form = """<h2>%s</h2>
<form method="post" action="%s" class="stack">
<label>%s<select name="char_id" required>%s</select></label>
<div class="radios">%s</div>
<label>%s<input type="password" name="edit_key" placeholder="%s"></label>
<button class="btn primary">%s</button>
</form>""" % (i18n.t("heading_participation"), h(url("/%s/e/%s" % (srv, ev["id"]))),
              i18n.t("select_char_label"), opts, radios,
              i18n.t("edit_key_placeholder"), i18n.t("placeholder_edit_key_authed"),
              i18n.t("btn_register_participation"))
    elif not chars:
        form = '<p class="hint">%s</p>' % i18n.t("hint_need_char_first")

    info = '<p class="ev-head">%s <span class="ev-date">%s</span>' % (
        state, i18n.t("ev_head_open_date", date=h(evutil.date_str(ev) or "-")))
    if evutil.deadline_str(ev):
        info += ' <span class="ev-date">%s</span>' % i18n.t(
            "ev_head_deadline", date=h(evutil.deadline_str(ev)))
    info += "</p>"
    links = ""
    if ev.get("published") or closed:
        links = '<p><a class="btn" href="%s">%s</a>' % (
            h(url("/%s/e/%s/shift" % (srv, ev["id"]))), i18n.t("link_published_shift"))
        if ev.get("published"):
            links += ' <a class="btn" href="%s">%s</a>' % (
                h(url("/%s/e/%s/rewards" % (srv, ev["id"]))), i18n.t("link_rewards"))
        links += "</p>"

    body = note + tpl.errors_html(errors) + """
%s
<p>%s</p>
%s
<h2>%s</h2>
<table class="kv">%s</table>
%s
%s""" % (info, bodytext, links, i18n.t("heading_participation_status", n=len(entries)),
         groups, shift_html, form)
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
