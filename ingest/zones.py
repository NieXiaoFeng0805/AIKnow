"""分区注册表：zones.toml -> Zone。

分区（zone）是一等数据维度（docs/design-v3 §1）：文档与 chunk 都带 zone_id，
检索必须显式指定分区，不允许默认全库。
"""

from __future__ import annotations

import tomllib
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

DEFAULT_ZONES_FILE = "zones.toml"


@dataclass(frozen=True)
class Zone:
    zone_id: str
    name: str
    purpose: str = ""
    sources: tuple[str, ...] = ()


def load_zones(path: str | Path = DEFAULT_ZONES_FILE) -> dict[str, Zone]:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"找不到分区注册表: {p}")
    data = tomllib.loads(p.read_text(encoding="utf-8"))
    table = data.get("zones")
    if not isinstance(table, dict) or not table:
        raise ValueError(f"{p} 缺少 zones 表，无法确定分区")
    zones: dict[str, Zone] = {}
    for zone_id, raw in table.items():
        if not isinstance(raw, dict):
            raise TypeError(f"{p} 里 zones.{zone_id} 不是表")
        sources = raw.get("sources", [])
        if isinstance(sources, str):
            sources = [sources]
        zones[zone_id] = Zone(
            zone_id=zone_id,
            name=str(raw.get("name", zone_id)),
            purpose=str(raw.get("purpose", "")),
            sources=tuple(str(s) for s in sources),
        )
    return zones


def require_zone(zones: Mapping[str, Zone], zone_id: str) -> Zone:
    if zone_id not in zones:
        known = ", ".join(sorted(zones)) or "空"
        raise ValueError(f"未知分区: {zone_id}；已定义: {known}")
    return zones[zone_id]


__all__ = ["DEFAULT_ZONES_FILE", "Zone", "load_zones", "require_zone"]
