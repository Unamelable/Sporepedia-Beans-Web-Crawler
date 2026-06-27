"""
models.py - Core data models (Asset, Sporecast, CrawlProgress).

Depends on: None (leaf module)
Used by: api/client, crawlers/full_crawler, organizers/folders, cli/commands/sporecast
"""
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
from enum import Enum


class AssetType(str, Enum):
    CREATURE = "CREATURE"
    BUILDING = "BUILDING"
    VEHICLE = "VEHICLE"
    ADVENTURE = "ADVENTURE"
    UFO = "UFO"


class ViewType(str, Enum):
    NEWEST = "NEWEST"
    TOP_RATED = "TOP_RATED"
    TOP_RATED_NEW = "TOP_RATED_NEW"
    FEATURED = "FEATURED"
    MAXIS_MADE = "MAXIS_MADE"
    RANDOM = "RANDOM"
    CUTE_AND_CREEPY = "CUTE_AND_CREEPY"


@dataclass
class Asset:
    id: int
    name: str
    type: AssetType
    author: str
    subtype: str = ""
    description: str = ""
    tags: str = ""
    rating: str = "-1"
    parent_id: Optional[int] = None
    created: str = ""
    thumb_url: str = ""
    image_url: str = ""

    @classmethod
    def from_api(cls, data: dict) -> "Asset":
        return cls(
            id=int(data.get("id", 0)),
            name=data.get("name", "Unknown"),
            type=AssetType(data.get("type", "CREATURE")),
            author=data.get("author", "Unknown"),
            subtype=data.get("subtype", ""),
            description=data.get("description", ""),
            tags=data.get("tags", "NULL"),
            rating=data.get("rating", "-1"),
            parent_id=int(data["parent"]) if data.get("parent") and data["parent"] != "NULL" else None,
            created=data.get("created", ""),
            thumb_url=data.get("thumb", ""),
            image_url=data.get("image", ""),
        )


@dataclass
class Sporecast:
    id: int
    title: str
    author: str
    subtitle: str = ""
    rating: str = "0"
    asset_count: int = 0
    tags: str = ""
    updated: str = ""

    @classmethod
    def from_api(cls, data: dict) -> "Sporecast":
        return cls(
            id=int(data.get("id", 0)),
            title=data.get("title", "Untitled"),
            author=data.get("author", "Unknown"),
            subtitle=data.get("subtitle", ""),
            rating=data.get("rating", "0"),
            asset_count=int(data.get("assetsCount", 0)),
            tags=data.get("tags", ""),
            updated=data.get("updateAt", ""),
        )


@dataclass
class CrawlProgress:
    crawl_id: str
    last_start_index: int = 0
    total_processed: int = 0
    status: str = "pending"
    last_updated: str = ""
