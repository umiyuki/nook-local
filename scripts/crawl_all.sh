#!/bin/bash

#1 ディレクトリの移動
cd /app

#2 python変数変更
#source venv/bin/activate

#3 ニュースの取得
python -m nook.services.run_services --service hackernews
python -m nook.services.run_services --service github
python -m nook.services.run_services --service paper
python -m nook.services.run_services --service techfeed
python -m nook.services.run_services --service reddit

#4 ニュースの登録

#deactivate
