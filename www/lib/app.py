"""WSGIアプリケーションの組み立て。CGIと開発サーバーの両方から使う。"""
from lib import admin, host, i18n, public
from lib.web import make_app


def _with_lang(routes, force_lang=None):
    def wrap(fn):
        def wrapped(req, *args):
            i18n.begin_request(req, force_lang=force_lang)
            return fn(req, *args)
        return wrapped
    return [(m, p, wrap(fn)) for m, p, fn in routes]


public_app = make_app(_with_lang(public.ROUTES + host.ROUTES) + i18n.ROUTES)
admin_app = make_app(_with_lang(admin.ROUTES, force_lang=i18n.DEFAULT))
