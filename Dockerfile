# ── 阶段 1: 构建前端 ──
FROM node:22-alpine AS frontend
WORKDIR /build/client
COPY client/package*.json ./
RUN npm ci
COPY client/ ./
RUN npm run build

# ── 阶段 2: 运行时 ──
FROM python:3.13-alpine AS runtime
WORKDIR /app

# 安全: 非 root 运行
RUN adduser -D -h /app appuser

# 安装 Python 依赖
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 复制后端代码
COPY server/ ./server/
COPY binance_portfolio_sl.py ./

# 复制已构建的前端
COPY --from=frontend /build/client/dist ./client/dist/

# 权限
RUN mkdir -p /app/data && chown -R appuser:appuser /app
USER appuser

EXPOSE 8080

ENV PYTHONUNBUFFERED=1

VOLUME ["/app/data"]

CMD ["python", "-m", "uvicorn", "server.main:app", "--host", "0.0.0.0", "--port", "8080"]
