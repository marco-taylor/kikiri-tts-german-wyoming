#!/bin/bash
set -e
echo "Kikiri TTS German + Wyoming"
echo "KOKORO_THREADS=${KOKORO_THREADS:-4} KIKIRI_TTS_SYNTH_SPEED=${KIKIRI_TTS_SYNTH_SPEED:-1.00}"
python -m tts_runtime.config
python /app/download_models.py
exec python -m tts_runtime
