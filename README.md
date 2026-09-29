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

## Zusätzliche / Custom Stimmen

Neben den bereits integrierten Stimmen **Martin** und **Victoria** können weitere kompatible Kikiri-/Kokoro-Stimmen über `KOKORO_EXTRA_VOICES` eingebunden werden.

Eine zusätzliche Stimme wird in folgendem Format angegeben:

```text
name|huggingface-repository|model-datei|voice-datei
```

Mehrere zusätzliche Stimmen können durch ein Semikolon (`;`) getrennt werden.

### Beispiel: Bernd

Die deutsche Kikiri-Stimme **Bernd** kann ohne Änderung des Docker-Images hinzugefügt werden.

**Zusätzliche Stimmen (`KOKORO_EXTRA_VOICES`):**

```text
bernd|kikiri-tts/kikiri-german-bernd|kokoro_german_bernd.pth|bernd.pt
```

Damit Bernd zusätzlich zu Martin und Victoria installiert wird:

**Installierte Stimmen (`KOKORO_VOICES`):**

```text
martin,victoria,bernd
```

Optional können alle drei Stimmen beim Start des Containers vorgeladen werden:

**Vorgeladene Stimmen (`KOKORO_PRELOAD`):**

```text
martin,victoria,bernd
```

Beim nächsten Start lädt der Container Modell und Voicepack von Bernd automatisch von Hugging Face herunter. Anschließend stehen **Martin, Victoria und Bernd** über die TTS-/Wyoming-Schnittstelle zur Verfügung.

Die Modelle und Voicepacks werden getrennt abgelegt:

```text
models/
├── martin/
│   ├── model.pth
│   └── voice.pt
├── victoria/
│   ├── model.pth
│   └── voice.pt
└── bernd/
    ├── model.pth
    └── voice.pt
```

Dadurch können auch Stage-2-feingetunte Stimmen mit einem eigenen Modell und Voicepack verwendet werden.

> **Hinweis:** Eine Custom Voice muss mit der verwendeten Kikiri-/Kokoro-Architektur kompatibel sein. Bei einer auf einem eigenen Modell feinabgestimmten Stimme reicht das Voicepack allein nicht aus.

Bernd auf Hugging Face:
https://huggingface.co/kikiri-tts/kikiri-german-bernd

### Beispiel: Thorsten

Die hochdeutsche Stimme **Thorsten** kann ebenfalls als Custom Voice
eingebunden werden.

**Zusätzliche Stimmen (`KOKORO_EXTRA_VOICES`):**

```text
thorsten|Thorsten-Voice/Kokoro|model.pth|voices/thorsten.pt
```

Werden Bernd und Thorsten gemeinsam verwendet:

```text
bernd|kikiri-tts/kikiri-german-bernd|kokoro_german_bernd.pth|bernd.pt;thorsten|Thorsten-Voice/Kokoro|model.pth|voices/thorsten.pt
```

**Installierte Stimmen (`KOKORO_VOICES`):**

```text
martin,victoria,bernd,thorsten
```

**Vorgeladene Stimmen (`KOKORO_PRELOAD`):**

```text
martin,victoria,bernd,thorsten
```

Beim Containerstart werden Modell und Voicepack automatisch
heruntergeladen und über die TTS-/Wyoming-Schnittstelle bereitgestellt.

Thorsten auf Hugging Face:
https://huggingface.co/Thorsten-Voice/Kokoro

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

## Credits & Upstream-Projekte

Kikiri TTS German + Wyoming ist ein unabhängiges Community-Projekt und baut auf mehreren Open-Source-Projekten auf.

Besonderer Dank gilt:

- **Kikiri TTS** – deutsche TTS-Implementierung und Grundlage dieses Projekts  
  https://github.com/semidark/kikiri-tts

- **Kokoro** – zugrunde liegende Text-to-Speech-Technologie  
  https://github.com/hexgrad/kokoro

- **Misaki** – Grapheme-to-Phoneme-Verarbeitung (G2P)  
  https://github.com/hexgrad/misaki

- **Wyoming Protocol** – Protokoll für die Integration von Sprachdiensten, unter anderem mit Home Assistant  
  https://github.com/rhasspy/wyoming

Die jeweiligen Komponenten, Modelle und Sprachressourcen unterliegen den
Lizenz- und Copyright-Bedingungen ihrer jeweiligen Upstream-Projekte.

Kikiri TTS German + Wyoming ist ein unabhängiges Community-Projekt und
ist nicht mit Kikiri, Kokoro, Home Assistant oder Unraid verbunden oder
von diesen offiziell unterstützt.
