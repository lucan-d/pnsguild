"""一般公開画面（public.py / host.py / tpl.py / forms.py）の日英2言語対応。

CGI（1リクエスト1プロセス）と開発サーバー（シングルスレッド逐次処理）
という実行環境の性質上、現在言語はモジュールレベルのグローバル変数で
保持する（全ハンドラの引数に lang を通す必要がない）。admin側は
lib/app.py で force_lang=DEFAULT を指定して常に日本語に固定する。
"""
import urllib.parse

SUPPORTED = ("ja", "en")
DEFAULT = "ja"
COOKIE_NAME = "lang"

_LANG_LABELS = (("ja", "日本語"), ("en", "English"))

_STRINGS = {
    # ---------- tpl.py（ページ共通部品） ----------
    "back_link": {"ja": "戻る", "en": "Back"},

    # ---------- web.py（エラーページ、admin共用） ----------
    "err_not_found": {"ja": "ページが見つかりません", "en": "Page not found"},
    "title_error": {"ja": "エラー", "en": "Error"},
    "err_internal": {"ja": "内部エラーが発生しました。",
                     "en": "An internal error occurred."},

    # ---------- formdata.py（フォーム解析エラー、admin共用） ----------
    "err_body_too_large": {
        "ja": "送信サイズが大きすぎます（合計 {mb}MB まで）",
        "en": "Request too large (max {mb}MB total)"},
    "err_bad_form": {"ja": "不正なフォームデータです", "en": "Invalid form data"},

    # ---------- forms.py（入力検証、admin共用） ----------
    "err_must_be_number": {"ja": "{label}は数値で入力してください",
                           "en": "{label} must be a number"},
    "err_name_required": {"ja": "キャラクター名を入力してください",
                          "en": "Please enter a character name"},
    "err_name_too_long": {"ja": "キャラクター名は30文字以内にしてください",
                          "en": "Character name must be 30 characters or less"},
    "err_guild_too_long": {"ja": "ギルド名は30文字以内にしてください",
                           "en": "Guild name must be 30 characters or less"},
    "err_troop_required": {"ja": "特化兵種を選択してください",
                           "en": "Please select a troop type"},
    "err_tier_range": {"ja": "Tierは1〜15で入力してください",
                       "en": "Tier must be between 1 and 15"},
    "err_shelter_format": {
        "ja": "避難所座標は「123,456」の形式で入力してください",
        "en": "Shelter coordinates must be in the format \"123,456\""},
    "err_shelter_range": {
        "ja": "避難所座標の範囲は 0〜510 , 0〜1022 です",
        "en": "Shelter coordinates must be within 0-510, 0-1022"},
    "field_march_size": {"ja": "部隊規模", "en": "March Size"},
    "field_gather_size": {"ja": "ギャザー規模", "en": "Gather Size"},
    "field_tier": {"ja": "Tier", "en": "Tier"},

    # ---------- public.py: _MSG ----------
    "msg_imgerr": {
        "ja": "画像の保存に失敗しました（形式・サイズ・投稿回数を確認してください）",
        "en": "Failed to save the image (check format, size, and upload count)"},
    "msg_saved": {"ja": "保存しました", "en": "Saved"},
    "msg_keysaved": {"ja": "保存しました（編集キーを変更しました）",
                     "en": "Saved (edit key changed)"},
    "msg_joined": {"ja": "参加情報を更新しました", "en": "Updated your registration"},
    "msg_joined_named": {"ja": "「{name}」の参加情報を更新しました",
                         "en": "Updated registration for \"{name}\""},

    # ---------- public.py: ログイン ----------
    "title_login_confirm": {"ja": "編集キーの確認", "en": "Confirm Edit Key"},
    "login_required_for": {"ja": "「{name}」の操作には編集キーが必要です。",
                           "en": "Editing \"{name}\" requires the edit key."},
    "edit_key_placeholder": {"ja": "編集キー", "en": "Edit key"},
    "btn_login": {"ja": "認証する", "en": "Log in"},
    "login_forgot_hint": {
        "ja": "編集キーを忘れた場合は管理者に再設定を依頼してください。",
        "en": "If you forgot the edit key, ask the administrator to reset it."},
    "err_login_key_wrong": {"ja": "編集キーが違います", "en": "Incorrect edit key"},
    "err_session_expired": {
        "ja": "セッションの有効期限が切れました。編集キーを入力してください",
        "en": "Your session has expired. Please enter your edit key"},
    "err_upload_rate": {
        "ja": "画像の投稿が多すぎます。1時間ほど空けてからもう一度お試しください",
        "en": "Too many image uploads. Please wait about an hour and try again"},

    # ---------- public.py: 避難所マップ ----------
    "shelter_map_toggle": {"ja": "避難所位置をマップ表示",
                           "en": "Show shelter location on map"},
    "shelter_map_aria": {"ja": "避難所位置", "en": "Shelter location"},
    "shelter_map_hint": {
        "ja": "マップ全体 511×1023（左上が 0,0・横方向は2倍に拡大表示）",
        "en": "Full map 511×1023 (0,0 at top-left; horizontal axis shown at 2x scale)"},

    # ---------- public.py: キャラカード/フォーム ----------
    "guild_none": {"ja": "（無所属）", "en": "(No guild)"},
    "char_card_nums": {"ja": "部隊 {march} ／ ギャザー {gather}",
                       "en": "March {march} / Gather {gather}"},
    "label_edit_key_new": {
        "ja": "編集キー（{min}文字以上・編集時に必要）",
        "en": "Edit key ({min}+ characters, required for future edits)"},
    "label_edit_key_confirm": {"ja": "編集キー（確認）", "en": "Edit key (confirm)"},
    "heading_change_key": {"ja": "編集キー変更", "en": "Change Edit Key"},
    "label_new_key": {
        "ja": "新しい編集キー（変更する場合のみ・{min}文字以上）",
        "en": "New edit key (only if changing, {min}+ characters)"},
    "label_new_key_confirm": {"ja": "新しい編集キー（確認）",
                              "en": "New edit key (confirm)"},
    "img_label_new": {"ja": "プロフィール画像（1枚・5MBまで）",
                      "en": "Profile image (1 file, up to 5MB)"},
    "img_label_replace": {"ja": "プロフィール画像（選択すると差し替え）",
                          "en": "Profile image (choose a file to replace)"},
    "label_char_name": {"ja": "キャラクター名 *", "en": "Character Name *"},
    "label_guild": {"ja": "ギルド名", "en": "Guild Name"},
    "label_troop_type": {"ja": "特化兵種 *", "en": "Troop Type *"},
    "label_tier": {"ja": "Tier（兵種ティア）", "en": "Tier (troop tier)"},
    "placeholder_tier_example": {"ja": "例: 8", "en": "e.g. 8"},
    "placeholder_march_example": {"ja": "例: 1500000", "en": "e.g. 1500000"},
    "label_shelter": {"ja": "避難所座標（xxx,yyy）",
                      "en": "Shelter Coordinates (xxx,yyy)"},
    "placeholder_shelter_example": {"ja": "例: 123,456", "en": "e.g. 123,456"},
    "btn_register": {"ja": "登録する", "en": "Register"},
    "btn_save": {"ja": "保存する", "en": "Save"},

    # ---------- public.py: イベント一覧 ----------
    "empty_no_events": {"ja": "イベントはありません", "en": "No events"},
    "tag_closed": {"ja": "締切", "en": "Closed"},
    "tag_open": {"ja": "受付中", "en": "Open"},
    "event_entries_count": {"ja": "（参加登録 {n}件）", "en": "({n} registered)"},

    # ---------- public.py: home ----------
    "err_server_not_registered": {
        "ja": "サーバー #{num} は未登録です。管理者に登録を依頼してください",
        "en": "Server #{num} is not registered. Please ask the administrator to register it"},
    "empty_no_servers": {"ja": "登録済みサーバーはまだありません",
                         "en": "No servers are registered yet"},
    "placeholder_server_num": {"ja": "サーバー番号（4桁）",
                               "en": "Server number (4 digits)"},
    "btn_go": {"ja": "移動", "en": "Go"},
    "heading_server_list": {"ja": "サーバー一覧", "en": "Server List"},
    "title_server_select": {"ja": "サーバー選択", "en": "Select Server"},

    # ---------- public.py: server_top ----------
    "btn_char_new": {"ja": "＋ キャラクター新規登録",
                     "en": "+ Register New Character"},
    "heading_events": {"ja": "イベント", "en": "Events"},
    "heading_chars": {"ja": "キャラクター（{n}）", "en": "Characters ({n})"},
    "tag_clear": {"ja": "解除", "en": "Clear"},
    "empty_no_chars": {"ja": "キャラクターがまだ登録されていません",
                       "en": "No characters registered yet"},
    "title_server_num": {"ja": "サーバー #{num}", "en": "Server #{num}"},

    # ---------- public.py: char_new / char_edit ----------
    "title_char_new": {"ja": "キャラクター新規登録", "en": "Register New Character"},
    "title_char_edit": {"ja": "キャラクター編集", "en": "Edit Character"},
    "err_key_too_short": {"ja": "編集キーは{min}文字以上にしてください",
                          "en": "The edit key must be at least {min} characters"},
    "err_key_confirm_mismatch": {"ja": "編集キー（確認）が一致しません",
                                 "en": "Edit key confirmation does not match"},
    "err_newkey_too_short": {
        "ja": "新しい編集キーは{min}文字以上にしてください",
        "en": "The new edit key must be at least {min} characters"},
    "err_newkey_confirm_mismatch": {
        "ja": "新しい編集キー（確認）が一致しません",
        "en": "New edit key confirmation does not match"},

    # ---------- public.py: char_detail ----------
    "kv_guild": {"ja": "ギルド名", "en": "Guild"},
    "kv_troop_type": {"ja": "特化兵種", "en": "Troop Type"},
    "kv_shelter": {"ja": "避難所座標", "en": "Shelter Coordinates"},
    "kv_updated": {"ja": "更新日", "en": "Updated"},
    "own_edit": {"ja": "編集", "en": "Edit"},
    "own_album": {"ja": "アルバム管理", "en": "Manage Album"},
    "own_hint": {
        "ja": "※本人（編集キーを知っている人）のみ操作できます。"
              "キャラクターの削除は管理者に依頼してください。",
        "en": "* Only the owner (who knows the edit key) can make changes. "
              "Ask the administrator to delete a character."},
    "heading_album": {"ja": "アルバム（{cur}/{max}）", "en": "Album ({cur}/{max})"},
    "empty_album": {"ja": "アルバムは空です", "en": "Album is empty"},

    # ---------- public.py: char_album ----------
    "title_album_manage": {"ja": "アルバム管理 - {name}",
                           "en": "Manage Album - {name}"},
    "err_select_file": {"ja": "ファイルを選択してください",
                        "en": "Please select a file"},
    "err_album_max": {"ja": "アルバムは最大{max}枚までです",
                      "en": "The album can hold up to {max} images"},
    "btn_delete": {"ja": "削除", "en": "Delete"},
    "btn_upload": {"ja": "アップロード", "en": "Upload"},
    "label_add_photo": {"ja": "画像を追加（JPEG/PNG/WebP・5MBまで）",
                        "en": "Add image (JPEG/PNG/WebP, up to 5MB)"},
    "hint_album_full": {
        "ja": "上限（{max}枚）に達しています。追加するには既存の画像を削除してください。",
        "en": "You've reached the limit ({max} images). Delete an existing image to add more."},
    "count_of": {"ja": "{cur} / {max} 枚", "en": "{cur} / {max}"},
    "heading_add": {"ja": "追加", "en": "Add"},

    # ---------- public.py: event_page / _event_view ----------
    "err_event_closed": {"ja": "このイベントは締め切られています",
                         "en": "This event is closed"},
    "err_select_char": {"ja": "キャラクターを選択してください",
                        "en": "Please select a character"},
    "err_select_choice": {"ja": "参加区分を選択してください",
                          "en": "Please select a participation option"},
    "err_login_key_wrong_event": {
        "ja": "編集キーが違います"
              "（この端末で初めて操作するキャラクターは編集キーが必要です）",
        "en": "Incorrect edit key (an edit key is required the first time "
              "you operate a character on this device)"},
    "deleted_char": {"ja": "（削除済み）", "en": "(deleted)"},
    "heading_forecast_shift": {"ja": "予想シフト表", "en": "Forecast Shift Table"},
    "forecast_hint": {
        "ja": "参加登録から自動で振り分けています"
              "（登録が変わると振り分けも変わります）。各対象の合計は"
              "キャプテンの部隊+ギャザー規模が上限で、入り切らない場合は"
              "補欠になります。",
        "en": "Automatically assigned from registrations (assignments change "
              "as registrations change). Each target's total is capped by the "
              "captain's march + gather size; anyone who doesn't fit becomes "
              "a reserve."},
    "label_captain": {"ja": "（キャプテン）", "en": "(Captain)"},
    "reserve_heading": {"ja": "補欠", "en": "Reserve"},
    "reserve_count": {"ja": "{n}人", "en": "{n} people"},
    "forecast_count_total": {"ja": "{n}人 ／ 合計 {total}",
                             "en": "{n} people / total {total}"},
    "forecast_cap": {"ja": "上限 {cap}", "en": "Cap {cap}"},
    "heading_participation": {"ja": "参加登録", "en": "Register Participation"},
    "select_char_label": {"ja": "キャラクター", "en": "Character"},
    "select_placeholder": {"ja": "選択してください", "en": "Please select"},
    "optgroup_authed": {"ja": "認証済み（編集キー不要）",
                        "en": "Authenticated (no edit key needed)"},
    "optgroup_others": {"ja": "その他（編集キーが必要）",
                        "en": "Other (edit key required)"},
    "current_choice_mark": {"ja": "／現在: {cur}", "en": " / current: {cur}"},
    "radio_cancel": {"ja": "参加登録を取り消す", "en": "Cancel registration"},
    "placeholder_edit_key_authed": {"ja": "認証済みの端末では不要",
                                    "en": "Not needed on an authenticated device"},
    "btn_register_participation": {"ja": "登録する", "en": "Register"},
    "hint_need_char_first": {
        "ja": "参加登録にはまずキャラクター登録が必要です。",
        "en": "You need to register a character before you can join events."},
    "ev_head_open_date": {"ja": "開催: {date}", "en": "Date: {date}"},
    "ev_head_deadline": {"ja": "受付締切: {date}",
                         "en": "Registration deadline: {date}"},
    "link_published_shift": {"ja": "発表シフト", "en": "Published Shift"},
    "link_rewards": {"ja": "報酬分配リスト", "en": "Reward Distribution List"},
    "heading_participation_status": {"ja": "参加状況（{n}件）",
                                     "en": "Participation Status ({n})"},

    # ---------- host.py: ホスト認証 ----------
    "title_host_auth": {"ja": "ホスト認証", "en": "Host Authentication"},
    "err_no_host_password": {
        "ja": "このイベントにはホストパスワードが設定されていません。"
              "管理者に設定を依頼してください。",
        "en": "No host password is set for this event. "
              "Please ask the administrator to set one."},
    "host_pass_required_for": {
        "ja": "「{title}」のホスト操作にはホストパスワードが必要です。",
        "en": "Host actions for \"{title}\" require the host password."},
    "placeholder_host_pass": {"ja": "ホストパスワード", "en": "Host password"},
    "err_host_pass_wrong": {"ja": "パスワードが違います", "en": "Incorrect password"},
    "err_host_session_expired": {
        "ja": "セッションの有効期限が切れました。もう一度認証してください",
        "en": "Your session has expired. Please log in again"},

    # ---------- host.py: 発表シフト ----------
    "title_published_shift": {"ja": "発表シフト - {title}",
                              "en": "Published Shift - {title}"},
    "shift_not_ready": {"ja": "発表シフトは受付締切後に作成できます。",
                        "en": "The published shift can be created after registration closes."},
    "deadline_label": {"ja": "受付締切: {date}",
                       "en": "Registration deadline: {date}"},
    "deadline_unset": {"ja": "未設定（手動締切待ち）",
                       "en": "Not set (waiting for manual closing)"},
    "shift_create_hint": {
        "ja": "受付は締め切られています。現在の予想シフトを元に発表シフトを"
              "作成します。作成後は参加登録の変動に影響されず、手動で調整"
              "できます。",
        "en": "Registration is closed. The published shift will be created "
              "from the current forecast. Once created, it won't change with "
              "new registrations and can be adjusted manually."},
    "btn_create_shift": {"ja": "発表シフトを作成する", "en": "Create Published Shift"},
    "shift_not_created_yet": {"ja": "発表シフトはまだ作成されていません。",
                              "en": "The published shift hasn't been created yet."},
    "link_create_as_host": {"ja": "ホストとして作成する", "en": "Create as host"},
    "label_sub": {"ja": "（サブ）", "en": "(Sub)"},
    "btn_captain": {"ja": "キャプテンに任命", "en": "Assign Captain"},
    "btn_sub": {"ja": "サブに任命", "en": "Assign Sub"},
    "btn_move_to": {"ja": "{name}へ移動", "en": "Move to {name}"},
    "btn_remove_from_list": {"ja": "リストから外す", "en": "Remove from list"},
    "unplaced": {"ja": "未配置", "en": "Unplaced"},
    "target_summary": {"ja": "{n}人 ／ 合計 {total} ／ 上限 {cap}{over}",
                       "en": "{n} people / total {total} / cap {cap}{over}"},
    "over_cap": {"ja": "（上限超過）", "en": "(over cap)"},
    "registered_choice": {"ja": "／登録: {choice}", "en": " / registered: {choice}"},
    "btn_add_to": {"ja": "{name}へ追加", "en": "Add to {name}"},
    "unplaced_heading": {
        "ja": "未配置 {n}人（参加申請者のうちこの{slot}のシフトに"
              "入っていない人）",
        "en": "Unplaced: {n} (registrants not yet placed in the {slot} shift)"},
    "published_at": {
        "ja": "発表: {date} ／ 参加登録の変動はこの表に反映されません。",
        "en": "Published: {date} / Changes to registrations are not reflected in this table."},
    "host_edit_hint": {"ja": "メンバーをタップすると任命・移動などの操作ができます。",
                       "en": "Tap a member to assign or move them."},
    "link_edit_as_host": {"ja": "ホストとして編集", "en": "Edit as host"},
    "slot_first": {"ja": "前半", "en": "First Half"},
    "slot_second": {"ja": "後半", "en": "Second Half"},
    "slot_all": {"ja": "全体", "en": "All"},
    "heading_shift_copy": {"ja": "コピー用テキスト（ゲーム内チャットへ）",
                           "en": "Copy Text (for in-game chat)"},
    "btn_copy": {"ja": "コピー", "en": "Copy"},
    "btn_copied": {"ja": "コピーしました", "en": "Copied"},

    # ---------- host.py: 報酬分配リスト ----------
    "title_rewards": {"ja": "報酬分配リスト - {title}",
                      "en": "Reward Distribution List - {title}"},
    "rewards_need_shift": {"ja": "発表シフトの作成後に利用できます。",
                           "en": "Available once the published shift is created."},
    "badge_full": {"ja": "（フル）", "en": "(Full)"},
    "fixed_tag": {"ja": "固定", "en": "Fixed"},
    "btn_fix_to": {"ja": "{label}に固定", "en": "Fix to {label}"},
    "btn_fix_none": {"ja": "色なしに固定", "en": "Fix to none"},
    "btn_auto": {"ja": "自動に戻す", "en": "Reset to auto"},
    "attend_label": {"ja": "出席", "en": "Attend"},
    "btn_update": {"ja": "更新", "en": "Update"},
    "attend_status_yes": {"ja": "出席", "en": "Attending"},
    "attend_status_no": {"ja": "欠席", "en": "Absent"},
    "empty_no_shift_members": {"ja": "発表シフトにメンバーがいません",
                               "en": "No members in the published shift"},
    "priority_hint": {
        "ja": "優先順位: キャプテン → サブ → フルタイム → 部隊数 → "
              "ギャザー。割当: {summary}",
        "en": "Priority: Captain → Sub → Full-time → March "
              "size → Gather. Allocation: {summary}"},
    "reward_edit_hint": {
        "ja": "名前をタップで色の固定、出席チェックで分配から除外できます。",
        "en": "Tap a name to fix a color; use the attend checkbox to exclude from distribution."},
    "th_num": {"ja": "#", "en": "#"},
    "th_color": {"ja": "色", "en": "Color"},
    "th_member": {"ja": "メンバー", "en": "Member"},
    "th_march": {"ja": "部隊", "en": "March"},
    "th_gather": {"ja": "ギャザー", "en": "Gather"},
    "th_attend": {"ja": "出席", "en": "Attend"},
    "color_red": {"ja": "赤", "en": "Red"},
    "color_blue": {"ja": "青", "en": "Blue"},
    "color_green": {"ja": "緑", "en": "Green"},
    "color_yellow": {"ja": "薄黄", "en": "Pale Yellow"},
}

_lang = DEFAULT
_return_to = "/"
_locked = False


def resolve_lang(req):
    c = req.cookie(COOKIE_NAME)
    return c if c in SUPPORTED else DEFAULT


def begin_request(req, force_lang=None):
    """1リクエストにつき1回呼ぶ。現在パス+クエリを切替リンクの戻り先として保持。

    force_lang 指定時（admin側）は言語固定とみなし、切替リンク自体を出さない。
    """
    global _lang, _return_to, _locked
    _locked = force_lang is not None
    _lang = force_lang if force_lang in SUPPORTED else resolve_lang(req)
    qs = req.environ.get("QUERY_STRING", "")
    _return_to = req.path + ("?" + qs if qs else "")


def current():
    return _lang


def t(key, **kwargs):
    entry = _STRINGS.get(key, {})
    s = entry.get(_lang) or entry.get(DEFAULT) or key
    return s.format(**kwargs) if kwargs else s


def switch_links():
    """[(href, label, is_current), ...] を返す。tpl.page() のヘッダーで使う。
    admin側（言語固定）では空リストを返し、切替リンク自体を出さない。"""
    if _locked:
        return []
    out = []
    for code, label in _LANG_LABELS:
        href = "/set-lang?lang=%s&back=%s" % (
            code, urllib.parse.quote(_return_to, safe=""))
        out.append((href, label, code == _lang))
    return out


def set_lang(req):
    """GET /set-lang?lang=en&back=/1234/ … Cookieを更新して戻る。"""
    from lib.web import redirect

    lang = req.q("lang")
    back = req.q("back") or "/"
    if lang not in SUPPORTED:
        lang = DEFAULT
    if not back.startswith("/") or back.startswith("//"):
        back = "/"  # オープンリダイレクト対策
    resp = redirect(back)
    resp.set_cookie(COOKIE_NAME, lang, 365 * 86400)
    return resp


ROUTES = [("GET", r"/set-lang", set_lang)]
