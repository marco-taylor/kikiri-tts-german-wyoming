FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    KOKORO_THREADS=4 \
    KOKORO_PRELOAD=martin,victoria \
    KOKORO_VOICES=martin,victoria \
    KOKORO_EXTRA_VOICES="" \
    OMP_NUM_THREADS=4 \
    MKL_NUM_THREADS=4 \
    OPENBLAS_NUM_THREADS=4 \
    NUMEXPR_NUM_THREADS=4 \
    WYOMING_TTS_CONCURRENT_REQUESTS=1

WORKDIR /app

# ---------------------------------------------------------
# System-Abhängigkeiten + Python-Pakete
# ---------------------------------------------------------
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        espeak-ng \
        libsndfile1 \
        curl \
        git \
    \
    # PyTorch CPU-only
    && pip install --no-cache-dir \
        --index-url https://download.pytorch.org/whl/cpu \
        torch \
    \
    # Laufzeit-Abhängigkeiten
    && pip install --no-cache-dir \
        numpy \
        soundfile \
        fastapi \
        "uvicorn[standard]" \
        huggingface_hub \
        loguru \
        transformers \
        wyoming_openai \
    \
    # Kikiri German Misaki Fork - nur deutsche Abhängigkeiten
    && pip install --no-cache-dir \
        "misaki[de] @ git+https://github.com/semidark/misaki.git" \
    \
    # Build-Abhängigkeiten und Caches entfernen
    && apt-get purge -y --auto-remove git \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf /root/.cache/pip \
    && find /usr/local/lib/python3.12/site-packages \
        -type d -name "__pycache__" -prune -exec rm -rf '{}' +

# ---------------------------------------------------------
# Kikiri / Kokoro
# ---------------------------------------------------------
COPY kokoro /app/kokoro
COPY training /app/training
COPY server.py /app/server.py
COPY download_models.py /app/download_models.py

# ---------------------------------------------------------
# German Wyoming Separator
# ---------------------------------------------------------
COPY german_text_rules.py \
     /usr/local/lib/python3.12/site-packages/german_text_rules.py

COPY wyoming_patch/apply_german_separator_patch.py \
     /tmp/apply_german_separator_patch.py

RUN python /tmp/apply_german_separator_patch.py \
    && rm -f /tmp/apply_german_separator_patch.py

# ---------------------------------------------------------
# Start
# ---------------------------------------------------------
COPY start.sh /app/start.sh

RUN chmod +x /app/start.sh

EXPOSE 10203

CMD ["/app/start.sh"]
