"""HTML生成の共通部品。可変値は必ず h() でエスケープして埋め込むこと。"""
import html

from lib import config, i18n


def h(s):
    return html.escape(str(s), quote=True)


def url(path):
    return config.BASE + path


def _langswitch_html():
    switch = i18n.switch_links()
    if not switch:
        return ""
    links = "".join(
        '<a class="%s" href="%s">%s</a>' % ("on" if cur else "", h(href), h(label))
        for href, label, cur in switch)
    return '<nav class="langswitch">%s</nav>' % links


def page(title, body, back=None, wide=False):
    backlink = ""
    if back:
        backlink = '<a class="back" href="%s">&laquo; %s</a>' % (h(back), i18n.t("back_link"))
    klass = "wide" if wide else ""
    return """<!DOCTYPE html>
<html lang="%s">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>%s - %s</title>
<link rel="stylesheet" href="%s">
</head>
<body class="%s">
<header><a href="%s">%s</a>%s</header>
<main>
%s
<h1>%s</h1>
%s
</main>
<footer>%s</footer>
</body>
</html>""" % (h(i18n.current()), h(title), h(config.SITE_NAME),
              url("/static/style.css"), klass,
              url("/"), h(config.SITE_NAME), _langswitch_html(),
              backlink, h(title), body,
              h(config.SITE_NAME))


def errors_html(errors):
    errors = [e for e in errors if e]
    if not errors:
        return ""
    lis = "".join("<li>%s</li>" % h(e) for e in errors)
    return '<ul class="errors">%s</ul>' % lis


def notice(msg):
    if not msg:
        return ""
    return '<p class="notice">%s</p>' % h(msg)


def fmt_num(n):
    if n is None or n == "":
        return "-"
    return "{:,}".format(n)


def fmt_march(n, tier):
    """部隊規模とTierの結合表示。例: 500,000(T8)"""
    s = fmt_num(n)
    if tier:
        s += "(T%s)" % tier
    return s


def troop_badge(t):
    if not t:
        return ""
    return '<span class="badge badge-%s">%s</span>' % (h(t), h(t))
