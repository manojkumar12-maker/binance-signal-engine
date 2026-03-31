FROM python:3.11-slim

WORKDIR /app

COPY engine/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY engine/ .

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app/app

CMD ["python", "app/main.py"]
