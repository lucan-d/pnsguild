"""管理側（PC基準）の画面。認証は Apache の Basic 認証（admin/.htaccess）前提。"""
import os
import re
import time

from lib import auth, config, evutil, images, store, tpl
from lib import shift as shiftmod
from lib.forms import validate_char
from lib.tpl import h
from lib.web import html_page, not_found, redirect


def aurl(path):
    return config.BASE + "/admin" + path


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _page(title, body, back=None):
    return html_page("[管理] " + title, body, back=back, wide=True)


def _csrf_input():
    return '<input type="hidden" name="csrf" value="%s">' % h(auth.admin_csrf())


def _csrf_ok(req):
    return auth.check_admin_csrf(req.field("csrf"))


def _deny(msg="不正なリクエストです（フォームを開き直してください）"):
    return _page("エラー", "<p>%s</p>" % h(msg))


def home(req):
    servers = store.load_servers()
    rows = ""
    for num in sorted(servers):
        rows += ('<tr><td><a href="%s">#%s</a></td><td>%s</td>'
                 '<td class="num">%d</td><td>%s</td></tr>') % (
            h(aurl("/%s" % num)), h(num), h(servers[num].get("name") or ""),
            len(store.list_characters(num)), h(servers[num].get("created") or ""))
    if not rows:
        rows = '<tr><td colspan="4">サーバー未登録</td></tr>'
    body = """
<h2>サーバー一覧</h2>
<table class="list"><tr><th>番号</th><th>表示名</th><th>キャラクター数</th><th>登録日</th></tr>%s</table>
<h2>新規サーバー登録</h2>
<form method="post" action="%s" class="inline">%s
<input type="text" name="num" pattern="\\d{4}" maxlength="4" placeholder="4桁番号" required>
<input type="text" name="name" maxlength="30" placeholder="表示名（任意）">
<button class="btn primary">登録</button>
</form>""" % (rows, h(aurl("/servers")), _csrf_input())
    return _page("トップ", body)


def server_create(req):
    if not _csrf_ok(req):
        return _deny()
    num = req.field("num")
    if not re.fullmatch(r"\d{4}", num):
        return _deny("サーバー番号は数字4桁です")
    name = req.field("name")[:30]
    with store.lock():
        servers = store.load_servers()
        if num not in servers:
            servers[num] = {"name": name or ("s" + num),
                            "created": time.strftime("%Y-%m-%d")}
            store.save_servers(servers)
    return redirect("/admin/")


def server_view(req, srv):
    servers = store.load_servers()
    if srv not in servers:
        return not_found()
    notices = []
    if req.method == "POST":
        if not _csrf_ok(req):
            return _deny()
        name = req.field("name")[:30]
        with store.lock():
            servers = store.load_servers()
            if srv in servers:
                servers[srv]["name"] = name or ("s" + srv)
                store.save_servers(servers)
        notices.append("表示名を変更しました")
    chars = store.list_characters(srv)
    rows = ""
    for c in chars:
        img = ""
        if c.get("has_profile_img"):
            img = '<img class="mini" src="%s" alt="">' % h(
                images.img_url(srv, c["id"], "t_profile.jpg"))
        rows += ("""<tr><td>%s</td><td><a href="%s">%s</a></td><td>%s</td><td>%s</td>
<td class="num">%s</td><td class="num">%s</td><td>%s</td><td class="num">%d</td><td>%s</td></tr>""") % (
            img, h(aurl("/%s/c/%s" % (srv, c["id"]))), h(c["name"]),
            h(c.get("guild") or ""), h(c.get("troop_type") or ""),
            h(tpl.fmt_march(c.get("march_size"), c.get("tier"))),
            h(tpl.fmt_num(c.get("gather_size"))),
            h(c.get("shelter") or ""), len(c.get("album") or []),
            h((c.get("updated") or "").replace("T", " ")))
    if not rows:
        rows = '<tr><td colspan="9">キャラクター未登録</td></tr>'
    body = "".join(tpl.notice(n) for n in notices) + """
<p><a href="%s">イベント管理</a> ／ <a href="%s">公開ページを見る</a></p>
<h2>サーバー情報</h2>
<form method="post" action="%s" class="inline">%s
<label>表示名 <input type="text" name="name" maxlength="30" value="%s"></label>
<button class="btn">変更</button>
</form>
<h2>キャラクター一覧</h2>
<table class="list">
<tr><th></th><th>名前</th><th>ギルド</th><th>兵種</th><th>部隊</th><th>ギャザー</th><th>座標</th><th>画像</th><th>更新</th></tr>
%s</table>""" % (h(aurl("/%s/events" % srv)), h(tpl.url("/%s/" % srv)),
                 h(aurl("/%s" % srv)), _csrf_input(),
                 h(servers[srv].get("name") or ""), rows)
    return _page("サーバー #%s" % srv, body, back=aurl("/"))


def char_edit(req, srv, cid):
    char = store.get_character(srv, cid)
    if not char:
        return not_found()
    notices = []
    errors = []
    if req.method == "POST":
        if not _csrf_ok(req):
            return _deny()
        data, errors = validate_char(req)
        newkey = req.field("new_key")
        if newkey and len(newkey) < config.MIN_KEY_LEN:
            errors.append("新しい編集キーは%d文字以上にしてください" % config.MIN_KEY_LEN)
        if not errors:
            with store.lock(srv):
                char = store.get_character(srv, cid)
                if not char:
                    return not_found()
                char.update(data)
                if newkey:
                    char["key_salt"] = auth.new_salt()
                    char["key_hash"] = auth.hash_key(char["key_salt"], newkey)
                    notices.append("編集キーを再設定しました")
                if req.field("del_profile"):
                    images.delete_image(srv, cid, "profile.jpg")
                    char["has_profile_img"] = False
                for name in req.fieldlist("del_img"):
                    if name in char.get("album", []):
                        char["album"].remove(name)
                        images.delete_image(srv, cid, name)
                f = req.file("profile_img")
                if f:
                    d = images.char_img_dir(srv, cid)
                    e = images.save_image(f[1], os.path.join(d, "profile.jpg"),
                                          os.path.join(d, "t_profile.jpg"))
                    if e:
                        errors.append(e)
                    else:
                        char["has_profile_img"] = True
                char["updated"] = _now()
                store.save_character(srv, char)
            notices.append("保存しました")

    def v(k):
        x = char.get(k)
        return h("" if x is None else x)

    opts = "".join(
        '<option value="%s"%s>%s</option>'
        % (t, " selected" if char.get("troop_type") == t else "", t)
        for t in config.TROOP_TYPES)
    imgs = ""
    if char.get("has_profile_img"):
        imgs += """<div class="ph-item"><img src="%s" alt="">
<label><input type="checkbox" name="del_profile" value="1"> プロフィール画像を削除</label></div>""" % h(
            images.img_url(srv, cid, "t_profile.jpg"))
    for name in char.get("album", []):
        imgs += """<div class="ph-item"><a href="%s"><img src="%s" alt=""></a>
<label><input type="checkbox" name="del_img" value="%s"> 削除</label></div>""" % (
            h(images.img_url(srv, cid, name)),
            h(images.img_url(srv, cid, "t_" + name)), h(name))
    if not imgs:
        imgs = '<p class="empty">画像なし</p>'
    body = "".join(tpl.notice(n) for n in notices) + tpl.errors_html(errors) + """
<form method="post" action="%s" enctype="multipart/form-data" class="stack admin-form">%s
<label>キャラクター名 *<input type="text" name="name" maxlength="30" value="%s" required></label>
<label>ギルド名<input type="text" name="guild" maxlength="30" value="%s"></label>
<label>特化兵種<select name="troop_type">%s</select></label>
<label>Tier（兵種ティア）<input type="text" name="tier" value="%s"></label>
<label>部隊規模<input type="text" name="march_size" value="%s"></label>
<label>ギャザー規模<input type="text" name="gather_size" value="%s"></label>
<label>避難所座標<input type="text" name="shelter" value="%s"></label>
<label>編集キー再設定（入力した場合のみ変更）<input type="text" name="new_key" autocomplete="off"></label>
<label>プロフィール画像差し替え<input type="file" name="profile_img"></label>
<h2>投稿画像</h2>
<div class="album manage">%s</div>
<button class="btn primary">保存する</button>
</form>
<h2>削除</h2>
<form method="post" action="%s">%s
<label><input type="checkbox" name="confirm" value="1" required> このキャラクターと全画像を完全に削除する</label>
<button class="btn danger">削除実行</button>
</form>""" % (h(aurl("/%s/c/%s" % (srv, cid))), _csrf_input(),
              v("name"), v("guild"), opts, v("tier"), v("march_size"),
              v("gather_size"), v("shelter"), imgs,
              h(aurl("/%s/c/%s/delete" % (srv, cid))), _csrf_input())
    return _page("%s（#%s）" % (char["name"], srv), body, back=aurl("/%s" % srv))


def char_delete(req, srv, cid):
    if not _csrf_ok(req) or req.field("confirm") != "1":
        return _deny("削除には確認チェックが必要です")
    with store.lock(srv):
        store.delete_character(srv, cid)
    images.delete_char_images(srv, cid)
    return redirect("/admin/%s" % srv)


def _shift_form_part(shift, choices, smap):
    """イベントフォームのシフト設定部分（対象の兵種 + 区分ごとの集計の扱い）。"""
    targets = (shift or {}).get("targets") or shiftmod.default_targets()
    rows = ""
    for i, tg in enumerate(targets):
        opts = "".join(
            '<option value="%s"%s>%s</option>'
            % (t, " selected" if tg.get("troop") == t else "", t)
            for t in config.TROOP_TYPES)
        rows += ('<tr><td>%s<input type="hidden" name="shift_name_%d" value="%s"></td>'
                 '<td><select name="shift_troop_%d">%s</select></td></tr>') % (
            h(tg["name"]), i, h(tg["name"]), i, opts)
    srows = ""
    for i, ch in enumerate(choices):
        cur = smap.get(ch) or shiftmod.guess_slot(ch)
        opts = "".join(
            '<option value="%s"%s>%s</option>'
            % (v, " selected" if v == cur else "", label)
            for v, label in shiftmod.SLOT_CHOICES)
        srows += ('<tr><td>%s<input type="hidden" name="slot_name_%d" value="%s"></td>'
                  '<td><select name="slot_%d">%s</select></td></tr>') % (
            h(ch), i, h(ch), i, opts)
    return """
<label><input type="checkbox" name="shift_on" value="1"%s>
 予想シフト表を使う（参加登録者を部隊規模がほぼ均等になるように自動振り分け）</label>
<table class="list shift-conf">
<tr><th>シフト対象</th><th>兵種</th></tr>%s</table>
<table class="list shift-conf">
<tr><th>参加区分</th><th>シフト集計での扱い</th></tr>%s</table>
<p class="hint">「前半」「後半」がある区分では前半・後半の2つのシフト表が作られます。
区分テキストを変更・追加した場合の扱いは自動判定（「前半」「後半」「不参加」を
含むかで判定）となるので、保存後にこの欄で調整してください。</p>
""" % (" checked" if (shift or {}).get("enabled") else "", rows, srows)


def _parse_shift(req, choices):
    targets = []
    for i in range(20):
        name = req.field("shift_name_%d" % i)
        if not name:
            break
        troop = req.field("shift_troop_%d" % i)
        if troop not in config.TROOP_TYPES:
            troop = "Fighter"
        targets.append({"name": name[:20], "troop": troop})
    if not targets:
        targets = shiftmod.default_targets()
    posted = {}
    for i in range(20):
        name = req.field("slot_name_%d" % i)
        if not name:
            break
        v = req.field("slot_%d" % i)
        if v in shiftmod.SLOT_VALUES:
            posted[name] = v
    slots = {ch: (posted.get(ch) or shiftmod.guess_slot(ch)) for ch in choices}
    return {"enabled": bool(req.field("shift_on")),
            "targets": targets, "slots": slots}


def _parse_choices(text, errors):
    items = [ln.strip() for ln in text.splitlines() if ln.strip()]
    items = list(dict.fromkeys(items))[:8]
    if not items:
        errors.append("参加区分を1つ以上入力してください")
    if any(len(i) > 20 for i in items):
        errors.append("参加区分は各20文字以内にしてください")
    return items


def _parse_dates(req, errors):
    """開催日時・受付締切を検証して (date_at, deadline_at) を返す。"""
    date_at = req.field("date_at")
    if date_at and evutil.parse_dt(date_at) is None:
        errors.append("開催日時の形式が不正です")
        date_at = ""
    deadline = req.field("deadline_at")
    if deadline and evutil.parse_dt(deadline) is None:
        errors.append("受付締切の形式が不正です")
        deadline = ""
    if not deadline and date_at:
        deadline = evutil.default_deadline(date_at)
    return date_at, deadline


def _date_form_part(ev):
    legacy = ""
    if (ev or {}).get("date") and not (ev or {}).get("date_at"):
        legacy = ('<p class="hint">旧形式の開催日時「%s」が設定されています。'
                  '下の欄で設定し直すと締切の自動計算が有効になります。</p>'
                  % h(ev["date"]))
    return legacy + """
<label>開催日時<input type="datetime-local" name="date_at" value="%s"></label>
<label>受付締切（空欄なら開催の%d時間前を自動設定）<input type="datetime-local" name="deadline_at" value="%s"></label>
<label>ホストパスワード（発表シフト編集用%s）<input type="text" name="host_pass" autocomplete="off"></label>
""" % (h((ev or {}).get("date_at") or ""), evutil.DEADLINE_HOURS,
       h((ev or {}).get("deadline_at") or ""),
       "・設定済み、入力時のみ変更" if (ev or {}).get("host_hash") else "・任意")


def events(req, srv):
    if not store.server_exists(srv):
        return not_found()
    errors = []
    if req.method == "POST":
        if not _csrf_ok(req):
            return _deny()
        title = req.field("title")
        if not title or len(title) > 50:
            errors.append("タイトルは1〜50文字で入力してください")
        choices = _parse_choices(req.field("choices"), errors)
        date_at, deadline = _parse_dates(req, errors)
        if not errors:
            ev = {"id": "", "title": title, "body": req.field("body")[:2000],
                  "date_at": date_at, "deadline_at": deadline,
                  "choices": choices, "shift": _parse_shift(req, choices),
                  "closed": False, "entries": {}, "created": _now()}
            hp = req.field("host_pass")
            if hp:
                ev["host_salt"] = auth.new_salt()
                ev["host_hash"] = auth.hash_key(ev["host_salt"], hp)
            with store.lock(srv):
                ev["id"] = store.new_event_id(srv)
                store.save_event(srv, ev)
            return redirect("/admin/%s/events" % srv)
    rows = ""
    for e in store.list_events(srv):
        state = "締切" if evutil.is_closed(e) else "受付中"
        if e.get("published"):
            state += "・発表済"
        rows += ('<tr><td><a href="%s">%s</a></td><td>%s</td><td>%s</td><td>%s</td>'
                 '<td class="num">%d</td></tr>') % (
            h(aurl("/%s/e/%s" % (srv, e["id"]))), h(e["title"]),
            h(evutil.date_str(e)), h(evutil.deadline_str(e)), state,
            len(e.get("entries") or {}))
    if not rows:
        rows = '<tr><td colspan="6">イベントなし</td></tr>'
    body = tpl.errors_html(errors) + """
<table class="list"><tr><th>タイトル</th><th>開催日時</th><th>受付締切</th><th>状態</th><th>参加登録</th></tr>%s</table>
<h2>新規イベント</h2>
<form method="post" action="%s" class="stack admin-form">%s
<label>タイトル *<input type="text" name="title" maxlength="50" required></label>
%s
<label>説明<textarea name="body" rows="4"></textarea></label>
<label>参加区分（1行に1つ・最大8）<textarea name="choices" rows="5">前半参加
後半参加
フルタイム
不参加</textarea></label>
%s
<button class="btn primary">作成</button>
</form>""" % (rows, h(aurl("/%s/events" % srv)), _csrf_input(),
              _date_form_part(None),
              _shift_form_part(None,
                               ["前半参加", "後半参加", "フルタイム", "不参加"], {}))
    return _page("イベント管理 #%s" % srv, body, back=aurl("/%s" % srv))


def event_edit(req, srv, eid):
    ev = store.get_event(srv, eid)
    if not ev:
        return not_found()
    errors = []
    notices = []
    if req.method == "POST":
        if not _csrf_ok(req):
            return _deny()
        if req.field("act") == "delete":
            if req.field("confirm") != "1":
                return _deny("削除には確認チェックが必要です")
            with store.lock(srv):
                store.delete_event(srv, eid)
            return redirect("/admin/%s/events" % srv)
        if req.field("act") == "discard_pub":
            if req.field("confirm") != "1":
                return _deny("破棄には確認チェックが必要です")
            with store.lock(srv):
                ev = store.get_event(srv, eid) or ev
                ev.pop("published", None)
                ev.pop("rewards", None)
                store.save_event(srv, ev)
            notices.append("発表シフトと報酬リストを破棄しました")
        else:
            title = req.field("title")
            if not title or len(title) > 50:
                errors.append("タイトルは1〜50文字で入力してください")
            choices = _parse_choices(req.field("choices"), errors)
            date_at, deadline = _parse_dates(req, errors)
            if not errors:
                with store.lock(srv):
                    ev = store.get_event(srv, eid) or ev
                    ev.update(title=title, body=req.field("body")[:2000],
                              date_at=date_at, deadline_at=deadline,
                              choices=choices,
                              shift=_parse_shift(req, choices),
                              closed=bool(req.field("closed")))
                    hp = req.field("host_pass")
                    if hp:
                        ev["host_salt"] = auth.new_salt()
                        ev["host_hash"] = auth.hash_key(ev["host_salt"], hp)
                    store.save_event(srv, ev)
                notices.append("保存しました")
    chars = dict((c["id"], c) for c in store.list_characters(srv))
    rows = ""
    for cid, ent in sorted((ev.get("entries") or {}).items()):
        c = chars.get(cid)
        rows += "<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (
            h(c["name"]) if c else "（削除済み）", h(ent.get("choice") or ""),
            h((ent.get("updated") or "").replace("T", " ")))
    if not rows:
        rows = '<tr><td colspan="3">参加登録なし</td></tr>'

    pub_url = tpl.url("/%s/e/%s/shift" % (srv, eid))
    if ev.get("published"):
        pub_html = """
<p>作成済み（%s）／ <a href="%s">公開ページを見る</a></p>
<form method="post" action="%s">%s
<input type="hidden" name="act" value="discard_pub">
<label><input type="checkbox" name="confirm" value="1" required>
 発表シフトと報酬リストを破棄する（作り直す場合）</label>
<button class="btn danger">破棄</button>
</form>""" % (h((ev["published"].get("created") or "").replace("T", " ")),
              h(pub_url), h(aurl("/%s/e/%s" % (srv, eid))), _csrf_input())
    else:
        pub_html = ('<p>未作成（受付締切後にホストが <a href="%s">発表シフトページ</a> '
                    'から作成します）</p>' % h(pub_url))
    body = "".join(tpl.notice(n) for n in notices) + tpl.errors_html(errors) + """
<form method="post" action="%s" class="stack admin-form">%s
<label>タイトル *<input type="text" name="title" maxlength="50" value="%s" required></label>
%s
<label>説明<textarea name="body" rows="4">%s</textarea></label>
<label>参加区分（1行に1つ）<textarea name="choices" rows="3">%s</textarea></label>
%s
<label><input type="checkbox" name="closed" value="1"%s> 締め切る（参加登録を受け付けない）</label>
<button class="btn primary">保存</button>
</form>
<h2>参加状況（%d件）</h2>
<table class="list"><tr><th>キャラクター</th><th>区分</th><th>更新</th></tr>%s</table>
<h2>発表シフト</h2>
%s
<h2>削除</h2>
<form method="post" action="%s">%s
<input type="hidden" name="act" value="delete">
<label><input type="checkbox" name="confirm" value="1" required> このイベントを削除する</label>
<button class="btn danger">削除実行</button>
</form>""" % (h(aurl("/%s/e/%s" % (srv, eid))), _csrf_input(),
              h(ev["title"]), _date_form_part(ev), h(ev.get("body") or ""),
              h("\n".join(ev.get("choices", []))),
              _shift_form_part(ev.get("shift"), ev.get("choices", []),
                               shiftmod.slot_map(ev)),
              " checked" if ev.get("closed") else "",
              len(ev.get("entries") or {}), rows, pub_html,
              h(aurl("/%s/e/%s" % (srv, eid))), _csrf_input())
    return _page("イベント: %s" % ev["title"], body,
                 back=aurl("/%s/events" % srv))


ROUTES = [
    ("GET", r"/", home),
    ("POST", r"/servers", server_create),
    ("GET", r"/(\d{4})/?", server_view),
    ("POST", r"/(\d{4})/?", server_view),
    ("GET", r"/(\d{4})/c/([a-z0-9]{8})", char_edit),
    ("POST", r"/(\d{4})/c/([a-z0-9]{8})", char_edit),
    ("POST", r"/(\d{4})/c/([a-z0-9]{8})/delete", char_delete),
    ("GET", r"/(\d{4})/events/?", events),
    ("POST", r"/(\d{4})/events/?", events),
    ("GET", r"/(\d{4})/e/([a-z0-9]{8})", event_edit),
    ("POST", r"/(\d{4})/e/([a-z0-9]{8})", event_edit),
]
