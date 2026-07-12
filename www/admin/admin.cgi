#!/usr/local/bin/python3
# 管理側エントリポイント。Basic認証は同ディレクトリの .htaccess で行う。
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from wsgiref.handlers import CGIHandler

from lib.app import admin_app

CGIHandler().run(admin_app)
