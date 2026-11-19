"""Migrate existing linked chargers to native subentries with HA stopped."""

import json
import sys
from pathlib import Path
from shutil import copy2


def migrate(storage, backup):
    paths = [storage / name for name in (
        "core.config_entries", "core.device_registry", "core.entity_registry"
    )]
    configs, devices, entities = [json.loads(path.read_text()) for path in paths]
    entries = configs["data"]["entries"]
    accounts = {
        entry["entry_id"]: entry for entry in entries
        if entry["domain"] == "sinotek_tuya" and entry["data"].get("kind") == "cloud"
    }
    existing = {child["unique_id"] for account in accounts.values() for child in account["subentries"]}
    moved = set()
    for entry in entries:
        data = entry["data"]
        account = accounts.get(data.get("cloud_entry_id"))
        if entry["domain"] != "sinotek_tuya" or entry["disabled_by"] or not account:
            continue
        old_id = entry["entry_id"]
        parent = account["entry_id"]
        device_id = data["device_id"]
        if device_id in existing:
            raise ValueError("A charger is already present as a cloud subentry")
        if entry["subentries"] or entry["options"]:
            raise ValueError("Unexpected standalone charger options")
        account["subentries"].append({
            "data": {key: value for key, value in data.items() if key != "cloud_entry_id"},
            "subentry_id": old_id, "subentry_type": "charger",
            "title": entry["title"], "unique_id": device_id,
        })
        existing.add(device_id)
        for device in devices["data"]["devices"]:
            if device["config_entry_id"] == old_id:
                device.update(config_entry_id=parent, config_subentry_id=old_id)
                if device.get("primary_config_entry") == old_id:
                    device["primary_config_entry"] = parent
        for entity in entities["data"]["entities"]:
            if entity["config_entry_id"] == old_id:
                entity.update(config_entry_id=parent, config_subentry_id=old_id)
        moved.add(old_id)
        print(f'{entry["title"]} → {account["title"]}')
    if not moved:
        return
    configs["data"]["entries"] = [entry for entry in entries if entry["entry_id"] not in moved]
    backup.mkdir(mode=0o700, exist_ok=True)
    for path in paths:
        copy2(path, backup / path.name)
    for path, data in zip(paths, (configs, devices, entities)):
        stage = path.with_name(path.name + ".sinotek-stage")
        copy2(path, stage)
        stage.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
        stage.replace(path)


if __name__ == "__main__":
    migrate(Path(sys.argv[1]), Path(sys.argv[2]))
