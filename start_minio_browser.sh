cd .
pip install -r backend/requirements.txt

export MINIO_ENDPOINT=172.168.30.240:9000      # IP and MinIO port
export MINIO_ACCESS_KEY=MJH6633U5B9SNEWAS8I9
export MINIO_SECRET_KEY=faMQjNt1ipHf5u4lnCjbz+lMG5OtZ8I1u1nC6OU4
export MINIO_SECURE=false                       # if https  ->   true

uvicorn backend.main:app --host 0.0.0.0 --port 8000
