"""
ReaSig Daemon - Entry Point

Usage: python -m daemon

Starts the ReaSig daemon TCP server. This process runs independently
from REAPER and handles all heavy lifting: DSP analysis, LLM API calls,
and streaming responses back to the ReaScript client.
"""

import asyncio
import logging
import signal
import sys

from .config import load_config
from .server import ReaSigServer


def setup_logging() -> None:
    """Configure logging for the daemon."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        datefmt="%H:%M:%S",
    )


def print_banner(host: str, port: int, model: str) -> None:
    """Print the startup banner."""
    print()
    print("╔══════════════════════════════════════════════════╗")
    print("║           ReaSig Daemon v0.1.0                  ║")
    print("║     AI Mix & Production Assistant               ║")
    print("╠══════════════════════════════════════════════════╣")
    print(f"║  Listening on: {host}:{port}                   ║")
    print(f"║  Model: {model:<40s} ║")
    print("║  Press Ctrl+C to stop                           ║")
    print("╚══════════════════════════════════════════════════╝")
    print()


async def main() -> None:
    """Main async entry point."""
    setup_logging()
    logger = logging.getLogger("reasig")

    # Load configuration
    config = load_config()
    errors = config.validate()
    if errors:
        for err in errors:
            logger.error("Config error: %s", err)
        sys.exit(1)

    # Create server
    server = ReaSigServer(config)
    
    # Register DSP handlers
    from .dsp.analyzer import analyze_audio_file
    from .dsp.masking import analyze_masking
    server.analyze_handler = analyze_audio_file
    server.masking_handler = analyze_masking

    # Register LLM handler
    from .llm import make_llm_handler
    if config.openrouter_api_key and config.openrouter_api_key != "sk-or-v1-your-key-here":
        server.llm_handler = make_llm_handler(config)
        logger.info("LLM handler registered (model: %s)", config.model)
    else:
        logger.warning(
            "OPENROUTER_API_KEY not set — LLM responses disabled. "
            "Raw DSP analysis will be returned instead. "
            "Add your key to .env to enable AI responses."
        )

    # Register signal handlers for graceful shutdown
    loop = asyncio.get_running_loop()

    def handle_shutdown():
        logger.info("Received shutdown signal")
        asyncio.create_task(server.shutdown())

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, handle_shutdown)

    # Start the server
    print_banner(config.host, config.port, config.model)
    logger.info("Daemon starting with model: %s", config.model)
    logger.info("Temp directory: %s", config.temp_dir)

    try:
        await server.serve_forever()
    except asyncio.CancelledError:
        pass
    finally:
        await server.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
