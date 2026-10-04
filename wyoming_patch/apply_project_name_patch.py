"""Build-time, fail-closed patch for wyoming_openai Describe/Info metadata."""

import importlib.util
import ast
from pathlib import Path

path = Path(importlib.util.find_spec("wyoming_openai.compatibility").origin)
source = path.read_text()
lines = source.splitlines(keepends=True)
function = next(
    node
    for node in ast.parse(source).body
    if isinstance(node, ast.FunctionDef) and node.name == "create_tts_programs"
)
tts_source = "".join(lines[function.lineno - 1 : function.end_lineno])
name = "Kikiri TTS German + Wyoming"
description = "Local German TTS powered by Kikiri/Kokoro"
if name not in tts_source:
    for old, new in [
        ('name="openai-streaming"', f'name="{name}"'),
        ('name="openai"', f'name="{name}"'),
        ('description="OpenAI (Streaming)"', f'description="{description}"'),
        ('description="OpenAI (Non-Streaming)"', f'description="{description}"'),
    ]:
        if tts_source.count(old) != 1:
            raise RuntimeError(
                f"Unexpected wyoming_openai metadata patch anchor: {old}"
            )
        tts_source = tts_source.replace(old, new, 1)
    source = (
        "".join(lines[: function.lineno - 1])
        + tts_source
        + "".join(lines[function.end_lineno :])
    )
    ast.parse(source)
    path.write_text(source)
print("Patched wyoming_openai TTS Describe/Info name and description")
