FROM python:3.11-slim AS builder

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn gevent

FROM python:3.11-slim

RUN groupadd -r trading && useradd -r -g trading trading && \
    mkdir -p /app/data && chown trading:trading /app/data

WORKDIR /app

COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

COPY . .

RUN chown -R trading:trading /app

USER trading

EXPOSE 8080

ENV DATABASE_URL=sqlite:///data/trades.db
ENV JSON_LOGGING=true
ENV PYTHONUNBUFFERED=1

CMD ["gunicorn", "-w", "2", "-k", "gevent", "--worker-connections", "1000", \
     "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-", \
     "--bind", "0.0.0.0:8080", "main:app"]
