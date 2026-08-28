"""Safety barrier to ensure paper mode never submits real orders."""

from loguru import logger


class SafetyBarrier:
    """Prevent any real order submission in paper mode."""

    def __init__(self):
        self.mode = "paper"

    def check(self, order_type: str, symbol: str, side: str, quantity: float) -> None:
        """
        Raises an exception if any real order is attempted in paper mode.
        """
        logger.error(f"Paper mode: attempted real order {order_type} {symbol} {side} {quantity}")
        raise RuntimeError("Paper mode forbids real order submission")

    def ensure_paper(self):
        """Return True if in paper mode, else raise."""
        if self.mode != "paper":
            raise RuntimeError("SafetyBarrier: mode is not paper")
        return True