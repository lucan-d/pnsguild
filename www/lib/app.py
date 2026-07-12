"""WSGIアプリケーションの組み立て。CGIと開発サーバーの両方から使う。"""
from lib import admin, host, public
from lib.web import make_app

public_app = make_app(public.ROUTES + host.ROUTES)
admin_app = make_app(admin.ROUTES)
