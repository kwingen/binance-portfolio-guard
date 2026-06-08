#!/usr/bin/env bash
set -e

DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$DIR"

RED='\033[31m' GREEN='\033[32m' YELLOW='\033[33m' NC='\033[0m'

echo -e "${GREEN}╔══════════════════════════════════╗${NC}"
echo -e "${GREEN}║  Binance Portfolio Guard 部署   ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════╝${NC}"
echo ""

# ── 检测 Docker ──
if command -v docker &>/dev/null; then
    echo -e "${GREEN}[✓]${NC} Docker 已安装，使用 Docker 部署"
    echo ""

    if [ ! -f ".env" ]; then
        echo -e "${YELLOW}创建 .env 文件...${NC}"
        cat > .env << 'ENVEOF'
SL_PASSWORD=你的密码
SL_BINANCE_API_KEY=你的API_Key
SL_BINANCE_API_SECRET=你的API_Secret
SL_BINANCE_PROXY=
ENVEOF
        echo -e "${YELLOW}请编辑 .env 填入配置，然后运行:${NC}"
        echo "  docker compose up -d"
        exit 0
    fi

    echo "构建镜像..."
    docker compose build
    echo ""
    echo "启动服务..."
    docker compose up -d
    echo ""
    echo -e "${GREEN}✅ 部署完成！${NC}"
    echo "   地址: http://localhost:8080"
    echo "   日志: docker compose logs -f"
    exit 0
fi

# ── 无 Docker: 手动部署 ──
echo -e "${YELLOW}未检测到 Docker，使用手动部署${NC}"
echo ""

# Python
if ! command -v python3 &>/dev/null; then
    echo -e "${RED}请先安装 Python 3.12+${NC}"
    exit 1
fi

# 创建 venv
if [ ! -d ".venv" ]; then
    echo "创建 Python 虚拟环境..."
    python3 -m venv .venv
fi
source .venv/bin/activate
pip install -q -r requirements.txt

# 构建前端
if command -v node &>/dev/null; then
    echo "构建前端..."
    cd client && npm ci --silent && npm run build && cd ..
else
    if [ ! -d "client/dist" ]; then
        echo -e "${RED}需要 Node.js 构建前端，或下载预构建的 dist/${NC}"
        exit 1
    fi
    echo "使用已有前端构建产物"
fi

# 启动
if [ -z "$SL_PASSWORD" ]; then
    echo ""
    echo -e "${YELLOW}⚠️  未设置 SL_PASSWORD 环境变量${NC}"
    echo "   首次启动后将打印 Setup Token，在浏览器中输入即可"
    echo ""
fi

echo -e "${GREEN}启动服务器...${NC}"
python -m uvicorn server.main:app --host 0.0.0.0 --port 8080
