import os
import json
import urllib.parse
from pathlib import Path
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from minio import Minio
from minio.error import S3Error

app = FastAPI(title="MinIO 视频文件库")

# ================= 配置 =================
MINIO_ENDPOINT   = os.getenv("MINIO_ENDPOINT", "127.0.0.1:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY", "")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY", "")
MINIO_SECURE     = os.getenv("MINIO_SECURE", "false").lower() == "true"
MINIO_BUCKET     = os.getenv("MINIO_BUCKET", "video")
METADATA_PATH    = os.getenv("METADATA_PATH", "/app/data/metadata.json")
FILE_URL_PREFIX  = os.getenv("FILE_URL_PREFIX", "")

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

client = Minio(MINIO_ENDPOINT, access_key=MINIO_ACCESS_KEY,
               secret_key=MINIO_SECRET_KEY, secure=MINIO_SECURE)

# ================= 元数据 =================
METADATA: dict[str, dict] = {}
_metadata_mtime: float = 0.0


def _to_object(url: str) -> str:
    if not url:
        return ""
    if FILE_URL_PREFIX and url.startswith(FILE_URL_PREFIX):
        return url[len(FILE_URL_PREFIX):]
    return url


def _load_metadata() -> None:
    global METADATA
    p = Path(METADATA_PATH)
    if not p.exists():
        METADATA = {}
        print(f"[warn] metadata not found: {p}")
        return
    try:
        items = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[error] failed to load metadata: {e}")
        return
    m = {}
    for it in items:
        obj = _to_object(it.get("file_url", ""))
        if obj:
            m[obj] = it
    METADATA = m
    print(f"[info] loaded {len(METADATA)} metadata entries")


def maybe_reload_metadata() -> None:
    global _metadata_mtime
    p = Path(METADATA_PATH)
    if not p.exists():
        return
    mtime = p.stat().st_mtime
    if mtime != _metadata_mtime:
        _metadata_mtime = mtime
        _load_metadata()


maybe_reload_metadata()


# ================= 工具 =================
def _guess_content_type(name: str) -> str:
    ext = name.lower().rsplit(".", 1)[-1] if "." in name else ""
    return {
        "mp4": "video/mp4", "webm": "video/webm", "mov": "video/quicktime",
        "avi": "video/x-msvideo", "mkv": "video/x-matroska",
        "mp3": "audio/mpeg", "wav": "audio/wav", "m4a": "audio/mp4",
        "jpg": "image/jpeg", "jpeg": "image/jpeg", "png": "image/png",
        "gif": "image/gif", "webp": "image/webp", "pdf": "application/pdf",
    }.get(ext, "application/octet-stream")


def _cover_of(obj_name: str, meta: dict) -> str:
    cover = _to_object(meta.get("cover_url", ""))
    if cover:
        return cover
    return obj_name.rsplit(".", 1)[0] + ".jpg"


def _match(meta: dict, video_type: int = 0, cate1_id: int = 0,
           cate2_id: int = 0, cate3_id: int = 0, label_id: int = 0,
           team_id: int = 0, group_id: int = 0, search: str = "") -> bool:
    if video_type and meta.get("video_type") != video_type:
        return False
    if cate1_id and (meta.get("cate_1_name") or {}).get("id") != cate1_id:
        return False
    if cate2_id and (meta.get("cate_2_name") or {}).get("id") != cate2_id:
        return False
    if cate3_id and (meta.get("cate_3_name") or {}).get("id") != cate3_id:
        return False
    if team_id and meta.get("team_id") != team_id:
        return False
    if group_id and meta.get("group_id") != group_id:
        return False
    if label_id:
        labels = [t.get("id") for t in (meta.get("public_labels") or [])]
        if label_id not in labels:
            return False
    if search:
        s = search.lower()
        text = " ".join([
            str(meta.get("title") or ""),
            str(meta.get("file_name") or ""),
            str(meta.get("real_name") or ""),
            str((meta.get("cate_2_name") or {}).get("title") or ""),
            str((meta.get("cate_3_name") or {}).get("title") or ""),
        ]).lower()
        if s not in text:
            return False
    return True


def _item_from_meta(obj_name: str, meta: dict) -> dict:
    return {
        "object_name": obj_name,
        "cover_object": _cover_of(obj_name, meta),
        "title": meta.get("title") or meta.get("file_name") or obj_name.split("/")[-1],
        "file_name": meta.get("file_name") or "",
        "video_type": meta.get("video_type", 0),
        "video_type_label": VIDEO_TYPE_LABELS.get(meta.get("video_type", 0), ""),
        "duration": meta.get("duration"),
        "file_size": meta.get("file_size"),
        "real_name": meta.get("real_name") or "",
        "team_name": meta.get("team_name") or "",
        "group_name": meta.get("group_name") or "",
        "shoot_time": meta.get("shoot_time") or "",
        "create_time": meta.get("create_time") or "",
        "cate_1": (meta.get("cate_1_name") or {}).get("title", ""),
        "cate_2": (meta.get("cate_2_name") or {}).get("title", ""),
        "cate_3": (meta.get("cate_3_name") or {}).get("title", ""),
        "public_labels": [t.get("tag_title", "") for t in (meta.get("public_labels") or [])],
        "down_cnt": meta.get("down_cnt", 0),
    }


# ================= API：基础信息 =================
@app.get("/api/info")
def info():
    maybe_reload_metadata()
    return {
        "bucket": MINIO_BUCKET,
        "endpoint": MINIO_ENDPOINT,
        "metadata_count": len(METADATA),
        "file_url_prefix": FILE_URL_PREFIX,
        "video_type_labels": VIDEO_TYPE_LABELS,
    }


# ================= API：目录浏览（保持不变） =================
@app.get("/api/objects")
def list_objects(prefix: str = Query("")):
    maybe_reload_metadata()
    if prefix and not prefix.endswith("/"):
        prefix += "/"
    try:
        objects = client.list_objects(MINIO_BUCKET, prefix=prefix, recursive=False)
        dirs, files = [], []
        for obj in objects:
            if obj.is_dir:
                dirs.append(obj.object_name)
            else:
                meta = METADATA.get(obj.object_name, {})
                files.append({
                    "name": obj.object_name,
                    "size": obj.size,
                    "last_modified": obj.last_modified.isoformat() if obj.last_modified else None,
                    "cover_object": _cover_of(obj.object_name, meta),
                    "title": meta.get("title") or "",
                    "cate_2": (meta.get("cate_2_name") or {}).get("title", ""),
                    "cate_3": (meta.get("cate_3_name") or {}).get("title", ""),
                    "real_name": meta.get("real_name", ""),
                    "duration": meta.get("duration"),
                })
        return {"dirs": sorted(dirs), "files": sorted(files, key=lambda x: x["name"])}
    except S3Error as e:
        raise HTTPException(500, f"MinIO error: {e}")


# ================= API：多维统计（facets） =================
@app.get("/api/facets")
def facets(video_type: int = Query(0)):
    """返回 video_type 列表、三级分类树、标签、团队，都带计数。

    - video_types：始终统计全量（不受 video_type 参数影响），便于切换类型
    - 分类树/标签/团队：按 video_type 过滤后再统计
    """
    maybe_reload_metadata()

    vt_counter: dict[int, int] = {}
    for meta in METADATA.values():
        vt = meta.get("video_type", 0)
        if vt:
            vt_counter[vt] = vt_counter.get(vt, 0) + 1

    tree: dict = {}
    label_counter: dict[int, dict] = {}
    team_counter: dict[int, dict] = {}

    for meta in METADATA.values():
        if video_type and meta.get("video_type") != video_type:
            continue

        c1 = meta.get("cate_1_name") or {}
        c2 = meta.get("cate_2_name") or {}
        c3 = meta.get("cate_3_name") or {}

        n1 = tree.setdefault(c1.get("id", 0), {
            "id": c1.get("id", 0), "title": c1.get("title") or "未分类",
            "count": 0, "children": {},
        })
        n1["count"] += 1
        if c2.get("id"):
            n2 = n1["children"].setdefault(c2["id"], {
                "id": c2["id"], "title": c2.get("title", ""),
                "count": 0, "children": {},
            })
            n2["count"] += 1
            if c3.get("id"):
                n3 = n2["children"].setdefault(c3["id"], {
                    "id": c3["id"], "title": c3.get("title", ""),
                    "count": 0, "children": {},
                })
                n3["count"] += 1

        for t in (meta.get("public_labels") or []):
            lid = t.get("id")
            if lid:
                e = label_counter.setdefault(lid, {
                    "id": lid, "title": t.get("tag_title", ""), "count": 0,
                })
                e["count"] += 1

        tid = meta.get("team_id")
        if tid:
            e = team_counter.setdefault(tid, {
                "id": tid, "title": meta.get("team_name", ""), "count": 0,
            })
            e["count"] += 1

    def to_list(node):
        return {
            "id": node["id"], "title": node["title"], "count": node["count"],
            "children": [to_list(c) for c in node["children"].values()],
        }

    return {
        "video_types": sorted(
            [
                {"id": vid, "label": VIDEO_TYPE_LABELS.get(vid, f"类型{vid}"), "count": cnt}
                for vid, cnt in vt_counter.items()
            ],
            key=lambda x: (x["id"] != 1, x["id"]),  # 成片排第一
        ),
        "categories": sorted(
            [to_list(n) for n in tree.values()],
            key=lambda x: -x["count"],
        ),
        "labels": sorted(label_counter.values(), key=lambda x: -x["count"]),
        "teams": sorted(team_counter.values(), key=lambda x: -x["count"]),
    }


# ================= API：多维过滤 + 分页 =================
@app.get("/api/objects/filter")
def filter_objects(
    video_type: int = Query(0),
    cate1_id: int = Query(0),
    cate2_id: int = Query(0),
    cate3_id: int = Query(0),
    label_id: int = Query(0),
    team_id: int = Query(0),
    group_id: int = Query(0),
    search: str = Query(""),
    page: int = Query(1, ge=1),
    pagesize: int = Query(60, ge=1, le=200),
    sort: str = Query("create_time_desc"),
):
    maybe_reload_metadata()
    matched = []
    for obj, meta in METADATA.items():
        if _match(meta, video_type, cate1_id, cate2_id, cate3_id,
                  label_id, team_id, group_id, search):
            matched.append((obj, meta))

    if sort == "create_time_asc":
        matched.sort(key=lambda x: x[1].get("create_time", ""))
    elif sort == "duration_desc":
        matched.sort(key=lambda x: x[1].get("duration") or 0, reverse=True)
    elif sort == "down_desc":
        matched.sort(key=lambda x: x[1].get("down_cnt") or 0, reverse=True)
    else:
        matched.sort(key=lambda x: x[1].get("create_time", ""), reverse=True)

    total = len(matched)
    start = (page - 1) * pagesize
    items = [_item_from_meta(obj, meta) for obj, meta in matched[start:start + pagesize]]
    return {"total": total, "page": page, "pagesize": pagesize, "items": items}


# ================= API：流式预览 / 下载 =================
@app.get("/api/preview")
def preview(object: str, request: Request):
    try:
        stat = client.stat_object(MINIO_BUCKET, object)
        file_size = stat.size
        range_header = request.headers.get("range")
        start, end, status_code = 0, file_size - 1, 200
        headers = {
            "Accept-Ranges": "bytes",
            "Content-Type": _guess_content_type(object),
            "Content-Disposition": f'inline; filename="{urllib.parse.quote(object.split("/")[-1])}"',
        }
        if range_header:
            try:
                rng = range_header.replace("bytes=", "").split("-")
                start = int(rng[0]) if rng[0] else 0
                end = int(rng[1]) if len(rng) > 1 and rng[1] else file_size - 1
            except ValueError:
                raise HTTPException(416, "Invalid Range")
            if start >= file_size:
                raise HTTPException(416, "Range Not Satisfiable")
            end = min(end, file_size - 1)
            status_code = 206
            headers["Content-Range"] = f"bytes {start}-{end}/{file_size}"
        headers["Content-Length"] = str(end - start + 1)
        resp = client.get_object(MINIO_BUCKET, object, offset=start, length=end - start + 1)

        def iterfile():
            try:
                for chunk in resp.stream(64 * 1024):
                    yield chunk
            finally:
                resp.close()
                resp.release_conn()

        return StreamingResponse(iterfile(), status_code=status_code,
                                 headers=headers, media_type=headers["Content-Type"])
    except S3Error as e:
        raise HTTPException(404, f"object not found: {object} ({e})")


@app.get("/api/download")
def download(object: str):
    try:
        resp = client.get_object(MINIO_BUCKET, object)
        filename = object.split("/")[-1]

        def iterfile():
            try:
                for chunk in resp.stream(64 * 1024):
                    yield chunk
            finally:
                resp.close()
                resp.release_conn()

        return StreamingResponse(
            iterfile(),
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{urllib.parse.quote(filename)}"'},
        )
    except S3Error as e:
        raise HTTPException(404, f"object not found: {object} ({e})")


# ================= 静态资源（必须最后） =================
FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")
app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="static")
