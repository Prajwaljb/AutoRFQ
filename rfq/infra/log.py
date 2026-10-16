"""Logging to run.log in the output folder, plus one console line per warning.

Never log secrets or email bodies: only IDs, counts and error types.
"""
import logging
import sys


def setup(run_dir, name="rfq"):
    logger = logging.getLogger(f"{name}.{run_dir.name}")
    logger.setLevel(logging.INFO)
    logger.propagate = False
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    run_dir.mkdir(parents=True, exist_ok=True)
    file_handler = logging.FileHandler(run_dir / "run.log", mode="w", encoding="utf-8")
    file_handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    logger.addHandler(file_handler)
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.WARNING)
    console.setFormatter(logging.Formatter("warning: %(message)s"))
    logger.addHandler(console)
    return logger


def close(logger):
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
