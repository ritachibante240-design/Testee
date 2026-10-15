FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY videos.db ./seed/videos.db
COPY storage/thumbnails/ ./seed/storage/thumbnails/
COPY storage/videos/videohub-compat-*.mp4 ./seed/storage/videos/
COPY start-container.sh ./start-container.sh

EXPOSE 8001

CMD ["sh", "/app/start-container.sh"]
