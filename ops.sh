#!/usr/bin/env bash
# ============================================================
# minio-browser 运维脚本
# 用法: ./ops.sh <命令>
# 命令: up | stop | restart | rebuild | logs | status | health
#       build-index | shell | backup | clean | help
# ============================================================
set -uo pipefail

# ---------- 配置 ----------
PROJECT_DIR="/root/minio-browser"
SERVICE="web"
CONTAINER="minio-browser"
PORT=8000
# ----------------------------

cd "$PROJECT_DIR" || { echo "❌ 目录不存在: $PROJECT_DIR"; exit 1; }

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; BLUE='\033[0;34m'; NC='\033[0m'
info()  { echo -e "${BLUE}[info]${NC} $*"; }
ok()    { echo -e "${GREEN}[ok]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $*"; }
err()   { echo -e "${RED}[error]${NC} $*"; }

# 检查 docker 是否可用
check_docker() {
    if ! docker info >/dev/null 2>&1; then
        err "Docker 未运行或无权限。先执行: systemctl status docker"
        exit 1
    fi
}

# ---------- 命令实现 ----------

cmd_up() {
    check_docker
    info "启动服务（不重建镜像）..."
    docker compose up -d
    ok "已启动"
    cmd_status
}

cmd_stop() {
    info "停止服务（保留容器和数据）..."
    docker compose stop
    ok "已停止"
}

cmd_down() {
    info "停止并移除容器（data/ 里的 metadata.json 保留）..."
    docker compose down
    ok "已移除"
}

cmd_restart() {
    check_docker
    info "重启容器（不重建镜像，不重新读 .env）..."
    docker compose restart "$SERVICE"
    ok "已重启"
    cmd_status
}

cmd_rebuild() {
    check_docker
    info "重新构建镜像并启动（代码改动后必用）..."
    docker compose up -d --build "$SERVICE"
    ok "已重建并启动"
    sleep 2
    cmd_health
}

cmd_recreate() {
    check_docker
    info "强制重建容器（改了 .env 后必用）..."
    docker compose up -d --force-recreate "$SERVICE"
    ok "已重建容器"
    cmd_status
}

cmd_logs() {
    info "实时日志（Ctrl+C 退出，不影响容器）..."
    docker compose logs -f --tail=100 "$SERVICE"
}

cmd_status() {
    echo
    docker compose ps
    echo
}

cmd_health() {
    info "健康检查 http://127.0.0.1:${PORT}/api/info"
    if curl -fsS --max-time 5 "http://127.0.0.1:${PORT}/api/info" 2>/dev/null; then
        echo
        ok "服务正常"
    else
        echo
        err "服务无响应，查看日志: ./ops.sh logs"
        return 1
    fi
}

cmd_build_index() {
    check_docker
    info "抓取接口生成 metadata.json（全量，耗时较长）..."
    docker compose --profile tools run --rm build-index
    ok "完成。后端会自动重载，无需重启"
    cmd_health
}

cmd_build_index_test() {
    check_docker
    info "试抓每种类型 2 页（快速验证 token）..."
    docker compose --profile tools run --rm -e MAX_PAGES=2 build-index
}

cmd_shell() {
    info "进入容器 shell..."
    docker compose exec "$SERVICE" bash || docker compose exec "$SERVICE" sh
}

cmd_backup() {
    local ts=$(date +%Y%m%d_%H%M%S)
    local src="data/metadata.json"
    if [ -f "$src" ]; then
        local dst="data/metadata.json.bak_${ts}"
        cp "$src" "$dst"
        ok "已备份 -> $dst ($(du -h "$dst" | cut -f1))"
    else
        warn "metadata.json 不存在，跳过"
    fi
}

cmd_clean() {
    warn "清理未使用的镜像和构建缓存（不影响运行中的容器）..."
    docker image prune -f
    docker builder prune -f
    ok "已清理"
}

cmd_help() {
    cat <<EOF
minio-browser 运维脚本

用法: ./ops.sh <命令>

  up              启动服务（不重建）
  stop            停止服务（保留容器）
  down            停止并移除容器（数据保留）
  restart         重启容器（改 .env 无效，改代码无效）
  rebuild         重新构建镜像并启动  ← 改了前端/后端代码后用这个
  recreate        强制重建容器        ← 改了 .env 后用这个
  logs            实时日志
  status          查看容器状态
  health          健康检查接口
  build-index     抓全量 metadata（接口可用时）
  build-index-test 试抓 2 页验证 token
  shell           进入容器
  backup          备份 metadata.json
  clean           清理未使用镜像和缓存
  help            显示帮助

常见场景:
  改了 frontend/index.html  -> ./ops.sh rebuild
  改了 backend/main.py      -> ./ops.sh rebuild
  改了 .env                 -> ./ops.sh recreate
  更新了 metadata.json      -> 无需操作，后端自动重载
  只想重启                 -> ./ops.sh restart
EOF
}

# ---------- 分发 ----------
case "${1:-help}" in
    up)               cmd_up ;;
    stop)             cmd_stop ;;
    down)             cmd_down ;;
    restart)          cmd_restart ;;
    rebuild)          cmd_rebuild ;;
    recreate)         cmd_recreate ;;
    logs)             cmd_logs ;;
    status)           cmd_status ;;
    health)           cmd_health ;;
    build-index)      cmd_build_index ;;
    build-index-test) cmd_build_index_test ;;
    shell)            cmd_shell ;;
    backup)           cmd_backup ;;
    clean)            cmd_clean ;;
    help|-h|--help)   cmd_help ;;
    *)                err "未知命令: $1"; cmd_help; exit 1 ;;
esac
