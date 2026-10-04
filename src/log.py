"""Levelled terminal log. INFO shows the flow and the problems; DEBUG adds patient data and model answers."""

import logging
import os

LOG_LEVEL = "INFO"  # Default level; the VITA_LOG_LEVEL environment variable overrides it (e.g. DEBUG).


class _SafeStreamHandler(logging.StreamHandler):
    """Writes to the terminal without failing on characters its encoding cannot show."""

    def emit(self, record):
        """Writes one record, replacing the characters the terminal cannot encode."""
        try:
            line = self.format(record) + self.terminator
            try:
                self.stream.write(line)
            except UnicodeEncodeError:
                encoding = getattr(self.stream, "encoding", None) or "ascii"
                self.stream.write(line.encode(encoding, "backslashreplace").decode(encoding))
            self.flush()
        except Exception:
            self.handleError(record)


def _configure() -> logging.Logger:
    """The root logger of the project, set up once with its own handler and level."""
    root = logging.getLogger("vita")
    if not root.handlers:
        handler = _SafeStreamHandler()
        handler.setFormatter(logging.Formatter("%(levelname)-7s %(name)s | %(message)s"))
        root.addHandler(handler)
        # Chainlit configures the global logger with its own format: keep ours separate.
        root.propagate = False
    level = os.environ.get("VITA_LOG_LEVEL", LOG_LEVEL).upper()
    root.setLevel(getattr(logging, level, logging.INFO))
    return root


def get_logger(name: str) -> logging.Logger:
    """The logger of one part of the project, e.g. get_logger("router") -> "vita.router"."""
    _configure()
    return logging.getLogger(f"vita.{name}")
