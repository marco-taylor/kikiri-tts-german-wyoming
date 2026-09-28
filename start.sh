#!/bin/bash
set -e

echo "============================================================"
echo "Kikiri TTS German + Wyoming"
echo "============================================================"
echo "KOKORO_THREADS : ${KOKORO_THREADS:-4}"
echo "KOKORO_PRELOAD : ${KOKORO_PRELOAD:-martin,victoria}"
echo

# ---------------------------------------------------------
# Modelle prüfen
# ---------------------------------------------------------

echo "[1/4] Prüfe Modelle..."

python /app/download_models.py

echo
echo "[2/4] Starte Kikiri German TTS..."

python /app/server.py &
TTS_PID=$!

cleanup() {
    echo
    echo "Beende Kikiri TTS..."
    kill "$TTS_PID" 2>/dev/null || true
}

trap cleanup EXIT INT TERM

echo "[3/4] Warte auf TTS-Server..."

READY=0

for i in $(seq 1 60); do
    if ! kill -0 "$TTS_PID" 2>/dev/null; then
        echo "FEHLER: TTS-Server wurde unerwartet beendet."
        exit 1
    fi

    if curl -fsS http://127.0.0.1:8881/health >/dev/null 2>&1; then
        READY=1
        break
    fi

    sleep 1
done

if [ "$READY" != "1" ]; then
    echo "FEHLER: TTS-Server wurde nicht rechtzeitig bereit."
    exit 1
fi

echo "TTS-Server ist bereit."
echo
echo "Verfügbare Stimmen:"
curl -fsS http://127.0.0.1:8881/v1/audio/voices
echo
echo

echo "[4/4] Starte Wyoming auf Port 10203..."

exec python -m wyoming_openai \
    --uri tcp://0.0.0.0:10203 \
    --log-level INFO \
    --languages de \
    --tts-openai-url http://127.0.0.1:8881/v1 \
    --tts-models kokoro \
    --tts-backend KOKORO_FASTAPI
