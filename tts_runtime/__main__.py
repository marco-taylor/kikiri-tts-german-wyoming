import asyncio
import os
import sys
from .config import Config

try:
    config = Config.from_env()
except ValueError as exc:
    print(str(exc), file=sys.stderr)
    raise SystemExit(2)

from . import service
from .server import Server
import server as http_backend
import uvicorn


async def main():
    policies = service.initialize(config)
    diagnostics = os.getenv("KIKIRI_TTS_DIAGNOSTICS_DIR")
    if diagnostics:
        os.makedirs(diagnostics, exist_ok=True)
    bridge = Server(policies, diagnostics)
    listener = await bridge.listen(
        port=int(os.getenv("WYOMING_PORT", "10203")), host="0.0.0.0"
    )
    http = uvicorn.Server(
        uvicorn.Config(
            http_backend.app,
            host="0.0.0.0",
            port=int(os.getenv("PORT", "8881")),
            workers=1,
        )
    )
    print(
        f"Kikiri TTS German + Wyoming: mode={policies.mode} KIKIRI_TTS_SYNTH_SPEED={config.requested}",
        flush=True,
    )
    async with listener:
        await http.serve()
    # Uvicorn owns signal handling; close active Wyoming clients before shutdown.
    for session in bridge.sessions:
        session.cancelled.set()


if __name__ == "__main__":
    asyncio.run(main())
