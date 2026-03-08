FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# System deps (optional but useful for audio transcoding in hosted voice mode).
# Keep minimal; add ffmpeg only if needed for Sonic input format conversion.
# RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*

COPY requirements.txt requirements.txt
COPY requirements-hosted.txt requirements-hosted.txt

RUN pip install --no-cache-dir -r requirements.txt -r requirements-hosted.txt

COPY leaksentinel leaksentinel
COPY services services
COPY scripts scripts
COPY ui ui
COPY docs docs
COPY data data
COPY README.md README.md
COPY plan.md plan.md

EXPOSE 8000

CMD ["python", "-m", "uvicorn", "services.api.main:app", "--host", "0.0.0.0", "--port", "8000"]

