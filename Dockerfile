FROM python:3.11-slim

WORKDIR /app

# 仅核心系统依赖(字体 + 运行时,不含 Chromium)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

# 精简 requirements:去掉 playwright(lite/medium 不需要,deep 会降级)
COPY requirements.txt /tmp/req-full.txt
RUN grep -Ev '^(playwright|mplfinance)' /tmp/req-full.txt > requirements.txt && \
    pip install --no-cache-dir -r requirements.txt flask

COPY . .

# HF Spaces 约定端口 7860
ENV PORT=7860 \
    HOTMONEY_USER=kiko \
    HOTMONEY_PASS=kiko404 \
    HOTMONEY_CONCURRENCY=2 \
    UZI_SKIP_PLAYWRIGHT=1 \
    PYTHONUNBUFFERED=1

EXPOSE 7860

CMD ["python", "webapp.py"]
