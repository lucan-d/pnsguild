"""イベント参加者の予想シフト振り分け。

- 参加区分ごとに「前半/後半/前後半/対象外」のスロットを持ち、
  前半・後半が定義されたイベントではシフト表を2つ生成する。
- 各シフト対象の部隊規模合計は、キャプテン（対象内最大部隊のキャラ）の
  「部隊規模+ギャザー規模」を上限とし、入り切らない参加者は補欠となる。
- 割り当ては兵種の一致を優先し、部隊規模の大きい順に合計最小の対象へ
  （LPT方式）。保存はせず閲覧時に都度計算する。結果は決定的。
"""
from lib import config

SLOT_CHOICES = (("first", "前半"), ("second", "後半"),
                ("both", "前後半"), ("none", "対象外"))
SLOT_VALUES = tuple(v for v, _ in SLOT_CHOICES)


def default_targets():
    return [{"name": n, "troop": t} for n, t in config.SHIFT_TARGETS]


def guess_slot(choice):
    """区分テキストからスロットを自動判定。"""
    if "不参加" in choice:
        return "none"
    has_f = "前半" in choice
    has_s = "後半" in choice
    if has_f and has_s:
        return "both"
    if has_f:
        return "first"
    if has_s:
        return "second"
    return "both"


def slot_map(ev):
    """choices の各区分 → スロット。未設定分は自動判定で補う。"""
    saved = (ev.get("shift") or {}).get("slots") or {}
    return {ch: (saved[ch] if saved.get(ch) in SLOT_VALUES else guess_slot(ch))
            for ch in ev.get("choices", [])}


def tables(ev, byid):
    """シフト表の一覧を返す。[(ラベル or None, buckets, 補欠リスト), ...]

    前半または後半の区分が定義されていれば前半・後半の2表、
    そうでなければ1表（ラベル None）。
    """
    smap = slot_map(ev)
    defined = set(smap.values())
    if "first" in defined or "second" in defined:
        return [(slot, ) + _assign(ev, _participants(ev, byid, smap, slot))
                for slot in ("first", "second")]
    return [(None, ) + _assign(ev, _participants(ev, byid, smap, None))]


def participants(ev, byid, slot=None):
    """指定スロットの参加者一覧（発表シフト編集の候補者などに使う）。"""
    return _participants(ev, byid, slot_map(ev), slot)


def _participants(ev, byid, smap, slot):
    parts = []
    entries = ev.get("entries") or {}
    for cid in sorted(entries):
        choice = entries[cid].get("choice") or ""
        s = smap.get(choice) or guess_slot(choice)
        if s == "none":
            continue
        if slot is not None and s not in (slot, "both"):
            continue
        c = byid.get(cid)
        if c:
            parts.append(c)
    return parts


def _march(c):
    return c.get("march_size") or 0


def _power(c):
    """キャプテン判定・上限計算に使う値 = 部隊規模 + ギャザー規模。"""
    return _march(c) + (c.get("gather_size") or 0)


def _captain(members):
    """キャプテン = 部隊規模+ギャザー規模が最大のキャラ。"""
    return max(members, key=lambda c: (_power(c), c["id"]))


def _bucket_cap(members):
    return _power(_captain(members))


def _fits(b, c):
    # 追加後のキャプテン（最大部隊）基準で上限を判定する
    return b["total"] + _march(c) <= _bucket_cap(b["members"] + [c])


def _assign(ev, parts):
    targets = (ev.get("shift") or {}).get("targets") or default_targets()
    buckets = [{"name": t["name"], "troop": t["troop"], "members": [],
                "total": 0, "cap": 0} for t in targets]
    reserves = []
    if not buckets:
        return buckets, sorted(parts, key=lambda c: (-_march(c), c["id"]))

    by_troop = {}
    for c in parts:
        by_troop.setdefault(c.get("troop_type") or "", []).append(c)

    rest = []
    for troop in sorted(by_troop):
        matched = [b for b in buckets if b["troop"] == troop]
        if matched:
            _lpt(by_troop[troop], matched, reserves)
        else:
            rest.extend(by_troop[troop])
    _lpt(rest, buckets, reserves)  # 一致する兵種の対象が無い参加者は全体へ

    for b in buckets:
        if b["members"]:
            cap_id = _captain(b["members"])["id"]
            # キャプテンを先頭に、以降は部隊規模の大きい順
            b["members"].sort(
                key=lambda c: (c["id"] != cap_id, -_march(c), c["id"]))
            b["captain"] = cap_id
            b["cap"] = _bucket_cap(b["members"])
        else:
            b["captain"] = None
            b["cap"] = 0
    reserves.sort(key=lambda c: (-_march(c), c["id"]))
    return buckets, reserves


def _lpt(chars, buckets, reserves):
    for c in sorted(chars, key=lambda c: (-_march(c), c["id"])):
        placed = False
        for b in sorted(buckets, key=lambda b: b["total"]):
            if not b["members"] or _fits(b, c):
                b["members"].append(c)
                b["total"] += _march(c)
                placed = True
                break
        if not placed:
            reserves.append(c)
