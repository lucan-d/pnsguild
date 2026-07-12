"""発表シフトと報酬分配リスト（イベントホスト向け機能）。

閲覧は全員可。作成・編集（任命・移動・出席・色変更）はホストパスワード
認証（キャラクターの編集キーと同じ署名Cookie方式）が必要。
発表シフトは受付締切後に予想シフトから生成して保存し、以後は手動調整のみ。
"""
import time

from lib import auth, config, evutil, shift, store, throttle, tpl
from lib.tpl import h, url
from lib.web import html_page, not_found, redirect

REWARD_COLORS = (("red", "赤", 1), ("blue", "青", 5),
                 ("green", "緑", 20), ("yellow", "薄黄", 74))
SLOT_LABELS = {"first": "前半", "second": "後半", "all": "全体"}


def _now():
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _march(c):
    return c.get("march_size") or 0


# ---------- ホスト認証 ----------

def _host_sess(req, srv, eid):
    tok = req.cookie(auth.host_cookie_name(srv, eid))
    if tok and auth.check_host_session(tok, srv, eid):
        return tok
    return None


def _login_page(srv, ev, tpath, error=""):
    back = url("/%s/e/%s" % (srv, ev["id"]))
    if not ev.get("host_hash"):
        return html_page("ホスト認証",
                         "<p>このイベントにはホストパスワードが設定されていません。"
                         "管理者に設定を依頼してください。</p>", back=back)
    body = tpl.errors_html([error]) + """
<p>「%s」のホスト操作にはホストパスワードが必要です。</p>
<form method="post" action="%s" class="stack">
<input type="password" name="host_pass" placeholder="ホストパスワード" required>
<button class="btn primary">認証する</button>
</form>""" % (h(ev["title"]), h(url(tpath)))
    return html_page("ホスト認証", body, back=back)


def _handle_host_login(req, srv, ev, tpath):
    fields, _ = req.form()
    if "host_pass" not in fields:
        return None
    lmsg = throttle.locked_message(ev)
    if lmsg:
        return _login_page(srv, ev, tpath, lmsg)
    if auth.verify_host(ev, req.field("host_pass")):
        throttle.clear_event_fails(srv, ev["id"])
        resp = redirect(tpath)
        resp.set_cookie(auth.host_cookie_name(srv, ev["id"]),
                        auth.make_host_session(srv, ev["id"]),
                        config.SESSION_DAYS * 86400)
        return resp
    throttle.note_event_fail(srv, ev["id"],
                             req.environ.get("REMOTE_ADDR"))
    return _login_page(srv, ev, tpath, "パスワードが違います")


def _csrf_ok(req, sess):
    return bool(sess) and req.field("csrf") == auth.csrf_token(sess)


# ---------- 発表シフトの生成 ----------

def build_published(ev, byid):
    slots = {}
    for label, buckets, _reserves in shift.tables(ev, byid):
        key = {"前半": "first", "後半": "second", None: "all"}[label]
        slots[key] = {"targets": [
            {"name": b["name"], "troop": b["troop"],
             "members": [c["id"] for c in b["members"]],
             "captain": b.get("captain"), "sub": None}
            for b in buckets]}
    return {"created": _now(), "slots": slots}


# ---------- 発表シフト画面 ----------

def shift_page(req, srv, eid):
    ev = store.get_event(srv, eid)
    if not ev:
        return not_found()
    byid = dict((c["id"], c) for c in store.list_characters(srv))
    tpath = "/%s/e/%s/shift" % (srv, eid)
    sess = _host_sess(req, srv, eid)

    if req.method == "POST":
        r = _handle_host_login(req, srv, ev, tpath)
        if r:
            return r
        if not _csrf_ok(req, sess):
            return _login_page(srv, ev, tpath, "セッションの有効期限が切れました。もう一度認証してください")
        return _shift_action(req, srv, eid, byid, tpath)

    if req.q("login") and not sess:
        return _login_page(srv, ev, tpath)

    back = url("/%s/e/%s" % (srv, eid))
    if not ev.get("published"):
        if not evutil.is_closed(ev):
            body = ('<p>発表シフトは受付締切後に作成できます。</p>'
                    '<p class="hint">受付締切: %s</p>') % h(evutil.deadline_str(ev) or "未設定（手動締切待ち）")
            return html_page("発表シフト - %s" % ev["title"], body, back=back)
        if sess:
            body = """
<p>受付は締め切られています。現在の予想シフトを元に発表シフトを作成します。
作成後は参加登録の変動に影響されず、手動で調整できます。</p>
<form method="post" action="%s">
<input type="hidden" name="csrf" value="%s">
<input type="hidden" name="act" value="create">
<button class="btn primary">発表シフトを作成する</button>
</form>""" % (h(url(tpath)), h(auth.csrf_token(sess)))
        else:
            body = ('<p>発表シフトはまだ作成されていません。</p>'
                    '<p><a class="btn" href="%s?login=1">ホストとして作成する</a></p>'
                    % h(url(tpath)))
        return html_page("発表シフト - %s" % ev["title"], body, back=back)

    return _render_shift(req, srv, ev, byid, sess, tpath)


def _find_member(targets, cid):
    for i, t in enumerate(targets):
        if cid in t["members"]:
            return i
    return None


def _shift_action(req, srv, eid, byid, tpath):
    act = req.field("act")
    slot = req.field("slot")
    cid = req.field("cid")
    with store.lock(srv):
        ev = store.get_event(srv, eid)
        if not ev:
            return not_found()
        if act == "create":
            if evutil.is_closed(ev) and not ev.get("published"):
                ev["published"] = build_published(ev, byid)
                store.save_event(srv, ev)
            return redirect(tpath)
        pub = ev.get("published")
        if not pub or slot not in pub.get("slots", {}):
            return redirect(tpath)
        targets = pub["slots"][slot]["targets"]

        def unplace(cid):
            i = _find_member(targets, cid)
            if i is not None:
                targets[i]["members"].remove(cid)
                if targets[i].get("captain") == cid:
                    targets[i]["captain"] = None
                if targets[i].get("sub") == cid:
                    targets[i]["sub"] = None

        if act in ("captain", "sub"):
            try:
                t = targets[int(req.field("target"))]
            except (ValueError, IndexError):
                return redirect(tpath)
            if cid in t["members"]:
                if act == "captain":
                    t["captain"] = cid
                    if t.get("sub") == cid:
                        t["sub"] = None
                else:
                    t["sub"] = cid
                    if t.get("captain") == cid:
                        t["captain"] = None
        elif act in ("move", "add"):
            try:
                dest = int(req.field("to"))
            except ValueError:
                return redirect(tpath)
            if cid in byid and 0 <= dest < len(targets):
                unplace(cid)  # 同一スロット内の重複を防ぐ（他リストからは移動）
                if cid not in targets[dest]["members"]:
                    targets[dest]["members"].append(cid)
        elif act == "remove":
            unplace(cid)
        store.save_event(srv, ev)
    q = "?t=" + slot if slot else ""
    return redirect(tpath + q)


def _member_label(t, cid, byid):
    c = byid.get(cid)
    name = h(c["name"]) if c else "（削除済み）"
    label = '%s<span class="sub">(%s)</span>' % (
        name, tpl.fmt_num(_march(c or {})))
    if t.get("captain") == cid:
        label += '<span class="cap">（キャプテン）</span>'
    if t.get("sub") == cid:
        label += '<span class="subcap">（サブ）</span>'
    return label


def _hidden(csrf, **kw):
    out = '<input type="hidden" name="csrf" value="%s">' % h(csrf)
    for k, v in sorted(kw.items()):
        out += '<input type="hidden" name="%s" value="%s">' % (h(k), h(v))
    return out


def _render_shift(req, srv, ev, byid, sess, tpath):
    pub = ev["published"]
    keys = [k for k in ("first", "second", "all") if k in pub["slots"]]
    cur = req.q("t") if req.q("t") in keys else keys[0]
    targets = pub["slots"][cur]["targets"]
    action_url = h(url(tpath))
    csrf = auth.csrf_token(sess) if sess else ""

    tabs = ""
    if len(keys) > 1:
        tabs = '<div class="tabs">'
        for k in keys:
            cls = "on" if k == cur else ""
            tabs += '<a class="%s" href="%s?t=%s">%s</a>' % (
                cls, action_url, h(k), h(SLOT_LABELS[k]))
        tabs += "</div>"

    placed = set()
    for t in targets:
        placed.update(t["members"])
    # 参加申請者全員（「不参加」を除く）のうち、このシフトに入っていない人。
    # 前半に配置済みでも後半の未配置には表示され、どちらへも追加できる。
    entries = ev.get("entries") or {}
    candidates = [c for c in shift.participants(ev, byid, None)
                  if c["id"] not in placed]

    body = tabs
    for ti, t in enumerate(targets):
        total = sum(_march(byid.get(cid) or {}) for cid in t["members"])
        capc = byid.get(t.get("captain") or "")
        cap = (_march(capc) + (capc.get("gather_size") or 0)) if capc else 0
        over = ' <span class="over">（上限超過）</span>' if capc and total > cap else ""
        rows = ""
        for cid in t["members"]:
            label = _member_label(t, cid, byid)
            if not sess:
                rows += '<div class="prow">%s</div>' % label
                continue
            acts = ""
            common = _hidden(csrf, slot=cur, cid=cid, target=str(ti))
            acts += ('<form method="post" action="%s">%s'
                     '<input type="hidden" name="act" value="captain">'
                     '<button class="btn small">キャプテンに任命</button></form>'
                     ) % (action_url, common)
            acts += ('<form method="post" action="%s">%s'
                     '<input type="hidden" name="act" value="sub">'
                     '<button class="btn small">サブに任命</button></form>'
                     ) % (action_url, common)
            for oi, ot in enumerate(targets):
                if oi == ti:
                    continue
                acts += ('<form method="post" action="%s">%s'
                         '<input type="hidden" name="act" value="move">'
                         '<input type="hidden" name="to" value="%d">'
                         '<button class="btn small">%sへ移動</button></form>'
                         ) % (action_url, _hidden(csrf, slot=cur, cid=cid),
                              oi, h(ot["name"]))
            acts += ('<form method="post" action="%s">%s'
                     '<input type="hidden" name="act" value="remove">'
                     '<button class="btn small danger">リストから外す</button></form>'
                     ) % (action_url, _hidden(csrf, slot=cur, cid=cid))
            rows += ('<details class="prow"><summary>%s</summary>'
                     '<div class="acts">%s</div></details>') % (label, acts)
        if not rows:
            rows = '<div class="prow empty">未配置</div>'
        body += """<div class="starget">
<h4>%s %s <span class="sub">%d人 ／ 合計 %s ／ 上限 %s%s</span></h4>
%s</div>""" % (h(t["name"]), tpl.troop_badge(t["troop"]), len(t["members"]),
               tpl.fmt_num(total), tpl.fmt_num(cap) if capc else "-", over, rows)

    if candidates:
        rows = ""
        for c in candidates:
            choice = (entries.get(c["id"]) or {}).get("choice") or ""
            label = '%s %s<span class="sub">(%s)／登録: %s</span>' % (
                h(c["name"]), tpl.troop_badge(c.get("troop_type")),
                tpl.fmt_num(_march(c)), h(choice))
            if not sess:
                rows += '<div class="prow">%s</div>' % label
                continue
            acts = ""
            for oi, ot in enumerate(targets):
                acts += ('<form method="post" action="%s">%s'
                         '<input type="hidden" name="act" value="add">'
                         '<input type="hidden" name="to" value="%d">'
                         '<button class="btn small">%sへ追加</button></form>'
                         ) % (action_url, _hidden(csrf, slot=cur, cid=c["id"]),
                              oi, h(ot["name"]))
            rows += ('<details class="prow"><summary>%s</summary>'
                     '<div class="acts">%s</div></details>') % (label, acts)
        body += ('<div class="starget"><h4>未配置 <span class="sub">%d人'
                 '（参加申請者のうちこの%sのシフトに入っていない人）</span></h4>'
                 '%s</div>') % (len(candidates), h(SLOT_LABELS[cur]), rows)

    foot = '<p class="hint">発表: %s ／ 参加登録の変動はこの表に反映されません。</p>' % h(
        (pub.get("created") or "").replace("T", " "))
    if sess:
        foot += '<p class="hint">メンバーをタップすると任命・移動などの操作ができます。</p>'
    else:
        foot += '<p><a class="btn small" href="%s?login=1">ホストとして編集</a></p>' % action_url
    foot += '<p><a class="btn" href="%s">報酬分配リスト</a></p>' % h(
        url("/%s/e/%s/rewards" % (srv, ev["id"])))
    return html_page("発表シフト - %s" % ev["title"], body + foot,
                     back=url("/%s/e/%s" % (srv, ev["id"])))


# ---------- 報酬分配リスト ----------

def _reward_rows(ev, byid):
    """発表シフトから1人1行（前後半合算）の行リストを優先順位順で返す。"""
    pub = ev.get("published") or {}
    smap = shift.slot_map(ev)
    entries = ev.get("entries") or {}
    people = {}
    for sl in pub.get("slots", {}).values():
        for t in sl["targets"]:
            for cid in t["members"]:
                p = people.setdefault(cid, {"captain": False, "sub": False})
                if t.get("captain") == cid:
                    p["captain"] = True
                if t.get("sub") == cid:
                    p["sub"] = True
    rows = []
    for cid, flags in people.items():
        c = byid.get(cid)
        if not c:
            continue
        choice = (entries.get(cid) or {}).get("choice") or ""
        rows.append({"c": c, "captain": flags["captain"], "sub": flags["sub"],
                     "full": smap.get(choice) == "both"})
    rows.sort(key=lambda r: (-r["captain"], -r["sub"], -r["full"],
                             -_march(r["c"]),
                             -(r["c"].get("gather_size") or 0), r["c"]["id"]))
    return rows


def _allocate(rows, attend_off, fixed):
    """出席者に上位から 赤1/青5/緑20/薄黄74 を割り振る。色固定は先に枠を消費。"""
    remain = dict((k, n) for k, _label, n in REWARD_COLORS)
    for r in rows:
        cid = r["c"]["id"]
        r["attend"] = cid not in attend_off
        f = fixed.get(cid)
        r["fixed"] = bool(r["attend"] and f)
        r["color"] = None
        if r["fixed"]:
            if f != "none":
                r["color"] = f
                if f in remain:
                    remain[f] -= 1
    for r in rows:
        if not r["attend"] or r["fixed"]:
            continue
        for k, _label, _n in REWARD_COLORS:
            if remain[k] > 0:
                remain[k] -= 1
                r["color"] = k
                break
    return rows


def rewards_page(req, srv, eid):
    ev = store.get_event(srv, eid)
    if not ev:
        return not_found()
    byid = dict((c["id"], c) for c in store.list_characters(srv))
    tpath = "/%s/e/%s/rewards" % (srv, eid)
    sess = _host_sess(req, srv, eid)

    if req.method == "POST":
        r = _handle_host_login(req, srv, ev, tpath)
        if r:
            return r
        if not _csrf_ok(req, sess):
            return _login_page(srv, ev, tpath, "セッションの有効期限が切れました。もう一度認証してください")
        act = req.field("act")
        cid = req.field("cid")
        with store.lock(srv):
            ev = store.get_event(srv, eid)
            if not ev:
                return not_found()
            rw = ev.setdefault("rewards", {"attend_off": [], "fixed": {}})
            rw.setdefault("attend_off", [])
            rw.setdefault("fixed", {})
            if act == "attend":
                if req.field("on"):
                    if cid in rw["attend_off"]:
                        rw["attend_off"].remove(cid)
                elif cid not in rw["attend_off"]:
                    rw["attend_off"].append(cid)
            elif act == "color":
                color = req.field("color")
                valid = tuple(k for k, _l, _n in REWARD_COLORS) + ("none",)
                if color == "auto":
                    rw["fixed"].pop(cid, None)
                elif color in valid:
                    rw["fixed"][cid] = color
            store.save_event(srv, ev)
        return redirect(tpath)

    if req.q("login") and not sess:
        return _login_page(srv, ev, tpath)

    back = url("/%s/e/%s/shift" % (srv, eid))
    if not ev.get("published"):
        return html_page("報酬分配リスト - %s" % ev["title"],
                         '<p>発表シフトの作成後に利用できます。</p>', back=back)

    rw = ev.get("rewards") or {}
    attend_off = set(rw.get("attend_off") or [])
    fixed = rw.get("fixed") or {}
    rows = _allocate(_reward_rows(ev, byid), attend_off, fixed)
    action_url = h(url(tpath))
    csrf = auth.csrf_token(sess) if sess else ""
    labels = dict((k, l) for k, l, _n in REWARD_COLORS)

    trs = ""
    for i, r in enumerate(rows):
        c = r["c"]
        cls = "rw-" + r["color"] if r["color"] else ""
        if not r["attend"]:
            cls = "rw-off"
        badges = ""
        if r["captain"]:
            badges += '<span class="cap">（キャプテン）</span>'
        if r["sub"]:
            badges += '<span class="subcap">（サブ）</span>'
        if r["full"]:
            badges += '<span class="sub">（フル）</span>'
        color_cell = labels.get(r["color"], "-")
        if r["fixed"]:
            color_cell += '<span class="sub">固定</span>'
        name = '<a href="%s">%s</a>' % (
            h(url("/%s/c/%s" % (srv, c["id"]))), h(c["name"]))
        if sess:
            acts = ""
            common = _hidden(csrf, cid=c["id"])
            for k, l, _n in REWARD_COLORS:
                acts += ('<form method="post" action="%s">%s'
                         '<input type="hidden" name="act" value="color">'
                         '<input type="hidden" name="color" value="%s">'
                         '<button class="btn small">%sに固定</button></form>') % (
                    action_url, common, k, l)
            acts += ('<form method="post" action="%s">%s'
                     '<input type="hidden" name="act" value="color">'
                     '<input type="hidden" name="color" value="none">'
                     '<button class="btn small">色なしに固定</button></form>') % (
                action_url, common)
            acts += ('<form method="post" action="%s">%s'
                     '<input type="hidden" name="act" value="color">'
                     '<input type="hidden" name="color" value="auto">'
                     '<button class="btn small">自動に戻す</button></form>') % (
                action_url, common)
            name = ('<details class="rwname"><summary>%s%s</summary>'
                    '<div class="acts">%s</div></details>') % (name, badges, acts)
            att = ('<form method="post" action="%s">%s'
                   '<input type="hidden" name="act" value="attend">'
                   '<label class="attlabel"><input type="checkbox" name="on" value="1"%s'
                   ' onchange="this.form.submit()"> 出席</label>'
                   '<noscript><button class="btn small">更新</button></noscript>'
                   '</form>') % (action_url, _hidden(csrf, cid=c["id"]),
                                 " checked" if r["attend"] else "")
        else:
            name += badges
            att = "出席" if r["attend"] else "欠席"
        trs += ('<tr class="%s"><td class="num">%d</td><td>%s</td><td>%s</td>'
                '<td class="num">%s</td><td class="num">%s</td><td>%s</td></tr>') % (
            cls, i + 1, color_cell, name,
            tpl.fmt_num(c.get("march_size")), tpl.fmt_num(c.get("gather_size")),
            att)
    if not trs:
        trs = '<tr><td colspan="6">発表シフトにメンバーがいません</td></tr>'

    counts = {}
    for r in rows:
        if r["color"]:
            counts[r["color"]] = counts.get(r["color"], 0) + 1
    summary = "／".join("%s %d/%d" % (l, counts.get(k, 0), n)
                        for k, l, n in REWARD_COLORS)
    hint = ('<p class="hint">優先順位: キャプテン → サブ → フルタイム → 部隊数 → '
            'ギャザー。割当: %s</p>') % h(summary)
    if sess:
        hint += '<p class="hint">名前をタップで色の固定、出席チェックで分配から除外できます。</p>'
    else:
        hint += '<p><a class="btn small" href="%s?login=1">ホストとして編集</a></p>' % action_url

    body = hint + ('<table class="list rwlist">'
                   '<tr><th>#</th><th>色</th><th>メンバー</th><th>部隊</th>'
                   '<th>ギャザー</th><th>出席</th></tr>%s</table>') % trs
    return html_page("報酬分配リスト - %s" % ev["title"], body, back=back)


ROUTES = [
    ("GET", r"/(\d{4})/e/([a-z0-9]{8})/shift", shift_page),
    ("POST", r"/(\d{4})/e/([a-z0-9]{8})/shift", shift_page),
    ("GET", r"/(\d{4})/e/([a-z0-9]{8})/rewards", rewards_page),
    ("POST", r"/(\d{4})/e/([a-z0-9]{8})/rewards", rewards_page),
]
