FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 APP_ENV=local
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg fonts-dejavu-core \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt constraints.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app app
COPY assets assets
COPY episodes episodes
RUN mkdir -p data/tmp output logs
ENTRYPOINT ["python", "-m", "app.main"]
CMD ["run"]
