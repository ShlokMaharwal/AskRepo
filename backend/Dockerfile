FROM python:3.11-slim
ARG LITE_MODE=false
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 \
    ASKREPO_DATA_DIR=/data ASKREPO_MODEL_CACHE=/opt/models LITE_MODE=${LITE_MODE}
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends git ca-certificates libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --uid 1000 askrepo \
    && mkdir /data /opt/models && chown askrepo:askrepo /data /opt/models
COPY requirements*.txt ./
RUN if [ "$LITE_MODE" = "true" ]; then \
      pip install --no-cache-dir -r requirements-lite.txt; \
    else \
      pip install --no-cache-dir 'torch>=2.6,<3' --index-url https://download.pytorch.org/whl/cpu \
      && pip install --no-cache-dir -r requirements.txt; \
    fi
COPY scripts/download_models.py ./scripts/download_models.py
RUN if [ "$LITE_MODE" != "true" ]; then python scripts/download_models.py; fi \
    && chown -R askrepo:askrepo /opt/models
COPY --chown=askrepo:askrepo app ./app
USER askrepo
EXPOSE 7860
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "7860", "--workers", "1", "--no-proxy-headers"]
