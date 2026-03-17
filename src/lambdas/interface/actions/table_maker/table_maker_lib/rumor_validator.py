#!/usr/bin/env python3
"""
Rumor Validator for table_maker row discovery.

Validates candidates using existing validation system to filter by entity existence
and requirement compliance. Stores validation searches to agent_memory.json for recall
during full validation.
"""

import json
import logging
import hashlib
import tempfile
import os
from typing import Dict, Any, List, Optional
from openpyxl import Workbook

logger = logging.getLogger(__name__)


class RumorValidator:
    """Validate candidates using the validation system + store to agent_memory."""

    def __init__(
        self,
        ai_client,
        session_id: str,
        email: str,
        s3_manager,
        validation_model: str = "sonar",
        context_size: str = "low",
        confidence_threshold: float = 0.7,
        hard_requirement_threshold: float = 0.0
    ):
        """
        Initialize rumor validator.

        Args:
            ai_client: AI client for structured calls
            session_id: Session ID for memory storage
            email: User email
            s3_manager: S3 manager for file operations
            validation_model: Model to use for validation (default: sonar)
            context_size: Search context size (default: low)
            confidence_threshold: Minimum realness score to pass (default: 0.7)
            hard_requirement_threshold: Minimum score for hard requirements (default: 0.0)
        """
        self.ai_client = ai_client
        self.session_id = session_id
        self.email = email
        self.s3_manager = s3_manager
        self.validation_model = validation_model
        self.context_size = context_size
        self.confidence_threshold = confidence_threshold
        self.hard_requirement_threshold = hard_requirement_threshold

    async def validate_candidates(
        self,
        candidates: List[Dict[str, Any]],
        columns: List[Dict[str, Any]],
        requirements: List[Dict[str, Any]],
        table_context: str
    ) -> Dict[str, Any]:
        """
        Validate candidates using the validation system.

        Args:
            candidates: List of candidates to validate (rumor or search candidates)
            columns: Column definitions (ID columns)
            requirements: Hard/soft requirements from search_strategy
            table_context: User context for the table

        Returns:
            {
                "validated_rows": [
                    {
                        # Original candidate fields +
                        "entity_exists": True,
                        "entity_confidence": 0.95,
                        "hard_requirements_met": True,
                        "soft_requirements_score": 0.8,
                        "validation_passed": True,
                        "validation_reasoning": "..."
                    }
                ],
                "filtered_rows": [...],  # Only rows that passed
                "stats": {
                    "total_candidates": 30,
                    "validation_passed": 25,
                    "validation_failed": 5,
                    "validation_time_seconds": 3.5
                }
            }
        """
        import time
        start_time = time.time()

        logger.info(f"[RUMOR_VAL] Starting validation of {len(candidates)} candidates")

        if not candidates:
            return {
                'validated_rows': [],
                'filtered_rows': [],
                'stats': {
                    'total_candidates': 0,
                    'validation_passed': 0,
                    'validation_failed': 0,
                    'validation_time_seconds': 0
                }
            }

        # Step 1: Create validation config programmatically (NO AI)
        validation_config = self._create_validation_config(columns, requirements, table_context)

        # Step 2: Prepare validation rows (add Realness Score column from candidate data)
        validation_rows = self._prepare_validation_rows(candidates, columns)

        # Step 3: Validate batch via validator_invoker
        validation_results = await self._validate_batch(validation_config, validation_rows)

        # Step 4: Parse validation results
        parsed_results = self._parse_validation_results(validation_results, candidates)

        # Step 5: Apply filtering logic
        validated_rows = []
        filtered_rows = []

        for result in parsed_results:
            passed, reasoning = self._apply_filtering_logic(result)
            result['validation_passed'] = passed
            result['validation_reasoning'] = reasoning

            validated_rows.append(result)

            if passed:
                filtered_rows.append(result)

        # Step 6: Store validation searches to agent_memory (handled by validator lambda)
        # The validator lambda automatically stores searches if session_id is provided
        logger.info(
            f"[RUMOR_VAL] Validation complete: {len(filtered_rows)}/{len(candidates)} passed"
        )

        validation_time = time.time() - start_time

        return {
            'validated_rows': validated_rows,
            'filtered_rows': filtered_rows,
            'stats': {
                'total_candidates': len(candidates),
                'validation_passed': len(filtered_rows),
                'validation_failed': len(validated_rows) - len(filtered_rows),
                'validation_time_seconds': round(validation_time, 2)
            }
        }

    def _create_validation_config(
        self,
        columns: List[Dict[str, Any]],
        requirements: List[Dict[str, Any]],
        table_context: str
    ) -> Dict[str, Any]:
        """
        Create validation config programmatically using ValidationConfigBuilder.

        NO AI CALLS - pure Python config generation.

        Args:
            columns: Column definitions (ID columns)
            requirements: Hard/soft requirements
            table_context: User context for the table

        Returns:
            Complete validation config dict
        """
        from .validation_config_builder import ValidationConfigBuilder

        builder = ValidationConfigBuilder(
            validation_model=self.validation_model,
            context_size=self.context_size
        )

        config = builder.build_config(
            columns=columns,
            requirements=requirements,
            table_name="Rumor Validation"
        )

        logger.info(
            f"[RUMOR_VAL] Config built: {len(config['validation_targets'])} validation targets"
        )

        return config

    def _prepare_validation_rows(
        self,
        candidates: List[Dict[str, Any]],
        columns: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Prepare candidates for validation.

        Converts candidates to validation format:
        - Extract ID column values
        - Add Realness Score column from candidate's realness_score field

        Args:
            candidates: List of candidates
            columns: Column definitions

        Returns:
            List of rows ready for validation
        """
        id_column_names = [
            col.get('name', '')
            for col in columns
            if col.get('importance', '').upper() == 'ID'
        ]

        validation_rows = []

        for candidate in candidates:
            id_values = candidate.get('id_values', {})
            realness_score = candidate.get('realness_score', 0.7)

            # Build row dict with ID columns + Realness Score
            row = {}

            # Add ID column values
            for col_name in id_column_names:
                row[col_name] = id_values.get(col_name, '')

            # Add Realness Score as a column (will be validated by validator)
            row['Realness Score'] = realness_score

            validation_rows.append(row)

        logger.info(f"[RUMOR_VAL] Prepared {len(validation_rows)} rows for validation")

        return validation_rows

    async def _validate_batch(
        self,
        validation_config: Dict[str, Any],
        validation_rows: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Validate batch using existing validator lambda.

        Creates temporary Excel + config files, calls validator_invoker,
        returns validation results.

        Args:
            validation_config: Validation config dict
            validation_rows: Rows to validate

        Returns:
            Validation results from validator lambda
        """
        from interface_lambda.core.validator_invoker import invoke_validator_lambda

        # Create temporary Excel file with validation rows
        with tempfile.NamedTemporaryFile(suffix='.xlsx', delete=False, mode='wb') as excel_file:
            wb = Workbook()
            ws = wb.active

            # Write header
            if validation_rows:
                headers = list(validation_rows[0].keys())
                ws.append(headers)

                # Write data rows
                for row in validation_rows:
                    ws.append([row.get(col, '') for col in headers])

            wb.save(excel_file.name)
            excel_temp_path = excel_file.name

        # Create temporary config file
        with tempfile.NamedTemporaryFile(suffix='.json', delete=False, mode='w') as config_file:
            json.dump(validation_config, config_file, indent=2)
            config_temp_path = config_file.name

        try:
            # Upload to S3
            excel_s3_key = f"{self.email}/rumor_validation/{self.session_id}/validation.xlsx"
            config_s3_key = f"{self.email}/rumor_validation/{self.session_id}/config.json"

            self.s3_manager.s3_client.upload_file(excel_temp_path, self.s3_manager.bucket_name, excel_s3_key)
            self.s3_manager.s3_client.upload_file(config_temp_path, self.s3_manager.bucket_name, config_s3_key)

            logger.info(f"[RUMOR_VAL] Uploaded Excel to {excel_s3_key}")
            logger.info(f"[RUMOR_VAL] Uploaded config to {config_s3_key}")

            # Get S3 bucket and lambda name from environment
            S3_CACHE_BUCKET = os.environ.get('S3_CACHE_BUCKET', 'perplexity-cache')
            VALIDATOR_LAMBDA_NAME = os.environ.get('VALIDATOR_LAMBDA_NAME')

            # Invoke validator lambda
            logger.info(f"[RUMOR_VAL] Invoking validator lambda for {len(validation_rows)} rows")

            validation_results = invoke_validator_lambda(
                excel_s3_key=excel_s3_key,
                config_s3_key=config_s3_key,
                max_rows=len(validation_rows),
                batch_size=len(validation_rows),
                S3_CACHE_BUCKET=S3_CACHE_BUCKET,
                VALIDATOR_LAMBDA_NAME=VALIDATOR_LAMBDA_NAME,
                preview_first_row=False,
                preview_max_rows=None,
                session_id=self.session_id,  # CRITICAL: Pass session_id for memory storage
                email=self.email
            )

            logger.info(f"[RUMOR_VAL] Validator lambda completed")

            return validation_results

        finally:
            # Clean up temporary files
            try:
                os.unlink(excel_temp_path)
                os.unlink(config_temp_path)
            except Exception as e:
                logger.warning(f"[RUMOR_VAL] Failed to clean up temp files: {e}")

    def _parse_validation_results(
        self,
        validation_results: Dict[str, Any],
        candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Parse validation results from validator lambda.

        Extracts Realness Score + requirement scores for each row.

        Args:
            validation_results: Results from validator lambda
            candidates: Original candidates

        Returns:
            List of parsed results with validation data merged into candidates
        """
        if not validation_results or 'validation_results' not in validation_results:
            logger.warning("[RUMOR_VAL] No validation results found")
            return candidates

        rows_dict = validation_results['validation_results']

        parsed_results = []

        for i, candidate in enumerate(candidates):
            # Find validation result for this candidate by index
            # Validator results are keyed by row_key (hash of ID values)
            # We'll match by position since we sent them in order
            row_keys = list(rows_dict.keys())

            if i >= len(row_keys):
                logger.warning(f"[RUMOR_VAL] No validation result for candidate {i}")
                parsed_results.append(candidate)
                continue

            row_key = row_keys[i]
            validation_result = rows_dict[row_key]

            # Extract Realness Score validation
            realness_data = validation_result.get('Realness Score', {})
            entity_exists = float(realness_data.get('answer', 0)) >= self.confidence_threshold
            entity_confidence = float(realness_data.get('answer', 0))

            # Extract hard requirement scores
            hard_req_scores = []
            for col_name, col_result in validation_result.items():
                if col_name.startswith('Hard: '):
                    score = float(col_result.get('answer', -999))
                    hard_req_scores.append(score)

            hard_requirements_met = all(
                score >= self.hard_requirement_threshold
                for score in hard_req_scores
            )

            # Extract soft requirement scores
            soft_req_scores = []
            for col_name, col_result in validation_result.items():
                if col_name.startswith('Soft: '):
                    score = float(col_result.get('answer', 0))
                    soft_req_scores.append(score)

            avg_soft_score = sum(soft_req_scores) / len(soft_req_scores) if soft_req_scores else 0

            # Merge validation data into candidate
            result = {**candidate}
            result['entity_exists'] = entity_exists
            result['entity_confidence'] = entity_confidence
            result['hard_requirements_met'] = hard_requirements_met
            result['soft_requirements_score'] = avg_soft_score

            parsed_results.append(result)

        return parsed_results

    def _apply_filtering_logic(self, validation_result: Dict[str, Any]) -> tuple:
        """
        Apply filtering logic to determine pass/fail.

        Rules:
        1. Entity must exist (Realness Score ≥ threshold)
        2. All hard requirements must pass (score ≥ 0)
        3. Soft requirements tracked but not required

        Args:
            validation_result: Parsed validation result

        Returns:
            (passed: bool, reasoning: str)
        """
        # Rule 1: Entity must exist
        entity_exists = validation_result.get('entity_exists', False)
        entity_confidence = validation_result.get('entity_confidence', 0)

        if not entity_exists:
            return False, f"Low realness score ({entity_confidence:.2f} < {self.confidence_threshold})"

        # Rule 2: All hard requirements must pass
        hard_requirements_met = validation_result.get('hard_requirements_met', False)

        if not hard_requirements_met:
            return False, "Failed one or more hard requirements"

        # Soft requirements tracked but not required
        soft_score = validation_result.get('soft_requirements_score', 0)

        return True, f"Passed (realness: {entity_confidence:.2f}, soft avg: {soft_score:.2f})"
