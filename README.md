# Kikiri TTS German + Wyoming

![Kikiri TTS](icons/kikiri-tts.png)

Lokaler deutscher Text-to-Speech-Server auf Basis von Kikiri/Kokoro mit Wyoming-Unterstützung für Home Assistant. Das Projekt ist auf hochwertige deutsche Sprachausgabe und lokalen CPU-Betrieb ausgelegt und wurde unter anderem auf einem Intel N100 getestet.

## Funktionen

- Deutsche neuronale TTS-Ausgabe
- Wyoming-Anbindung für Home Assistant
- OpenAI-kompatible TTS-API
- Standardstimmen `martin` und `victoria`
- Unterstützung zusätzlicher kompatibler Stimmen
- Automatischer Download fehlender Modelle
- Modelle dauerhaft außerhalb des Docker-Images speicherbar
- CPU-Betrieb ohne dedizierte GPU
- Deutsche Textnormalisierung
- Stabiler Non-Streaming-Betrieb
- Adaptive Audioausgabe für geringere wahrgenommene Latenz
- Optional konfigurierbare Synthesebeschleunigung mit tonhöhenneutraler Rückdehnung
- Konservativer Fallback, wenn eine kontinuierliche adaptive Ausgabe nicht sicher möglich ist

## Home Assistant / Wyoming

Für Home Assistant wird der Container über die Wyoming-Integration eingebunden:

```text
Host: IP-Adresse des Unraid-/Docker-Servers
Port: 10203
```

Home Assistant erkennt anschließend die vom Server angebotenen deutschen TTS-Stimmen.

Der Wyoming-Dienst soll sich als **Kikiri TTS German + Wyoming** identifizieren und nicht als generischer OpenAI-TTS-Dienst. Falls nach einem Update noch eine alte Bezeichnung angezeigt wird, die bestehende Wyoming-Integration in Home Assistant neu laden bzw. bei Bedarf neu hinzufügen.

## Ports

| Port | Funktion |
| --- | --- |
| `10203/tcp` | Wyoming TTS für Home Assistant |
| `8881/tcp` | interner OpenAI-kompatibler TTS-Server |

Normalerweise muss nur Port `10203` veröffentlicht werden.

## Stimmen und Modelle

Die Sprachmodelle sind absichtlich nicht Bestandteil des Git-Repositories oder Docker-Images. Beim Start werden konfigurierte fehlende Modelle heruntergeladen und unter `/app/models` gespeichert.

Standardmäßig stehen zur Verfügung:

- `martin`
- `victoria`

Für dauerhafte Speicherung sollte `/app/models` als Volume eingebunden werden, beispielsweise unter Unraid:

```text
/mnt/user/appdata/kikiri-tts-german-wyoming/models -> /app/models
```

### Zusätzliche Stimmen

Weitere kompatible Kikiri-/Kokoro-Stimmen können über `KOKORO_EXTRA_VOICES` ergänzt werden:

```text
name|huggingface-repository|model-datei|voice-datei
```

Mehrere Definitionen werden mit `;` getrennt.

Beispiel Bernd:

```text
bernd|kikiri-tts/kikiri-german-bernd|kokoro_german_bernd.pth|bernd.pt
```

Beispiel Thorsten:

```text
thorsten|Thorsten-Voice/Kokoro|model.pth|voices/thorsten.pt
```

Danach die gewünschten Stimmen beispielsweise konfigurieren als:

```text
KOKORO_VOICES=martin,victoria,bernd,thorsten
KOKORO_PRELOAD=martin,victoria,bernd,thorsten
```

Kompatible Stimmen können außerdem manuell als eigener Modellordner bereitgestellt werden:

```text
models/
└── meine_stimme/
    ├── model.pth
    └── voice.pt
```

Modell und Voicepack müssen zur verwendeten Kikiri-/Kokoro-Architektur kompatibel sein. Bei einer auf einem eigenen Modell feinabgestimmten Stimme reicht das Voicepack allein nicht aus.

## Adaptive Ausgabe und Synthese-Speed

Die optimierte Ausgabe kann Audio bereits wiedergeben, während nachfolgendes Audio weiter synthetisiert wird. Die Planung verwendet verfügbare Audiodaten und konservative Sicherheitsreserven; wenn eine kontinuierliche Ausgabe nicht sicher erscheint, muss auf den stabilen Fallback zurückgegriffen werden.

`KIKIRI_TTS_SYNTH_SPEED` steuert die optionale Synthesebeschleunigung.

| Wert | Bedeutung |
| --- | --- |
| `1.00` | Originalgeschwindigkeit und höchste Referenzqualität |
| `1.20` | auf Intel N100 erfolgreich als schnellerer Home-Assistant-Kompromiss getestet |
| `1.00–1.25` | vorgesehener Einstellbereich |

Dezimalwerte wie `1.175` sind zulässig. Bei Werten über `1.00` wird die schnellere Synthese anschließend tonhöhenneutral auf eine natürliche Wiedergabedauer zurückgedehnt. Der notwendige Stretch-Faktor wird aus den tatsächlichen Audiodauern bestimmt und nicht einfach aus dem eingestellten Speed abgeleitet.

`1.20` ist keine allgemeine Empfehlung für jede CPU und jede Stimme. Bei hörbaren Qualitätsunterschieden sollte ein niedrigerer Wert verwendet werden. `1.00` bleibt die Qualitätsreferenz.

## Umgebungsvariablen

Wichtige Einstellungen sind unter anderem:

```text
KOKORO_THREADS=4
KOKORO_PRELOAD=martin,victoria
KOKORO_VOICES=martin,victoria
KOKORO_EXTRA_VOICES=
WYOMING_TTS_CONCURRENT_REQUESTS=1
KIKIRI_TTS_SYNTH_SPEED=1.00
```

Je nach Release kann zusätzlich ein Betriebsmodus für Non-Streaming bzw. adaptive Ausgabe angeboten werden. Maßgeblich sind die im jeweiligen Unraid-Template bzw. Container definierten Variablen.

## Docker Build

```bash
docker build -t kikiri-tts-german-wyoming:latest .
```

## Docker Start

```bash
docker run -d \
  --name kikiri-tts-german-wyoming \
  --restart unless-stopped \
  -p 10203:10203 \
  -v /mnt/user/appdata/kikiri-tts-german-wyoming/models:/app/models \
  -e KOKORO_THREADS=4 \
  -e KOKORO_PRELOAD=martin,victoria \
  -e KOKORO_VOICES=martin,victoria \
  -e KIKIRI_TTS_SYNTH_SPEED=1.00 \
  ghcr.io/marco-taylor/kikiri-tts-german-wyoming:latest
```

Für Unraid empfiehlt sich die Installation über Community Applications, sobald die aktuelle Version veröffentlicht ist.

## Intel N100

Das Projekt wurde auf einem Intel N100 mit vier CPU-Kernen praktisch getestet. Für diesen Rechner ist `KOKORO_THREADS=4` ein sinnvoller Ausgangspunkt.

Die Qualitätsreferenz ist:

```text
KIKIRI_TTS_SYNTH_SPEED=1.00
```

Für geringere Latenz wurde außerdem erfolgreich mit Home Assistant getestet:

```text
KIKIRI_TTS_SYNTH_SPEED=1.20
```

Die tatsächliche Leistung hängt von Stimme, Textlänge und gleichzeitiger Systemlast ab.

## Projektpflege und Image-Größe

Modelle, Test-WAVs, Benchmarks, lokale virtuelle Umgebungen und temporäre Entwicklungsartefakte gehören nicht in das Produktionsimage oder Git-Repository. Vor Releases sollten `.gitignore`, `.dockerignore`, Docker-Layer und Runtime-Abhängigkeiten geprüft werden, damit nur für den Betrieb benötigte Daten ausgeliefert werden.

## Credits und Upstream-Projekte

Kikiri TTS German + Wyoming ist ein unabhängiges Community-Projekt und baut auf mehreren Open-Source-Komponenten auf:

- Kikiri TTS – deutsche TTS-Grundlage
- Kokoro – zugrunde liegende TTS-Technologie
- Misaki – Grapheme-to-Phoneme-Verarbeitung
- Wyoming Protocol – Integration von Sprachdiensten mit Home Assistant
- wyoming_openai – Wyoming-/OpenAI-kompatible TTS-Anbindung

Modelle und Abhängigkeiten können eigenen Lizenz- und Nutzungsbedingungen unterliegen. Diese sind bei der Verwendung zusätzlicher Stimmen oder Modelle separat zu beachten.

Kikiri TTS German + Wyoming ist ein unabhängiges Community-Projekt und nicht mit Kikiri, Kokoro, Home Assistant oder Unraid verbunden oder von diesen offiziell unterstützt.
