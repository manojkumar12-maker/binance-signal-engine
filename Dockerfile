FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN mkdir -p /app/data /app/logs

ENV TRADING_MODE=demo
ENV BROKER_ENABLED=false
ENV AUTO_TRADE=false
ENV LIVE_TRADING_ENABLED=false
ENV USE_TESTNET=true

EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

CMD ["python", "main.py"]