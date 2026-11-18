#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
接口已停用时，从之前导出的 video_list.csv 反向生成 metadata.json。
用法：python tools/csv_to_metadata.py video_list.csv data/metadata.json
"""
import csv
import json
import sys


def unflatten(row: dict) -> dict:
    obj: dict = {}
    for k, v in row.items():
        if v == "" or v is None:
            continue
        parts = k.split(".")
        cur = obj
        for p in parts[:-1]:
            cur = cur.setdefault(p, {})
        cur[parts[-1]] = v
    return obj


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("用法: python csv_to_metadata.py <input.csv> [output.json]")
    src = sys.argv[1]
    dst = sys.argv[2] if len(sys.argv) > 2 else "metadata.json"

    with open(src, encoding="utf-8-sig") as f:
        rows = [unflatten(r) for r in csv.DictReader(f)]

    # 类型还原
    for r in rows:
        for k in ("duration", "file_size"):
            if k in r and r[k] not in ("", None):
                try:
                    r[k] = int(float(r[k]))
                except (ValueError, TypeError):
                    pass
        for ck in ("cate_1_name", "cate_2_name", "cate_3_name"):
            if ck in r and isinstance(r[ck], dict) and "id" in r[ck]:
                try:
                    r[ck]["id"] = int(float(r[ck]["id"]))
                except (ValueError, TypeError):
                    pass

    with open(dst, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)
    print(f"[done] {len(rows)} 条 -> {dst}")


if __name__ == "__main__":
    main()
