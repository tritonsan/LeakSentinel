FROM python:3.10-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0 \
    STREAMLIT_SERVER_PORT=8501

WORKDIR /app

COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY leaksentinel leaksentinel
COPY scripts scripts
COPY ui ui
COPY data data

# Seed the dashboard with deterministic demo artifacts so the public UI is populated.
RUN python scripts/generate_flows.py \
    && python scripts/generate_thermal_images.py \
    && python scripts/build_spectrograms.py \
    && python scripts/create_manifest.py \
    && python -m leaksentinel run --scenario-id S05 --mode local --judge-mode \
    && python -m leaksentinel ops incident-open --scenario-id S05 --mode local

EXPOSE 8501

CMD ["streamlit", "run", "ui/dashboard.py", "--server.address", "0.0.0.0", "--server.port", "8501", "--server.headless", "true"]
