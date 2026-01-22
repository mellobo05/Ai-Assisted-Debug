from __future__ import annotations

import re
from typing import Iterable

from pydantic import BaseModel, ConfigDict, field_validator


JIRA_ISSUE_KEY_RE = re.compile(r"^[A-Z][A-Z0-9]+-\d+$")


class APIModel(BaseModel):
    """
    Common base for API schemas:
    - forbid unknown keys (prevents silent typos in payloads)
    - keep things predictable across endpoints
    """

    model_config = ConfigDict(extra="forbid")


def _strip_or_none(v: object) -> object:
    if v is None:
        return None
    if isinstance(v, str):
        s = v.strip()
        return s
    return v


def _uniq_preserve_order(items: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for x in items:
        if x in seen:
            continue
        seen.add(x)
        out.append(x)
    return out

