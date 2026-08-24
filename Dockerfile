FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg curl ca-certificates && \
    rm -rf /var/lib/apt/lists/* && \
    useradd --create-home --uid 10001 webtools

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN chown -R webtools:webtools /app

USER webtools

ENV FLASK_SESSION_SECURE=1 \
    PYTHONUNBUFFERED=1

EXPOSE 8000

# Single worker keeps download progress consistent without Redis.
# Raise threads for concurrent light requests.
CMD ["gunicorn", "app:app", "--bind", "0.0.0.0:8000", "--workers", "1", "--threads", "8", "--timeout", "120"]
