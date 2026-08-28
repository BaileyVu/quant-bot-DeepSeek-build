"""Application entry point."""

import sys
from quantos.logging import setup_logging
from quantos.config import get_config

def main():
    # Load config (validates)
    config = get_config()
    # Setup logging
    logger = setup_logging()
    logger.info("QuantOS starting")
    logger.info(f"Loaded config: symbols={config.symbols}, interval={config.interval}")
    logger.info("QuantOS started successfully")
    return 0

if __name__ == "__main__":
    sys.exit(main())