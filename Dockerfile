# AutoRFQ with live ferguson.com lookups: the web app, the inbox watcher and a real Chromium on an
# invisible virtual display (Xvfb). ferguson.com refuses headless Chrome, so the browser is headed but hidden.
#   docker build -t autorfq . && docker run -p 8000:8000 --env-file .env autorfq
# Build web/dist first (cd web && npm ci && npm run build); scripts/deploy_azure.py --target container does it.
FROM python:3.12-slim-bookworm

RUN apt-get update \
 && apt-get install -y --no-install-recommends tini chromium xvfb xauth fonts-liberation fonts-dejavu-core ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN grep -v -i '^pytest' requirements.txt > /tmp/req.txt && pip install --no-cache-dir -r /tmp/req.txt

COPY app app
COPY rfq rfq
COPY data data
COPY templates templates
COPY reference reference
COPY emails emails
COPY web/dist web/dist
COPY mailbot.py ./

ENV RFQ_MODE=live \
    RFQ_IN_CONTAINER=1 \
    RFQ_OUT_DIR=/data/out \
    RFQ_PRODUCTS_DB=/data/out/products.db \
    PYTHONUNBUFFERED=1
EXPOSE 8000
# tini reaps the browser processes each live run leaves behind
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["python", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
