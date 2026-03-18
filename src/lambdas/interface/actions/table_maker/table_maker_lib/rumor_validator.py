#!/usr/bin/env python3
"""
Rumor Validator for table_maker row discovery.

Validates V-disposition candidates using existing validation system to filter by entity existence
and requirement compliance. K-disposition candidates bypass validation entirely.
Stores validation searches to agent_memory.json for recall during full validation.
"""

import json
import logging
import os
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)


class RumorValidator:
    """Validate candidates using the validation system + store to agent_memory."""

    def __init__(
        self,
        ai_client,
        session_id: str,
        email: str,
        s3_manager,
        conversation_id: str = "",
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
            conversation_id: Conversation ID (used for S3 config path)
            validation_model: Model to use for validation (default: sonar)
            context_size: Search context size (default: low)
            confidence_threshold: Minimum entity-exists score to pass (default: 0.7)
            hard_requirement_threshold: Minimum score for hard requirements (default: 0.0)
        """
        self.ai_client = ai_client
        self.session_id = session_id
        self.email = email
        self.s3_manager = s3_manager
        self.conversation_id = conversation_id
        self.validation_model = validation_model
        self.context_size = context_size
        self.confidence_threshold = confidence_threshold
        self.hard_requirement_threshold = hard_requirement_threshold

    async def validate_candidates(
        self,
        validate_candidates: List[Dict[str, Any]],
        columns: List[Dict[str, Any]],
        requirements: List[Dict[str, Any]],
        table_context: str
    ) -> Dict[str, Any]:
        """
        Validate V-disposition candidates using the validation system.

        K-disposition candidates should be passed via keep_candidates in execution.py
        and merged after this call — they are NOT passed here.

        Args:
            validate_candidates: V-disposition candidates to validate
            columns: Column definitions (ID columns)
            requirements: Hard/soft requirements from search_strategy
            table_context: User context for the table

        Returns:
            {
                "validated_rows": [...],  # All V candidates with validation data
                "filtered_rows": [...],   # Only rows that passed validation
                "stats": {...}
            }
        """
        import time
        start_time = time.time()

        logger.info(f"[RUMOR_VAL] Starting validation of {len(validate_candidates)} V-disposition candidates")

        if not validate_candidates:
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

        # Step 2: Prepare validation rows
        validation_rows = self._prepare_validation_rows(validate_candidates, columns)

        # Step 3: Validate batch via direct payload (no Excel)
        validation_results = await self._validate_batch(validation_config, validation_rows)

        # Step 4: Parse validation results
        parsed_results = self._parse_validation_results(validation_results, validate_candidates)

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

        logger.info(
            f"[RUMOR_VAL] Validation complete: {len(filtered_rows)}/{len(validate_candidates)} passed"
        )

        validation_time = time.time() - start_time

        # Build enhanced_data for cost tracking by caller
        enhanced_data = self._build_enhanced_data(validation_results, validation_time)
        cost_usd = enhanced_data.get('costs', {}).get('actual', {}).get('total_cost', 0.0)

        return {
            'validated_rows': validated_rows,
            'filtered_rows': filtered_rows,
            'enhanced_data': enhanced_data,
            'stats': {
                'total_candidates': len(validate_candidates),
                'validation_passed': len(filtered_rows),
                'validation_failed': len(validated_rows) - len(filtered_rows),
                'validation_time_seconds': round(validation_time, 2),
                'cost_usd': cost_usd,
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
        Prepare V-disposition candidates as flat row dicts (ID column values only).

        Row keys are NOT added here — they are generated by S3TableParser after
        the rows are written to CSV and parsed back, ensuring consistency with the
        rest of the validation system.
        """
        id_column_names = [
            col.get('name', '')
            for col in columns
            if col.get('importance', '').upper() == 'ID'
        ]

        validation_rows = []

        for candidate in candidates:
            id_values = candidate.get('id_values', {})
            row = {}
            for col_name in id_column_names:
                row[col_name] = id_values.get(col_name, '')
            validation_rows.append(row)

        logger.info(f"[RUMOR_VAL] Prepared {len(validation_rows)} flat rows for CSV write")

        return validation_rows

    async def _validate_batch(
        self,
        validation_config: Dict[str, Any],
        validation_rows: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Validate batch using direct payload to validator lambda.

        Steps:
        1. Write V-candidate rows as CSV to table maker S3 path
           (results/.../table_maker/{conv_id}/rumor_validate_candidates.csv)
        2. Parse with S3TableParser to get rows with _row_key (same code path
           as the rest of the validation system)
        3. Write config JSON beside the CSV in the table maker folder
           (results/.../table_maker/{conv_id}/rumor_validation_config.json)
        4. Invoke validator lambda with rows passed directly in payload (no Excel)
        """
        import csv
        import io
        from interface_lambda.core.validator_invoker import invoke_validator_lambda_with_rows
        from shared_table_parser import S3TableParser

        VALIDATOR_LAMBDA_NAME = os.environ.get('VALIDATOR_LAMBDA_NAME')
        main_bucket = self.s3_manager.bucket_name

        # Step 1: Write V-candidates as CSV into table maker results folder
        if not validation_rows:
            return {'validation_results': {}, 'metadata': {}}

        col_names = [k for k in validation_rows[0].keys() if not k.startswith('_')]
        csv_buffer = io.StringIO()
        writer = csv.DictWriter(csv_buffer, fieldnames=col_names)
        writer.writeheader()
        for row in validation_rows:
            writer.writerow({k: row.get(k, '') for k in col_names})

        csv_s3_key = self.s3_manager.get_table_maker_path(
            email=self.email,
            session_id=self.session_id,
            conversation_id=self.conversation_id or 'default',
            file_name='rumor_validate_candidates.csv'
        )
        self.s3_manager.s3_client.put_object(
            Bucket=main_bucket,
            Key=csv_s3_key,
            Body=csv_buffer.getvalue().encode('utf-8'),
            ContentType='text/csv'
        )
        logger.info(f"[RUMOR_VAL] Wrote {len(validation_rows)} V-candidates to s3://{main_bucket}/{csv_s3_key}")

        # Step 2: Parse CSV with S3TableParser to get consistent _row_key values
        table_parser = S3TableParser()
        parsed_data = table_parser.parse_s3_table(main_bucket, csv_s3_key)
        rows_with_keys = parsed_data.get('data', [])
        logger.info(f"[RUMOR_VAL] S3TableParser returned {len(rows_with_keys)} rows with _row_key")

        # Step 3: Write config JSON beside the V-candidates CSV in the table maker folder.
        # Pass main_bucket + this key to the validator lambda — no separate cache bucket needed.
        config_bytes = json.dumps(validation_config, indent=2).encode('utf-8')

        config_s3_key = self.s3_manager.get_table_maker_path(
            email=self.email,
            session_id=self.session_id,
            conversation_id=self.conversation_id or 'default',
            file_name='rumor_validation_config.json'
        )
        self.s3_manager.s3_client.put_object(
            Bucket=main_bucket,
            Key=config_s3_key,
            Body=config_bytes,
            ContentType='application/json'
        )
        logger.info(f"[RUMOR_VAL] Wrote config to s3://{main_bucket}/{config_s3_key}")

        # Step 4: Invoke validator lambda with rows inline (no Excel)
        logger.info(f"[RUMOR_VAL] Invoking validator lambda for {len(rows_with_keys)} V-disposition rows")

        validation_results = invoke_validator_lambda_with_rows(
            rows=rows_with_keys,
            config_s3_key=config_s3_key,
            S3_CACHE_BUCKET=main_bucket,
            VALIDATOR_LAMBDA_NAME=VALIDATOR_LAMBDA_NAME,
            session_id=self.session_id,
            email=self.email
        )

        logger.info(f"[RUMOR_VAL] Validator lambda completed")

        return validation_results

    def _parse_validation_results(
        self,
        validation_results: Dict[str, Any],
        candidates: List[Dict[str, Any]]
    ) -> List[Dict[str, Any]]:
        """
        Parse validation results from validator lambda.

        Extracts Entity Exists score + requirement scores for each row.
        Falls back to parsing the old "Realness Score" column name if present.
        """
        if not validation_results or 'validation_results' not in validation_results:
            logger.warning("[RUMOR_VAL] No validation results found")
            return candidates

        rows_dict = validation_results['validation_results']

        parsed_results = []

        for i, candidate in enumerate(candidates):
            row_keys = list(rows_dict.keys())

            if i >= len(row_keys):
                logger.warning(f"[RUMOR_VAL] No validation result for candidate {i}")
                parsed_results.append(candidate)
                continue

            row_key = row_keys[i]
            validation_result = rows_dict[row_key]

            # Extract Entity Exists score (new, -2..+2 scale) or Realness Score (legacy, 0-1)
            # Detect by column name to avoid ambiguity — values 0 and 1 are valid on both scales
            if 'Entity Exists' in validation_result:
                entity_data = validation_result['Entity Exists']
                try:
                    # -2..+2 → normalize to 0-1: (-2→0.0, -1→0.25, 0→0.5, 1→0.75, 2→1.0)
                    entity_confidence = (float(entity_data.get('value', -2)) + 2) / 4.0
                except (ValueError, TypeError):
                    entity_confidence = 0.0
            else:
                entity_data = validation_result.get('Realness Score', {})
                try:
                    entity_confidence = float(entity_data.get('value', 0))
                except (ValueError, TypeError):
                    entity_confidence = 0.0
            entity_exists = entity_confidence >= self.confidence_threshold

            # Extract hard requirement scores
            hard_req_scores = []
            for col_name, col_result in validation_result.items():
                if col_name.startswith('Hard: '):
                    val = str(col_result.get('value', '')).strip().lower()
                    score = 1.0 if val in ('yes', 'true', '1', 'pass', 'passed') else 0.0
                    hard_req_scores.append(score)

            hard_requirements_met = all(
                score >= self.hard_requirement_threshold
                for score in hard_req_scores
            )

            # Extract soft requirement scores
            soft_req_scores = []
            for col_name, col_result in validation_result.items():
                if col_name.startswith('Soft: '):
                    val = str(col_result.get('value', '')).strip().lower()
                    score = 1.0 if val in ('yes', 'true', '1', 'pass', 'passed') else 0.0
                    soft_req_scores.append(score)

            avg_soft_score = sum(soft_req_scores) / len(soft_req_scores) if soft_req_scores else 0

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
        1. Entity must exist (Entity Exists score ≥ threshold)
        2. All hard requirements must pass
        3. Soft requirements tracked but not required
        """
        entity_exists = validation_result.get('entity_exists', False)
        entity_confidence = validation_result.get('entity_confidence', 0)

        if not entity_exists:
            return False, f"Entity not confirmed ({entity_confidence:.2f} < {self.confidence_threshold})"

        hard_requirements_met = validation_result.get('hard_requirements_met', False)

        if not hard_requirements_met:
            return False, "Failed one or more hard requirements"

        soft_score = validation_result.get('soft_requirements_score', 0)

        return True, f"Passed (entity_confidence: {entity_confidence:.2f}, soft avg: {soft_score:.2f})"

    def _build_enhanced_data(self, validation_results: Dict[str, Any], processing_time: float) -> Dict[str, Any]:
        """
        Convert validator lambda metadata into the enhanced_data format expected by
        _add_api_call_to_runs so rumor validation costs are tracked in the runs DB.
        """
        from datetime import datetime, timezone

        token_usage = validation_results.get('metadata', {}).get('token_usage', {})
        total_cost = token_usage.get('total_cost', 0.0)
        total_tokens = token_usage.get('total_tokens', 0)

        # Build provider_metrics from by_provider breakdown
        provider_metrics = {}
        for provider, pdata in token_usage.get('by_provider', {}).items():
            pcost = pdata.get('total_cost', 0.0)
            ptokens = pdata.get('total_tokens', 0)
            pcalls = pdata.get('calls', 0)
            if pcost > 0 or ptokens > 0:
                provider_metrics[provider] = {
                    'calls': pcalls,
                    'tokens': ptokens,
                    'cost_actual': pcost,
                    'cost_estimated': pcost,
                    'time_actual': processing_time,
                    'time_estimated': processing_time,
                    'cache_hit_tokens': 0,
                }

        if not provider_metrics:
            provider_metrics['perplexity'] = {
                'calls': token_usage.get('api_calls', 1),
                'tokens': total_tokens,
                'cost_actual': total_cost,
                'cost_estimated': total_cost,
                'time_actual': processing_time,
                'time_estimated': processing_time,
                'cache_hit_tokens': 0,
            }

        cost_entry = {'total_cost': total_cost, 'input_cost': 0.0, 'output_cost': total_cost}

        return {
            'call_info': {
                'model': self.validation_model,
                'api_provider': next(iter(provider_metrics), 'perplexity'),
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'search_context_size': self.context_size,
                'max_web_searches': token_usage.get('api_calls', 0),
            },
            'tokens': {
                'input_tokens': 0,
                'output_tokens': 0,
                'total_tokens': total_tokens,
                'cache_creation_tokens': 0,
                'cache_read_tokens': token_usage.get('cached_calls', 0),
                'thoughts_token_count': 0,
                'candidates_token_count': 0,
            },
            'costs': {
                'actual': cost_entry,
                'estimated': cost_entry,
                'cache_savings': {'absolute_savings': 0.0, 'percentage_savings': 0.0},
            },
            'timing': {
                'time_actual_seconds': processing_time,
                'time_estimated_seconds': processing_time,
            },
            'caching': {},
            'per_row': {},
            'is_top_level_call': True,
            'provider_metrics': provider_metrics,
        }
