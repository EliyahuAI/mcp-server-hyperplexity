#!/usr/bin/env python3
"""
Validation Config Builder for rumor validation.

Programmatically builds validation configs from templates WITHOUT AI calls.
Pure Python code for config generation.
"""

import copy
import logging
from typing import Dict, Any, List

logger = logging.getLogger(__name__)


class ValidationConfigBuilder:
    """Build validation config programmatically from template - NO AI CALLS."""

    # Static template for validation config
    CONFIG_TEMPLATE = {
        "general_notes": "Rumor validation - entity existence + requirements",
        "search_groups": [
            {
                "group_id": 0,
                "group_name": "Identifiers",
                "description": "ID columns for row identification - not validated"
            },
            {
                "group_id": 1,
                "group_name": "Validation",
                "model": "sonar",
                "search_context_size": "low",
                "description": "Entity existence and requirement validation"
            }
        ],
        "validation_targets": [],  # Populated programmatically
        "qc_settings": {
            "enable_qc": False  # No QC for rumor validation
        }
    }

    def __init__(self, validation_model: str = "sonar", context_size: str = "low"):
        """
        Initialize config builder.

        Args:
            validation_model: Model to use for validation (default: sonar)
            context_size: Search context size (low, medium, high)
        """
        self.validation_model = validation_model
        self.context_size = context_size

    def build_config(
        self,
        columns: List[Dict[str, Any]],
        requirements: List[Dict[str, Any]],
        table_name: str = "Rumor Validation"
    ) -> Dict[str, Any]:
        """
        Build validation config by inserting into template - NO AI CALLS.

        Process:
        1. Start with CONFIG_TEMPLATE (static Python dict)
        2. Insert ID columns into validation_targets (importance='ID', search_group=0)
        3. Insert Realness Score column (type='scale', range 0-1, search_group=1)
        4. Insert hard requirements as scale columns (search_group=1)
        5. Insert soft requirements as scale columns (search_group=1)
        6. Return complete config dict

        Args:
            columns: Column definitions (ID columns from column_definition)
            requirements: Requirements list (hard/soft from search_strategy)
            table_name: Name for the validation config

        Returns:
            Complete validation config dict (ready for validator_invoker)
        """
        logger.info(f"[CONFIG_BUILDER] Building validation config for {table_name}")

        # Deep copy template to avoid mutation
        config = copy.deepcopy(self.CONFIG_TEMPLATE)

        # Update search group model settings
        for group in config['search_groups']:
            if group['group_id'] == 1:
                group['model'] = self.validation_model
                group['search_context_size'] = self.context_size

        validation_targets = []

        # Step 1: Add ID columns (not validated, just for row keys)
        id_columns_added = 0
        for col in columns:
            if col.get('importance', '').upper() == 'ID':
                validation_targets.append({
                    "column": col.get('name', ''),
                    "importance": "ID",
                    "search_group": 0,
                    "description": f"Identifier column: {col.get('name', '')}"
                })
                id_columns_added += 1

        logger.info(f"[CONFIG_BUILDER] Added {id_columns_added} ID columns")

        # Step 2: Add Realness Score (validates entity existence)
        validation_targets.append({
            "column": "Realness Score",
            "type": "scale",
            "scale_definition": "0 (does not exist / fictional / hallucinated) to 1 (definitely exists / verified real entity)",
            "importance": "RESEARCH",
            "search_group": 1,
            "instruction": (
                "Does this entity actually exist? "
                "0 = fictional/hallucinated entity with no evidence of existence, "
                "1 = verified real entity with multiple reliable sources confirming existence. "
                "Use web search to verify existence and find supporting evidence."
            )
        })
        logger.info("[CONFIG_BUILDER] Added Realness Score column")

        # Step 3: Add hard requirements (must all pass with score ≥ 0)
        hard_req_count = 0
        for req in requirements:
            if req.get('type', '').lower() == 'hard':
                req_text = req.get('requirement', '')
                # Truncate for column name (max 100 chars)
                short_text = req_text[:97] + '...' if len(req_text) > 100 else req_text

                validation_targets.append({
                    "column": f"Hard: {short_text}",
                    "type": "scale",
                    "scale_definition": "-2 (strongly disagree / does not meet requirement) to +2 (strongly agree / exceeds requirement)",
                    "importance": "RESEARCH",
                    "search_group": 1,
                    "instruction": (
                        f"Requirement: {req_text}\n\n"
                        "Rate how well this entity meets this requirement:\n"
                        "-2 = strongly disagrees / clearly does not meet requirement\n"
                        "-1 = somewhat disagrees / partially meets requirement\n"
                        "0 = neutral / unclear if requirement is met\n"
                        "+1 = somewhat agrees / mostly meets requirement\n"
                        "+2 = strongly agrees / clearly exceeds requirement\n\n"
                        "Use web search to find evidence supporting your rating."
                    )
                })
                hard_req_count += 1

        logger.info(f"[CONFIG_BUILDER] Added {hard_req_count} hard requirements")

        # Step 4: Add soft requirements (scored but not required)
        soft_req_count = 0
        for req in requirements:
            if req.get('type', '').lower() == 'soft':
                req_text = req.get('requirement', '')
                # Truncate for column name (max 100 chars)
                short_text = req_text[:97] + '...' if len(req_text) > 100 else req_text

                validation_targets.append({
                    "column": f"Soft: {short_text}",
                    "type": "scale",
                    "scale_definition": "-2 (strongly disagree / does not meet preference) to +2 (strongly agree / exceeds preference)",
                    "importance": "RESEARCH",
                    "search_group": 1,
                    "instruction": (
                        f"Preference: {req_text}\n\n"
                        "Rate how well this entity meets this preference:\n"
                        "-2 = strongly disagrees / clearly does not meet preference\n"
                        "-1 = somewhat disagrees / partially meets preference\n"
                        "0 = neutral / unclear if preference is met\n"
                        "+1 = somewhat agrees / mostly meets preference\n"
                        "+2 = strongly agrees / clearly exceeds preference\n\n"
                        "This is a soft requirement - entities can pass validation without meeting this."
                    )
                })
                soft_req_count += 1

        logger.info(f"[CONFIG_BUILDER] Added {soft_req_count} soft requirements")

        # Assign validation targets to config
        config['validation_targets'] = validation_targets

        logger.info(
            f"[CONFIG_BUILDER] Config built successfully: "
            f"{id_columns_added} ID cols, 1 realness col, "
            f"{hard_req_count} hard reqs, {soft_req_count} soft reqs"
        )

        return config
