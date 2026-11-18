#!/bin/sh

# 基本信息
curl http://127.0.0.1:8000/api/info

# 应返回：
# {"bucket":"video","endpoint":"...","metadata_count":15000,...}

# 列根目录（应看到 public/ 等目录）
curl 'http://127.0.0.1:8000/api/objects?prefix='

# 分类树（应看到 成片 / 破界冰霸杯 等）
curl http://127.0.0.1:8000/api/categories | head -c 500
