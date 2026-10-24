'''Run media jobs without the web server: `python -m apps.worker` (uses the same SITE_* settings).'''
from __future__ import annotations

import asyncio
import logging
import signal

import pymongo

from apps.api.composition import build_services
from apps.api.settings import ServerConfig, Settings

logger = logging.getLogger("apps.worker")


async def run() -> None:
    config = ServerConfig.from_settings(Settings())  # type: ignore[call-arg]
    client: pymongo.AsyncMongoClient = pymongo.AsyncMongoClient(config.mongodb_url)
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    try:
        services = await build_services(config, client[config.database_name])
        logger.info("Worker %s processing jobs for %s", services.worker.worker_id, config.root_path)
        await services.worker.run(stop)
    finally:
        await client.aclose()


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    asyncio.run(run())


if __name__ == "__main__":
    main()
