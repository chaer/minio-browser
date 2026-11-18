# 1. 配环境
cp .env.example .env && vi .env

# 2. 生成元数据（接口可用时）
docker compose --profile tools run --rm build-index

# 3. 启动
docker compose up -d --build

# 4. 访问
# http://172.168.30.240:8000
