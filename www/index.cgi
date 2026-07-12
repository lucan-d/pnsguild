#!/usr/local/bin/python3
# 一般側エントリポイント。さくらで python3 が見つからない場合は
# シバンを `which python3` の結果に書き換えること。
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from wsgiref.handlers import CGIHandler

from lib.app import public_app

CGIHandler().run(public_app)
