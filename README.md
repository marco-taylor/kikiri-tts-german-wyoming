# Kikiri TTS German + Wyoming

![Kikiri TTS](icons/kikiri-tts.png)

Lokaler deutscher Text-to-Speech-Server auf Basis von Kikiri/Kokoro mit Wyoming-Unterstützung für Home Assistant.

## Funktionen

- Deutsche TTS-Ausgabe
- Wyoming-Protokoll für Home Assistant
- OpenAI-kompatible TTS-API
- Stimmen Martin und Victoria
- Automatischer Download fehlender Sprachmodelle
- Modelle werden außerhalb des Docker-Images gespeichert
- Zusätzliche Stimmen können über Variablen ergänzt werden
- Für CPU-Betrieb geeignet, unter anderem Intel N100
- Nicht-streamende Wyoming-TTS-Ausgabe

## Ports

| Port | Funktion |
| --- | --- |
| 10203 | Wyoming TTS |
| 8881 | Interner TTS-Server |

Für Home Assistant wird normalerweise nur Port 10203 benötigt.

## Modelle

Die Modelle sind absichtlich nicht Bestandteil dieses Git-Repositories.

Beim Start prüft download_models.py, ob die benötigten Modelle vorhanden sind. Fehlende Modelle werden automatisch von Hugging Face heruntergeladen.

Standardmäßig stehen folgende Stimmen zur Verfügung:

- martin
- victoria

Die Modelle befinden sich im Container unter /app/models.

Für eine dauerhafte Speicherung sollte /app/models als Volume eingebunden werden.

Unraid-Beispiel:

    /mnt/user/appdata/kikiri-tts-german-wyoming/models -> /app/models

## Umgebungsvariablen

Standardwerte:

    KOKORO_THREADS=4
    KOKORO_PRELOAD=martin,victoria
    KOKORO_VOICES=martin,victoria
    KOKORO_EXTRA_VOICES=
    WYOMING_TTS_CONCURRENT_REQUESTS=1

## Docker Build

    docker build -t kikiri-tts-german-wyoming:latest .

## Docker Start

    docker run -d \
      --name kikiri-tts-german-wyoming \
      --restart unless-stopped \
      -p 10203:10203 \
      -v /mnt/user/appdata/kikiri-tts-german-wyoming/models:/app/models \
      -e KOKORO_THREADS=4 \
      -e KOKORO_PRELOAD=martin,victoria \
      -e KOKORO_VOICES=martin,victoria \
      kikiri-tts-german-wyoming:latest

## Home Assistant

Den Container über die Wyoming-Integration hinzufügen.

    Host: IP-Adresse des Unraid-Servers
    Port: 10203

Anschließend sollten die verfügbaren TTS-Stimmen über Wyoming erkannt werden.

## Projektstruktur

    .
    ├── Dockerfile
    ├── README.md
    ├── download_models.py
    ├── german_text_rules.py
    ├── server.py
    ├── start.sh
    ├── icons/
    │   └── kikiri-tts.png
    ├── kokoro/
    ├── training/
    └── wyoming_patch/

## Hinweis

Dieses Projekt verwendet Komponenten aus Kikiri/Kokoro sowie weiteren Open-Source-Projekten. Die jeweiligen Lizenzen und Bedingungen der verwendeten Modelle und Abhängigkeiten sind zu beachten.
