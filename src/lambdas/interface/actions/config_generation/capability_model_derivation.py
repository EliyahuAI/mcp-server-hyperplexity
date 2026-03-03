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
    """Determine group model from capability flags assigned to the group.

    Track selection:
      - P (force_search_flag) → always search track, even if N also present
      - N (trigger_flag) without P → no-search track
      - everything else → search track

    Within search track:
      - C or U → upgrade table (the-clone-claude)
      - P (no C/U) → base_default (the-clone-flash); P overrides Ql
      - Ql (no P, no upgrades) → base_qualitative (sonar-pro)
      - untagged → base_default (the-clone-flash)
    """
    no_search = cfg["no_search_track"]
    search = cfg["search_track"]
    force_flag = search.get("force_search_flag", "")

    # P forces search track, overriding N
    on_no_search = (no_search["trigger_flag"] in flags) and not (force_flag and force_flag in flags)

    if on_no_search:
        upgrades = sum(1 for f in no_search["upgrade_flags"] if f in flags)
        if upgrades == 0:
            return no_search["base"]
        table = no_search["upgrade_table"]
        return table[min(upgrades, len(table)) - 1]
    else:
        upgrades = sum(1 for f in search["upgrade_flags"] if f in flags)
        if upgrades > 0:
            table = search["upgrade_table"]
            return table[min(upgrades, len(table)) - 1]
        # P forces the-clone (base_default), overriding Ql→sonar-pro routing
        if force_flag and force_flag in flags:
            return search["base_default"]
        if search["qualitative_flag"] in flags:
            return search["base_qualitative"]
        return search["base_default"]


def _derive_qc(
    group_models: List[str],
    num_groups: int,
    cfg: Dict,
) -> Tuple[bool, Optional[str]]:
    qc = cfg["qc"]
    if num_groups < qc["min_search_groups"]:
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

    # Use the capability system if ANY non-0 group has the `capability` key present
    # (even with an empty value — empty means "use the default model").
    # Legacy configs that predate this system have no `capability` key at all → no-op.
    has_capability_field = any(
        "capability" in g
        for g in search_groups
        if g.get("group_id", 0) != 0
    )
    if not has_capability_field:
        return config

    if cap_config is None:
        cap_config = _load_config()

    group_models: List[str] = []
    num_groups = 0

    for group in search_groups:
        gid = group["group_id"]
        if gid == 0:
            continue
        if "capability" not in group:
            continue  # skip groups that opted out of the capability system entirely
        cap_str = group.get("capability", "")
        flags = parse_capability(cap_str)  # empty string → empty set → base_default

        model = _group_model(flags, cap_config)
        group["model"] = model
        group_models.append(model)
        num_groups += 1

    config.pop("default_model", None)

    enable_qc, qc_model = _derive_qc(group_models, num_groups, cap_config)
    new_qc = {"enable_qc": enable_qc, **({"model": [qc_model]} if qc_model else {})}
    # Preserve token settings if already configured (e.g. by LLM or previous pass)
    existing_qc = config.get("qc_settings", {})
    for key in ("max_tokens_default", "tokens_per_validated_column_default"):
        if key in existing_qc:
            new_qc[key] = existing_qc[key]
    config["qc_settings"] = new_qc

    logger.info("[CAPABILITY] models=%s qc=%s", group_models, qc_model or "none")
    return config
