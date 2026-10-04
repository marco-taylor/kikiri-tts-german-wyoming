FROM python:3.12-slim-bookworm AS soundtouch-build
RUN apt-get update \
    && apt-get install -y --no-install-recommends g++ libsoundtouch-dev \
    && rm -rf /var/lib/apt/lists/*
COPY tts_runtime/soundtouch_shim.cpp /build/soundtouch_shim.cpp
RUN g++ -O2 -shared -fPIC /build/soundtouch_shim.cpp -lSoundTouch \
    -o /build/libkikiri_soundtouch.so

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
    WYOMING_TTS_CONCURRENT_REQUESTS=1 \
    KIKIRI_TTS_SYNTH_SPEED=1.00 \
    KIKIRI_TTS_MODE=adaptive
WORKDIR /app
COPY requirements.txt /tmp/requirements.txt
RUN apt-get update \
    && apt-get install -y --no-install-recommends espeak-ng libsndfile1 libsoundtouch1 curl git \
    && pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cpu torch==2.14.0 \
    && pip install --no-cache-dir -r /tmp/requirements.txt \
    && apt-get purge -y --auto-remove git \
    && rm -rf /var/lib/apt/lists/* /root/.cache/pip /tmp/requirements.txt \
    && find /usr/local/lib/python3.12/site-packages -type d -name __pycache__ -prune -exec rm -rf '{}' +
COPY --from=soundtouch-build /build/libkikiri_soundtouch.so /usr/local/lib/libkikiri_soundtouch.so
COPY kokoro /app/kokoro
COPY training /app/training
COPY server.py download_models.py start.sh /app/
COPY tts_runtime/*.py /app/tts_runtime/
COPY LICENSE NOTICE /app/
COPY german_text_rules.py /usr/local/lib/python3.12/site-packages/german_text_rules.py
COPY wyoming_patch /tmp/wyoming_patch
RUN python /tmp/wyoming_patch/apply_german_separator_patch.py \
    && python /tmp/wyoming_patch/apply_project_name_patch.py \
    && rm -rf /tmp/wyoming_patch \
    && chmod +x /app/start.sh
EXPOSE 10203
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s \
    CMD curl -fsS http://127.0.0.1:8881/health || exit 1
CMD ["/app/start.sh"]
