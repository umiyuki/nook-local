#!/bin/bash

# ディレクトリに移動
cd /root/nook-tomatio13/nook-local

# 仮想環境を有効化
source .venv/bin/activate

# すべてのサービスを実行
python -m nook.services.run_services --service all

# 仮想環境を無効化
deactivate