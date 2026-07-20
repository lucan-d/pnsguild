"""フォーム入力の検証（一般側・管理側で共用）。"""
import re

from lib import config, i18n


def _num(s, label, errors):
    s = s.replace(",", "").replace("，", "").strip()
    if not s:
        return None
    if not s.isdigit() or len(s) > 12:
        errors.append(i18n.t("err_must_be_number", label=label))
        return None
    return int(s)


def validate_char(req):
    """キャラクター項目を検証して (data, errors) を返す。"""
    errors = []
    name = req.field("name")
    if not name:
        errors.append(i18n.t("err_name_required"))
    elif len(name) > 30:
        errors.append(i18n.t("err_name_too_long"))
    guild = req.field("guild")
    if len(guild) > 30:
        errors.append(i18n.t("err_guild_too_long"))
    troop = req.field("troop_type")
    if troop not in config.TROOP_TYPES:
        errors.append(i18n.t("err_troop_required"))
        troop = ""
    march = _num(req.field("march_size"), i18n.t("field_march_size"), errors)
    gather = _num(req.field("gather_size"), i18n.t("field_gather_size"), errors)
    tier = _num(req.field("tier"), i18n.t("field_tier"), errors)
    if tier is not None and not 1 <= tier <= 15:
        errors.append(i18n.t("err_tier_range"))
        tier = None
    shelter = req.field("shelter").replace("，", ",").replace(" ", "").replace("　", "")
    if shelter:
        m = re.fullmatch(r"(\d{1,4}),(\d{1,4})", shelter)
        if not m:
            errors.append(i18n.t("err_shelter_format"))
        elif int(m.group(1)) > 510 or int(m.group(2)) > 1022:
            errors.append(i18n.t("err_shelter_range"))
    return (dict(name=name, guild=guild, troop_type=troop,
                 march_size=march, gather_size=gather, tier=tier,
                 shelter=shelter),
            errors)
