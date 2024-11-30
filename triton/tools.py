"""Tools"""

import os
from pathlib import Path

KEY_PASSWORD = os.getenv("KEY_PASSWORD")


def escape_markdown_v2(text: str) -> str:
    """Markdown escape"""
    special_chars = r"*_[]()~`>#+-=|{}.!\\"
    return "".join(f"\\{char}" if char in special_chars else char for char in text)


def wei_to_unit(wei: int) -> float:
    """Converts wei to currency unit."""
    return wei / 10**18


def wei_to_olas(wei: int) -> str:
    """Converts and formats wei to WxDAI."""
    return f"{wei_to_unit(wei):.2f} OLAS"


def str_to_bool(value: str) -> bool:
    """Converts string to bool"""
    return str(value).lower() in ["true", "1", "yes"]


def load_env_to_dict(path: Path):
    """Load env vars into dict"""
    env_vars = {}
    with open(path, "r", encoding="utf-8") as file:
        for line in file:
            line = line.strip()
            if line and line.startswith("#"):
                continue
            key, value = line.split("=", 1)
            env_vars[key.strip()] = value.strip()
    return env_vars
