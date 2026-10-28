# LawLens 镜像：前端构建 + 后端运行
# 构建：docker build -f deploy/Dockerfile -t lawlens .
# 运行：见 docker-compose.yml

# ---------- 1. 构建前端 ----------
FROM node:20-alpine AS web
WORKDIR /app/frontend
RUN corepack enable
COPY frontend/package.json frontend/pnpm-lock.yaml ./
RUN pnpm install --frozen-lockfile
COPY frontend/ ./
RUN pnpm build

# ---------- 2. 运行后端 ----------
FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8 \
    DILIGENCE_DATA_DIR=/data

WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY --from=web /app/frontend/dist frontend/dist

# 数据目录：数据库、上传件、报告
RUN mkdir -p /data/uploads /data/reports
VOLUME ["/data"]

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=3).status==200 else 1)"

CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]
