"""Manifest management for tracking data sources and metadata.

This module provides utilities to read and update the data manifest file,
which tracks all data sources, their coverage, and acquisition metadata.
"""
import json
from datetime import datetime
from pathlib import Path
from typing import Any

def get_manifest_path() -> Path:
    """Get the path to the manifest.json file.

    :return: Absolute path to manifest.json
    """
    return Path(__file__).parent.parent.parent / "data" / "manifest.json"

def read_manifest() -> dict[str, Any]:
    """Read the current manifest file.

    :return: Manifest data as dictionary
    """
    manifest_path = get_manifest_path()
    if not manifest_path.exists():
        raise FileNotFoundError(f"Manifest not found: {manifest_path}")
    with open(manifest_path, 'r', encoding='utf-8') as f:
        return json.load(f)

def write_manifest(manifest: dict[str, Any]) -> None:
    """Write updated manifest back to file.

    :param manifest: Complete manifest dictionary to write
    """
    manifest_path = get_manifest_path()
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest["metadata"]["last_updated"] = datetime.now().strftime("%Y-%m-%d")
    with open(manifest_path, 'w', encoding='utf-8') as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)

def update_dataset(dataset_name: str, updates: dict[str, Any]) -> None:
    """Update a specific dataset's metadata in the manifest.

    :param dataset_name: Key name of the dataset in manifest
    :param updates: Dictionary of fields to update
    """
    manifest = read_manifest()
    if dataset_name not in manifest["datasets"]:
        raise KeyError(f"Dataset '{dataset_name}' not found in manifest")
    for key, value in updates.items():
        if isinstance(value, dict) and key in manifest["datasets"][dataset_name]:
            manifest["datasets"][dataset_name][key].update(value)
        else:
            manifest["datasets"][dataset_name][key] = value
    write_manifest(manifest)

def mark_verified(dataset_name: str, coverage_info: dict[str, Any] | None = None) -> None:
    """Mark a dataset's coverage as verified.

    :param dataset_name: Key name of the dataset in manifest
    :param coverage_info: Optional additional coverage information to update
    """
    updates = {"coverage": {"verified": True}}
    if coverage_info:
        updates["coverage"].update(coverage_info)
    update_dataset(dataset_name, updates)

def update_gm_data(num_files: int, last_updated: str | None = None) -> None:
    """Update GM executives dataset metadata after scraping.

    :param num_files: Number of CSV files successfully downloaded
    :param last_updated: Date string (YYYY-MM-DD), defaults to today
    """
    if last_updated is None:
        last_updated = datetime.now().strftime("%Y-%m-%d")
    update_dataset("gm_executives", {
        "last_updated": last_updated,
        "files": num_files
    })

def get_dataset_info(dataset_name: str) -> dict[str, Any]:
    """Get metadata for a specific dataset.

    :param dataset_name: Key name of the dataset in manifest
    :return: Dataset metadata dictionary
    """
    manifest = read_manifest()
    if dataset_name not in manifest["datasets"]:
        raise KeyError(f"Dataset '{dataset_name}' not found in manifest")
    return manifest["datasets"][dataset_name]

def list_datasets() -> list[str]:
    """Get list of all datasets tracked in manifest.

    :return: List of dataset names
    """
    manifest = read_manifest()
    return list(manifest["datasets"].keys())

def get_unverified_datasets() -> list[str]:
    """Get list of datasets that haven't had coverage verified.

    :return: List of dataset names with verified=False
    """
    manifest = read_manifest()
    unverified = []
    for name, data in manifest["datasets"].items():
        if "coverage" in data and not data["coverage"].get("verified", False):
            unverified.append(name)
    return unverified
