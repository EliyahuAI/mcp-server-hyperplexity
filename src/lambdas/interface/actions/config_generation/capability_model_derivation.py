"""capability_model_derivation.py

Reads capability_config.json and derives group models + QC settings from per-group
capability flags (set directly on each search group, not on individual columns).
No model names or business logic here — all rules live in the config file.
"""

import json
import logging
import os
from typing import Any, Dict, List, Optional, Set, Tuple

logger = logging.getLogger(__name__)

_CONFIG_PATH = os.path.join(os.path.dirname(__file__), "capability_config.json")


def _load_config() -> Dict[str, Any]:
    try:
        with open(_CONFIG_PATH) as f:
            return json.load(f)
    except FileNotFoundError:
        raise RuntimeError(f"capability_config.json not found at {_CONFIG_PATH}") from None
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"capability_config.json is malformed: {exc}") from exc


def parse_capability(code: str) -> Set[str]:
    if not code or not code.strip():
        return set()
    return {f.strip() for f in code.split("|") if f.strip()}


def _group_model(flags: Set[str], cfg: Dict) -> str:
    """Determine group model from capability flags assigned to the group."""
    if cfg["no_search_track"]["trigger_flag"] in flags:
        track = cfg["no_search_track"]
        upgrades = sum(1 for f in track["upgrade_flags"] if f in flags)
        if upgrades == 0:
            return track["base"]
        table = track["upgrade_table"]
        return table[min(upgrades, len(table)) - 1]
    else:
        track = cfg["search_track"]
        upgrades = sum(1 for f in track["upgrade_flags"] if f in flags)
        if upgrades > 0:
            table = track["upgrade_table"]
            return table[min(upgrades, len(table)) - 1]
        if track["qualitative_flag"] in flags:
            return track["base_qualitative"]
        return track["base_default"]


def _derive_qc(
    group_models: List[str],
    num_groups: int,
    cfg: Dict,
    has_p_flag: bool = False,
) -> Tuple[bool, Optional[str]]:
    qc = cfg["qc"]
    # P flag enables QC even for single-group configs (provenance verification)
    if num_groups < qc["min_search_groups"] and not has_p_flag:
        return False, None
    elv_substr = qc.get("elevated_if_model_contains", "")
    if elv_substr and any(elv_substr in m for m in group_models):
        return True, qc["elevated"]
    return True, qc["standard"]


def derive_model_config(
    config: Dict[str, Any],
    cap_config: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Derive group models and qc_settings from per-group capability codes.

    Flags are read from each search group's `capability` field (e.g. "Ql|P").
    Groups without a capability field are skipped (no-op for legacy configs).
    """
    search_groups = config.get("search_groups", [])

    has_capabilities = any(
        g.get("capability", "").strip()
        for g in search_groups
        if g.get("group_id", 0) != 0
    )
    if not has_capabilities:
        return config

    if cap_config is None:
        cap_config = _load_config()

    group_models: List[str] = []
    num_groups = 0
    has_p_flag = False

    for group in search_groups:
        gid = group["group_id"]
        if gid == 0:
            continue
        cap_str = group.get("capability", "")
        if not cap_str or not cap_str.strip():
            continue
        flags = parse_capability(cap_str)
        if "P" in flags:
            has_p_flag = True

        model = _group_model(flags, cap_config)
        group["model"] = model
        group_models.append(model)
        num_groups += 1

    config.pop("default_model", None)

    enable_qc, qc_model = _derive_qc(group_models, num_groups, cap_config, has_p_flag=has_p_flag)
    new_qc = {"enable_qc": enable_qc, **({"model": [qc_model]} if qc_model else {})}
    # Preserve token settings if already configured (e.g. by LLM or previous pass)
    existing_qc = config.get("qc_settings", {})
    for key in ("max_tokens_default", "tokens_per_validated_column_default"):
        if key in existing_qc:
            new_qc[key] = existing_qc[key]
    config["qc_settings"] = new_qc

    logger.info("[CAPABILITY] models=%s qc=%s", group_models, qc_model or "none")
    return config
