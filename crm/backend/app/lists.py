"""Slug lists stored as ",a,b," strings on Contact.routes / Contact.tags."""

import re
from collections.abc import Iterable


def slug(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", str(value).strip().lower()).strip("-")


def pack(values: Iterable[str]) -> str:
    items: list[str] = []
    for v in values:
        s = slug(v)
        if s and s not in items:
            items.append(s)
    return "," + ",".join(items) + "," if items else ""


def unpack(packed: str) -> list[str]:
    return [p for p in (packed or "").split(",") if p]


def merge(packed: str, values: Iterable[str]) -> str:
    return pack([*unpack(packed), *values])
