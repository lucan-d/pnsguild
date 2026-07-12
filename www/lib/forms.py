"""フォーム入力の検証（一般側・管理側で共用）。"""
import re

from lib import config


def _num(s, label, errors):
    s = s.replace(",", "").replace("，", "").strip()
    if not s:
        return None
    if not s.isdigit() or len(s) > 12:
        errors.append(label + "は数値で入力してください")
        return None
    return int(s)


def validate_char(req):
    """キャラクター項目を検証して (data, errors) を返す。"""
    errors = []
    name = req.field("name")
    if not name:
        errors.append("キャラクター名を入力してください")
    elif len(name) > 30:
        errors.append("キャラクター名は30文字以内にしてください")
    guild = req.field("guild")
    if len(guild) > 30:
        errors.append("ギルド名は30文字以内にしてください")
    troop = req.field("troop_type")
    if troop not in config.TROOP_TYPES:
        errors.append("特化兵種を選択してください")
        troop = ""
    march = _num(req.field("march_size"), "部隊規模", errors)
    gather = _num(req.field("gather_size"), "ギャザー規模", errors)
    tier = _num(req.field("tier"), "Tier", errors)
    if tier is not None and not 1 <= tier <= 15:
        errors.append("Tierは1〜15で入力してください")
        tier = None
    shelter = req.field("shelter").replace("，", ",").replace(" ", "").replace("　", "")
    if shelter:
        m = re.fullmatch(r"(\d{1,4}),(\d{1,4})", shelter)
        if not m:
            errors.append("避難所座標は「123,456」の形式で入力してください")
        elif int(m.group(1)) > 510 or int(m.group(2)) > 1022:
            errors.append("避難所座標の範囲は 0〜510 , 0〜1022 です")
    return (dict(name=name, guild=guild, troop_type=troop,
                 march_size=march, gather_size=gather, tier=tier,
                 shelter=shelter),
            errors)
