"""
folders.py - Maps Spore asset subtypes to filesystem folder structures.

Depends on: models (Asset)
Used by: cli/commands/_common, crawlers/full_crawler
"""
from pathlib import Path
from spore_crawler.models import Asset


# Subtype hex -> folder mapping from research
SUBTYPE_FOLDERS = {
    # Creatures
    "0x9ea3031a": "Creatures/Animal",
    "0x372e2c04": "Creatures/Tribal",
    "0xccc35c46": "Creatures/Civ",
    "0x65672ade": "Creatures/Space",
    "0x4178b8e8": "Creatures/Captain",
    # Buildings
    "0x99e92f05": "Buildings/City Hall",
    "0x4e3f7777": "Buildings/House",
    "0x47c10953": "Buildings/Factory",
    "0x72c49181": "Buildings/Entertainment",
    # Vehicles
    "0x7d433fad": "Vehicles/Military Land",
    "0x8f963dcb": "Vehicles/Military Water",
    "0x441cd3e6": "Vehicles/Military Air",
    "0xf670aa43": "Vehicles/Economic Land",
    "0x2a5147a9": "Vehicles/Economic Water",
    "0x1a4e0708": "Vehicles/Economic Air",
    "0x9ad7d4aa": "Vehicles/Religious Land",
    "0x1f2a25b6": "Vehicles/Religious Water",
    "0x449c040f": "Vehicles/Religious Air",
    "0xbc1041e6": "Vehicles/Colony Land",
    "0xc15695da": "Vehicles/Colony Water",
    "0x2090a11b": "Vehicles/Colony Air",
    "0x98e03c0d": "Vehicles/Spaceships",
    # Adventures
    "0x287adcdc": "Adventures/Attack",
    "0x25a6ea6e": "Adventures/Collect",
    "0xc34c5e14": "Adventures/Defend",
    "0x37fd4e0d": "Adventures/Explore",
    "0xe27ddad4": "Adventures/Puzzle",
    "0xc422519e": "Adventures/Quest",
    "0xfb734cd1": "Adventures/Socialize",
    "0xb4707f8f": "Adventures/Story",
    "0x27818fe6": "Adventures/Template",
    "0x20790816": "Adventures/No Genre",
}

# Fallback by type when subtype is unknown
TYPE_FOLDERS = {
    "CREATURE": "Creatures/Other",
    "BUILDING": "Buildings/Other",
    "VEHICLE": "Vehicles/Other",
    "ADVENTURE": "Adventures/Other",
    "UFO": "Vehicles/Spaceships",
}


def get_asset_folder(asset: Asset) -> str:
    """Get the subfolder path for an asset based on its subtype"""
    subtype = asset.subtype.lower().strip()
    if subtype in SUBTYPE_FOLDERS:
        return SUBTYPE_FOLDERS[subtype]
    return TYPE_FOLDERS.get(asset.type.value, "Other")


def get_asset_path(asset: Asset, base_dir: Path) -> Path:
    """Get full file path for an asset"""
    folder = get_asset_folder(asset)
    return base_dir / folder / f"{asset.id}.png"


def get_sporecast_path(sporecast_title: str, base_dir: Path, author: str = "", sporecast_id: int = 0) -> Path:
    """Get folder path for a sporecast.

    Uses 'username_sanitized-title' format when author is provided,
    otherwise falls back to sanitized title.
    """
    safe_title = "".join(c if c.isalnum() or c in " -_" else "_" for c in sporecast_title)
    safe_title = safe_title.strip().replace(" ", "_").rstrip("_")
    if author:
        safe_author = "".join(c if c.isalnum() or c in " -_" else "_" for c in author)
        safe_author = safe_author.strip().replace(" ", "_").rstrip("_")
        return base_dir / "Sporecasts" / f"{safe_author}_{safe_title}"
    return base_dir / "Sporecasts" / safe_title


def ensure_directories(base_dir: Path):
    """Create all category folders"""
    folders = set(SUBTYPE_FOLDERS.values()) | set(TYPE_FOLDERS.values())
    folders.add("Sporecasts")
    for folder in folders:
        (base_dir / folder).mkdir(parents=True, exist_ok=True)
