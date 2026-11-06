# One image for both cloud pieces:
#   Cloud Run service  -> the web app (default CMD)
#   Cloud Run job      -> `python -m aicc_demo.web.job` (set by deploy/gcp.sh)

# --- frontend -------------------------------------------------------------
FROM node:22-slim AS ui
WORKDIR /build/web
COPY web/package.json web/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY web/ ./
# vite writes to ../src/aicc_demo/web/static
RUN npm run build

# --- app ------------------------------------------------------------------
FROM python:3.12-slim
# JavaScript runtime yt-dlp uses for YouTube's challenges.
COPY --from=denoland/deno:bin /deno /usr/local/bin/deno
RUN apt-get update \
 && apt-get install -y --no-install-recommends ffmpeg tesseract-ocr tesseract-ocr-eng \
 && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY --from=ui /build/src/aicc_demo/web/static ./src/aicc_demo/web/static
# Editable install keeps the built UI next to the package code.
RUN pip install --no-cache-dir -e ".[cloud]"
# Bake the Whisper model in, so job tasks don't download it on every run.
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"

ENV AICC_MODE=cloud PYTHONUNBUFFERED=1 PORT=8080
CMD exec uvicorn --factory aicc_demo.web.app:create_app_from_env --host 0.0.0.0 --port ${PORT}
