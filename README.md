# MinIO 视频文件库

基于 MinIO S3 协议的视频浏览/播放/下载 Web 项目，支持目录浏览和业务三级分类。

- 后端：FastAPI + MinIO SDK
- 前端：原生 HTML + Tailwind CDN（单文件）
- 部署：Docker Compose

## 关键概念

| 名称 | 含义 |
| :--- | :--- |
| `hdd1`~`hdd4` | MinIO 纠删码阵列的**物理数据盘**，不是 bucket |
| `video` | 逻辑 **bucket**（MinIO Web Console 里看到的桶） |
| `public/2026/10/20/xxx.mp4` | **object_name**，即接口返回的 `file_url` |
| 纠删码 | 对象被切分片写到多块盘，**不能直接读物理文件**，必须走 S3 API |

`/mnt/hdd3/video/public/...` 中 `/mnt/hdd3` 是挂载点，`video` 是 bucket，`public/...` 是 object_name。

## 部署步骤

### 1. 准备目录

```bash
mkdir -p minio-browser/{backend,frontend,tools,data}
# 把上面的文件按结构放好
```

### 2. 配置环境

```bash
cp .env.example .env
vi .env
# 填 MINIO_ENDPOINT / MINIO_ACCESS_KEY / MINIO_SECRET_KEY / DOUYOYO_TOKEN
# MINIO_BUCKET=video，FILE_URL_PREFIX 留空
```

### 3. 生成元数据索引（分类和封面依赖它）

**方式 A：接口可用**（推荐，在容器里跑，不污染宿主机环境）

```bash
docker compose --profile tools run --rm build-index
# 生成 ./data/metadata.json
```

**方式 B：接口不可用，但有之前导出的 CSV**

```bash
python tools/csv_to_metadata.py video_list.csv data/metadata.json
```

**方式 C：手动放**

把已有的 `metadata.json` 放到 `./data/` 目录即可。

> 后端会监听 `metadata.json` 的 mtime，文件更新后无需重启容器，刷新页面即生效。

### 4. 启动服务

```bash
docker compose up -d --build
docker compose logs -f web
```

打开 `http://<服务器IP>:8000`。

## 网络说明

- **MinIO 与容器在同一台宿主机**：`.env` 里 `MINIO_ENDPOINT=host.docker.internal:9000`（compose 已配置 `host-gateway`）。
- **MinIO 在另一台机器**：写那台机器的内网 IP，如 `192.168.1.100:9000`。
- MinIO 是 HTTPS：`MINIO_SECURE=true`，endpoint 不带 `https://`。

## 验证

```bash
# 健康检查
curl http://127.0.0.1:8000/api/info

# 列目录（应看到 public/ 等）
curl 'http://127.0.0.1:8000/api/objects?prefix='

# 分类树
curl http://127.0.0.1:8000/api/categories
```

也可以进入容器用 mc 验证桶和对象：

```bash
docker compose exec web python - <<'PY'
from minio import Minio
import os
c = Minio(os.getenv("MINIO_ENDPOINT"), access_key=os.getenv("MINIO_ACCESS_KEY"),
          secret_key=os.getenv("MINIO_SECRET_KEY"),
          secure=os.getenv("MINIO_SECURE","false").lower()=="true")
print([b.name for b in c.list_buckets()])
print(c.stat_object("video", "public/2026/10/20/f23e8b17f2f363d329ff839277c0fb29.mp4"))
PY
```

## 功能说明

| 功能 | 路径 |
| :--- | :--- |
| 目录浏览（类 FTP） | 左侧「📂 全部文件」 |
| 业务三级分类 | 左侧分类树，点击任意层级过滤 |
| 视频在线播放（可拖进度条） | 点击视频卡片，HTTP Range 流式代理 |
| 封面缩略图 | 直接读取 `cover_url` 对应的 MinIO 对象 |
| 下载 | `/api/download?object=...` |

## 常见问题

**封面显示不出来**：确认 MinIO 里 `cover_url` 对应的 `.jpg` 存在。若不存在，前端会回退到纯黑背景，不影响使用。

**分类树为空**：`data/metadata.json` 没生成或为空，执行第 3 步。

**`stat_object` 报 NoSuchKey**：核对 `mc ls myminio/video/public/2026/10/20/`，若实际路径多了一层前缀，调整 `FILE_URL_PREFIX`。

**连接 MinIO 超时**：检查容器网络能否访问 MinIO，Linux 上用 `host.docker.internal` 需 compose 里 `extra_hosts`（已内置）。
