#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抓取 douyoyo 接口全量数据（所有 video_type），保存为 metadata.json。

video_type 说明：
  1=成片  2=分镜/素材  3=第三方  4=AI裂变/衍生回显  6=音频
  7=脚本  9=附件  10=达人素材  11=爆款素材  12=采集/个人收藏视频

环境变量：
  DOUYOYO_TOKEN  必填
  VIDEO_TYPES    逗号分隔，默认 "1,2,3,4,6,7,9,10,11,12"
  PAGESIZE       每页条数，默认 120
  MAX_PAGES      每类型最大页数，0=翻到底，默认 0
  META_OUTPUT    输出路径，默认 metadata.json
  SAVE_PER_TYPE  是否额外保存每类型单独文件，默认 false
"""
import json
import os
import sys
import time

import requests

API_URL = "https://api.douyoyo.com/v1/p/l/user/video/getList"
TOKEN = os.environ.get("DOUYOYO_TOKEN", "1d02ffbd554c3d8aa184b93471d60f41")
PAGESIZE = int(os.environ.get("PAGESIZE", "120"))
MAX_PAGES = int(os.environ.get("MAX_PAGES", "0"))
OUTPUT = os.environ.get("META_OUTPUT", "metadata.json")
SAVE_PER_TYPE = os.environ.get("SAVE_PER_TYPE", "false").lower() == "true"

VIDEO_TYPES = [
    int(x.strip())
    for x in os.environ.get("VIDEO_TYPES", "1,2,3,4,6,7,9,10,11,12").split(",")
    if x.strip()
]

VIDEO_TYPE_LABELS = {
    1: "成片",
    2: "分镜/素材",
    3: "第三方",
    4: "AI裂变/衍生回显",
    6: "音频",
    7: "脚本",
    9: "附件",
    10: "达人素材",
    11: "爆款素材",
    12: "采集/个人收藏视频",
}

BODY_BASE = {
    "video_type": 1,
    "page": 1,
    "pagesize": PAGESIZE,
    "isTalent": 2,
    "has_person_tag": 0,
    "author_type": 3,
    "authorPeopleType": 1,
    "time_type": 1,
    "platform_type": "7",
    "push_platform_type": [],
    "latest_launch_status": "",
    "not_push_platform_type": [],
    "is_satisfy": 2,
    "search_title": "",
    "taskProjectId": [],
}


def fetch_page(session, headers, video_type: int, page: int) -> dict:
    body = dict(BODY_BASE)
    body["video_type"] = video_type
    body["page"] = page

    last_err = None
    for attempt in range(3):
        try:
            r = session.post(API_URL, headers=headers, json=body, timeout=30)
            r.raise_for_status()
            payload = r.json()
            if payload.get("code") != 200:
                raise RuntimeError(f"code={payload.get('code')} msg={payload.get('msg')}")
            return payload
        except Exception as e:
            last_err = e
            print(f"[warn] vt={video_type} page={page} 第 {attempt + 1}/3 次失败: {e}",
                  file=sys.stderr)
            if attempt < 2:
                time.sleep(1 + attempt)
    raise RuntimeError(f"vt={video_type} page={page} 最终失败: {last_err}")


def fetch_by_type(session, headers, video_type: int) -> list[dict]:
    """抓取单个 video_type 的全部分页数据。"""
    label = VIDEO_TYPE_LABELS.get(video_type, str(video_type))
    print(f"\n=== video_type={video_type} ({label}) ===")

    items_all: list[dict] = []
    page = 1
    t0 = time.time()

    while True:
        payload = fetch_page(session, headers, video_type, page)
        data = payload.get("data") or {}
        items = data.get("list") or []
        total = data.get("total")
        total_page = data.get("total_page") or 0

        print(f"[vt={video_type}] page={page}/{total_page or '?'} "
              f"total={total} 本页 {len(items)} 条")

        # 终止条件 1：空页
        if not items:
            break
        items_all.extend(items)

        # 终止条件 2：到达 total_page
        if total_page and page >= int(total_page):
            break
        # 终止条件 3：最后一页不满
        if len(items) < PAGESIZE:
            break
        # 终止条件 4：达到 MAX_PAGES
        if MAX_PAGES > 0 and page >= MAX_PAGES:
            print(f"[vt={video_type}] 达到 MAX_PAGES={MAX_PAGES}，停止")
            break

        page += 1
        time.sleep(0.5)

    elapsed = time.time() - t0
    print(f"[vt={video_type}] 抓取完成：{len(items_all)} 条，耗时 {elapsed:.1f}s")
    return items_all


def save_json(items: list[dict], path: str) -> None:
    out_abs = os.path.abspath(path)
    os.makedirs(os.path.dirname(out_abs) or ".", exist_ok=True)
    with open(out_abs, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"[save] {len(items)} 条 -> {out_abs}")


def main() -> None:
    if not TOKEN:
        sys.exit("请设置环境变量 DOUYOYO_TOKEN")
    if not VIDEO_TYPES:
        sys.exit("VIDEO_TYPES 为空")

    print(f"计划抓取 video_type: {VIDEO_TYPES}")
    print(f"每页 {PAGESIZE} 条，MAX_PAGES={MAX_PAGES}（0=翻到底）")

    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "token": TOKEN,
        "Authorization": TOKEN,
    }
    session = requests.Session()

    merged: dict = {}                 # id -> item
    per_type_count: dict[int, int] = {}
    failed_types: list[int] = []
    duplicate_hits = 0

    for vt in VIDEO_TYPES:
        try:
            items = fetch_by_type(session, headers, vt)
        except Exception as e:
            print(f"[error] video_type={vt} 抓取失败，跳过: {e}", file=sys.stderr)
            per_type_count[vt] = 0
            failed_types.append(vt)
            continue

        per_type_count[vt] = len(items)

        if SAVE_PER_TYPE:
            save_json(items, f"metadata_vt{vt}.json")

        for item in items:
            key = item.get("id")
            if key is None:
                key = item.get("file_url") or f"no_id_{len(merged)}"
            if key in merged:
                duplicate_hits += 1
                continue
            merged[key] = item

        # 每完成一个类型就落盘一次，防止后面崩溃丢全部
        save_json(list(merged.values()), OUTPUT)

    # 最终汇总
    all_items = list(merged.values())
    save_json(all_items, OUTPUT)

    print("\n========== 汇总 ==========")
    for vt in VIDEO_TYPES:
        label = VIDEO_TYPE_LABELS.get(vt, str(vt))
        flag = "  [失败]" if vt in failed_types else ""
        print(f"  vt={vt:<2} {label:<18} {per_type_count.get(vt, 0):>6} 条{flag}")
    print(f"  跨类型重复(按 id) : {duplicate_hits} 条")
    print(f"  去重合并后总计    : {len(all_items)} 条")
    print(f"  输出文件          : {os.path.abspath(OUTPUT)}")

    if failed_types:
        print(f"\n[注意] 以下类型抓取失败，可单独重跑：")
        print(f"  VIDEO_TYPES={','.join(str(x) for x in failed_types)} "
              f"python build_index.py")
        sys.exit(1)


if __name__ == "__main__":
    main()
