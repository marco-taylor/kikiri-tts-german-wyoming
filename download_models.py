#!/usr/bin/env python3

import os
import shutil
import sys
from pathlib import Path

from huggingface_hub import hf_hub_download


MODELS_DIR = Path("/app/models")


# ---------------------------------------------------------
# Eingebaute Stimmen
# ---------------------------------------------------------

KNOWN_VOICES = {
    "martin": {
        "repo": "kikiri-tts/kikiri-german-martin",
        "model": "kikiri_german_martin_ep10.pth",
        "voice": "voices/martin.pt",
    },
    "victoria": {
        "repo": "kikiri-tts/kikiri-german-victoria",
        "model": "kikiri_german_victoria_ep10.pth",
        "voice": "voices/victoria.pt",
    },
}


def parse_extra_voices():
    """
    Format:
    name|repo|model|voice;name2|repo2|model2|voice2

    Beispiel:
    anna|user/repository|anna.pth|voices/anna.pt
    """

    result = {}

    value = os.getenv("KOKORO_EXTRA_VOICES", "").strip()

    if not value:
        return result

    for entry in value.split(";"):
        entry = entry.strip()

        if not entry:
            continue

        parts = [part.strip() for part in entry.split("|")]

        if len(parts) != 4:
            raise ValueError(
                "Ungültiger Eintrag in KOKORO_EXTRA_VOICES: "
                f"{entry!r}. Erwartet: name|repo|model|voice"
            )

        name, repo, model, voice = parts

        if not all((name, repo, model, voice)):
            raise ValueError(
                f"Unvollständiger Eintrag in KOKORO_EXTRA_VOICES: {entry!r}"
            )

        name = name.lower()

        result[name] = {
            "repo": repo,
            "model": model,
            "voice": voice,
        }

    return result


def selected_voices():
    value = os.getenv("KOKORO_VOICES", "martin,victoria")

    result = []

    for item in value.split(","):
        name = item.strip().lower()

        if name and name not in result:
            result.append(name)

    return result


def download_if_missing(repo, remote_file, local_file):
    local_file = Path(local_file)

    # -----------------------------------------------------
    # Existiert die Datei bereits?
    # Dann NICHT herunterladen und NICHT überschreiben.
    # -----------------------------------------------------

    if local_file.is_file() and local_file.stat().st_size > 0:
        print(
            f"Vorhanden: {local_file} "
            f"({local_file.stat().st_size / 1024 / 1024:.1f} MB)",
            flush=True,
        )
        return

    local_file.parent.mkdir(parents=True, exist_ok=True)

    print(f"Fehlt     : {local_file}", flush=True)
    print(f"Lade      : {repo}/{remote_file}", flush=True)

    temp_file = local_file.with_suffix(
        local_file.suffix + ".part"
    )

    try:
        cached_file = hf_hub_download(
            repo_id=repo,
            filename=remote_file,
        )

        shutil.copyfile(cached_file, temp_file)

        if not temp_file.is_file():
            raise RuntimeError(
                f"Temporäre Datei fehlt: {temp_file}"
            )

        if temp_file.stat().st_size == 0:
            raise RuntimeError(
                f"Heruntergeladene Datei ist leer: {remote_file}"
            )

        temp_file.replace(local_file)

        print(
            f"Gespeichert : {local_file} "
            f"({local_file.stat().st_size / 1024 / 1024:.1f} MB)",
            flush=True,
        )

    except Exception:
        temp_file.unlink(missing_ok=True)
        raise


def main():
    print("=" * 60)
    print("Kikiri German – Modellverwaltung")
    print("=" * 60)

    try:
        voices = dict(KNOWN_VOICES)

        extra = parse_extra_voices()

        # Extra-Einträge dürfen auch eine vorhandene Definition
        # bewusst überschreiben.
        voices.update(extra)

        selected = selected_voices()

        print(
            "Aktivierte Stimmen :",
            ", ".join(selected) if selected else "(keine)",
        )

        print(
            "Bekannte Stimmen   :",
            ", ".join(voices),
        )

        if extra:
            print(
                "Zusätzliche Stimmen:",
                ", ".join(extra),
            )

        if not selected:
            raise RuntimeError(
                "KOKORO_VOICES enthält keine Stimmen."
            )

        unknown = [
            name for name in selected
            if name not in voices
        ]

        if unknown:
            raise RuntimeError(
                "Keine Download-Konfiguration für: "
                + ", ".join(unknown)
                + ". Über KOKORO_EXTRA_VOICES hinzufügen."
            )

        for name in selected:
            data = voices[name]

            print()
            print("-" * 60)
            print(f"Stimme     : {name}")
            print(f"Repository : {data['repo']}")
            print("-" * 60)

            voice_dir = MODELS_DIR / name

            download_if_missing(
                data["repo"],
                data["model"],
                voice_dir / "model.pth",
            )

            download_if_missing(
                data["repo"],
                data["voice"],
                voice_dir / "voice.pt",
            )

    except Exception as exc:
        print()
        print(
            f"FEHLER bei der Modellverwaltung: {exc}",
            file=sys.stderr,
        )
        sys.exit(1)

    print()
    print("=" * 60)
    print("Alle aktivierten Modelle sind vorhanden.")
    print("=" * 60)


if __name__ == "__main__":
    main()
