#!/usr/bin/env python3
"""
Validator Lambda-based QC Reviewer for table generation system.

Uses the validator lambda to perform quality control on discovered rows
with 2x1 hard/soft requirement weighting.
"""

import json
import logging
import time
from typing import Dict, Any, Optional, List

# Configure logging
logger = logging.getLogger(__name__)


class ValidatorQC:
    """Quality control reviewer using validator lambda with requirement-based scoring."""

    def __init__(self, validator_lambda_client, config_template_path: Optional[str] = None):
        """
        Initialize Validator QC.

        Args:
            validator_lambda_client: Client for invoking validator lambda
                                    (e.g., boto3.client('lambda'))
            config_template_path: Optional path to validator config template JSON
        """
        self.validator_lambda_client = validator_lambda_client
        self.config_template_path = config_template_path

        logger.info("Initialized ValidatorQC")

    async def review_rows_with_validator(
        self,
        discovered_rows: List[Dict],
        requirements: List[Dict],
        columns: List[Dict],
        user_context: str,
        table_name: str,
        model: str = "sonar",
        context_size: str = "low",
        min_qc_score: float = 0.5,
        max_rows: int = 50,
        min_row_count: int = 4
    ) -> Dict[str, Any]:
        """
        Review and filter discovered rows using validator lambda with 2x1 weighting.

        Process:
        1. Generate validator config from requirements
        2. Call validator lambda with discovered rows
        3. Parse results with 2x1 hard/soft weighting
        4. Return results in same format as traditional QC

        Args:
            discovered_rows: List of consolidated candidates from row discovery
            requirements: List of requirement dicts with 'requirement', 'type', 'rationale'
            columns: List of column definitions
            user_context: Original user requirements/request
            table_name: Name of the table
            model: AI model to use (default: sonar)
            context_size: Search context size (default: low)
            min_qc_score: Minimum QC score to keep row (default: 0.5)
            max_rows: Maximum number of rows to return (default: 50)
            min_row_count: Minimum number of rows to guarantee (default: 4)

        Returns:
            Dictionary with results matching traditional QC format:
            {
                'success': bool,
                'approved_rows': List[Dict],  # Rows with keep=true, sorted by qc_score
                'rejected_rows': List[Dict],  # Rows with keep=false
                'qc_summary': Dict,  # Summary statistics
                'reviewed_rows': List[Dict],  # All reviewed rows
                'enhanced_data': Dict,  # API call metadata for cost tracking
                'processing_time': float,  # Seconds
                'error': Optional[str]
            }
        """
        result = {
            'success': False,
            'approved_rows': [],
            'rejected_rows': [],
            'qc_summary': {},
            'reviewed_rows': [],
            'enhanced_data': {},
            'processing_time': 0.0,
            'error': None
        }

        start_time = time.time()

        try:
            logger.info(f"Starting Validator QC review of {len(discovered_rows)} rows")

            # Validate inputs
            if not discovered_rows:
                logger.warning("No rows to review")
                result['success'] = True
                result['qc_summary'] = {
                    'total_reviewed': 0,
                    'kept': 0,
                    'rejected': 0,
                    'promoted': 0,
                    'demoted': 0,
                    'reasoning': 'No rows provided for review'
                }
                result['processing_time'] = time.time() - start_time
                return result

            if not requirements:
                error_msg = "No requirements provided for validator QC"
                logger.error(error_msg)
                result['error'] = error_msg
                result['processing_time'] = time.time() - start_time
                return result

            # Generate validator config from requirements
            logger.info("Generating validator config from requirements")
            validator_config = self._generate_validator_config(
                requirements=requirements,
                table_name=table_name,
                columns=columns,
                model=model,
                context_size=context_size
            )

            # TODO: Call validator lambda with config and rows
            # This will be implemented once validator lambda client integration is complete
            # For now, we'll create a placeholder structure
            logger.warning("[TODO] Validator lambda integration not yet implemented")
            logger.info("Validator config generated successfully:")
            logger.info(f"  - Entity Exists column: boolean")
            logger.info(f"  - Hard requirement columns: {sum(1 for r in requirements if r['type'] == 'hard')}")
            logger.info(f"  - Soft requirement columns: {sum(1 for r in requirements if r['type'] == 'soft')}")

            # Placeholder: Parse validator results and apply 2x1 weighting
            # This will process actual validator lambda response when integration is complete
            reviewed_rows = self._parse_validator_results(
                validator_results={},  # TODO: Replace with actual validator response
                discovered_rows=discovered_rows,
                requirements=requirements,
                min_qc_score=min_qc_score
            )

            # Separate approved and rejected rows
            approved_rows = [
                row for row in reviewed_rows
                if row.get('keep', False) and row.get('qc_score', 0) >= min_qc_score
            ]

            rejected_rows_pool = [
                row for row in reviewed_rows
                if not row.get('keep', False)
            ]

            # Apply minimum row guarantee
            minimum_guarantee_applied = False
            promoted_count = 0

            if len(approved_rows) < min_row_count and rejected_rows_pool:
                # Sort rejected rows by qc_score descending
                rejected_sorted = sorted(
                    rejected_rows_pool,
                    key=lambda x: x.get('qc_score', 0),
                    reverse=True
                )

                # Calculate how many we need to promote
                needed = min_row_count - len(approved_rows)
                to_promote = rejected_sorted[:needed]

                # Promote rejected rows to demoted status
                for row in to_promote:
                    row['keep'] = True
                    row['priority_adjustment'] = 'demote'
                    existing_rationale = row.get('qc_rationale', '')
                    if existing_rationale:
                        row['qc_rationale'] = f"{existing_rationale} [Promoted to meet minimum row count]"
                    else:
                        row['qc_rationale'] = "Promoted to meet minimum row count"
                    approved_rows.append(row)
                    promoted_count += 1

                minimum_guarantee_applied = True
                logger.info(f"[MIN_GUARANTEE] Promoted {promoted_count} rejected rows to meet minimum of {min_row_count}")

            # Sort approved rows by priority tier, then by qc_score
            priority_order = {'promote': 0, 'none': 1, 'demote': 2}

            approved_rows_sorted = sorted(
                approved_rows,
                key=lambda x: (
                    priority_order.get(x.get('priority_adjustment', 'none'), 1),
                    -x.get('qc_score', 0)
                ),
            )

            # Apply max_rows limit
            final_approved = approved_rows_sorted[:max_rows]

            # Build QC summary
            demoted_count = sum(1 for row in final_approved if row.get('priority_adjustment') == 'demote')
            promoted_count_final = sum(1 for row in final_approved if row.get('priority_adjustment') == 'promote')

            qc_summary = {
                'total_reviewed': len(reviewed_rows),
                'kept': len(approved_rows),
                'rejected': len(rejected_rows_pool),
                'promoted': promoted_count_final,
                'demoted': demoted_count,
                'reasoning': f'Validator QC with 2x1 hard/soft weighting. Reviewed {len(reviewed_rows)} rows.',
                'minimum_guarantee_applied': minimum_guarantee_applied,
                'insufficient_rows': len(discovered_rows) < min_row_count
            }

            # Build rejected rows list for response
            rejected_rows = []
            for row in rejected_rows_pool:
                row_id = row.get('row_id', 'Unknown')
                rejection_reason = row.get('qc_rationale', 'Failed validator QC criteria')
                rejected_rows.append({
                    'row_id': row_id,
                    'rejection_reason': rejection_reason
                })

            # Build successful result
            result['success'] = True
            result['approved_rows'] = final_approved
            result['rejected_rows'] = rejected_rows
            result['qc_summary'] = qc_summary
            result['reviewed_rows'] = reviewed_rows
            result['processing_time'] = time.time() - start_time

            logger.info(
                f"Validator QC review completed successfully. "
                f"Reviewed: {len(reviewed_rows)}, "
                f"Approved: {len(final_approved)}, "
                f"Rejected: {len(rejected_rows)}, "
                f"Time: {result['processing_time']:.1f}s"
            )

        except Exception as e:
            error_msg = f"Error during Validator QC review: {str(e)}"
            logger.error(error_msg)
            result['error'] = error_msg
            result['processing_time'] = time.time() - start_time

        return result

    def _generate_validator_config(
        self,
        requirements: List[Dict],
        table_name: str,
        columns: List[Dict],
        model: str,
        context_size: str
    ) -> Dict[str, Any]:
        """
        Generate validator config from requirements.

        Creates a validator config with one search group containing:
        - Entity Exists (boolean column)
        - One column per hard requirement (scale -2 to +2)
        - One column per soft requirement (scale -2 to +2)

        Args:
            requirements: List of requirement dicts
            table_name: Name of the table
            columns: List of column definitions
            model: AI model to use
            context_size: Search context size

        Returns:
            Validator config dictionary
        """
        # Separate hard and soft requirements
        hard_requirements = [r for r in requirements if r['type'] == 'hard']
        soft_requirements = [r for r in requirements if r['type'] == 'soft']

        logger.info(f"Generating config: {len(hard_requirements)} hard, {len(soft_requirements)} soft requirements")

        # Build columns for validator config
        validator_columns = []

        # 1. Entity Exists column (boolean)
        validator_columns.append({
            "name": "Entity Exists",
            "type": "boolean",
            "instruction": "Does this entity actually exist? Verify sources are legitimate and entity is real."
        })

        # 2. Hard requirement columns (scale -2 to +2)
        for req in hard_requirements:
            validator_columns.append({
                "name": f"Hard Req: {req['requirement'][:50]}",  # Truncate for readability
                "type": "scale",
                "scale_definition": "-2 (strongly disagree) to +2 (strongly agree)",
                "instruction": f"Statement: {req['requirement']}. Rate how well this entity meets this requirement."
            })

        # 3. Soft requirement columns (scale -2 to +2)
        for req in soft_requirements:
            validator_columns.append({
                "name": f"Soft Req: {req['requirement'][:50]}",  # Truncate for readability
                "type": "scale",
                "scale_definition": "-2 (strongly disagree) to +2 (strongly agree)",
                "instruction": f"Statement: {req['requirement']}. Rate how well this entity meets this requirement."
            })

        # Build validator config structure
        validator_config = {
            "table_name": table_name,
            "search_groups": [
                {
                    "name": "Row Quality Check",
                    "model": model,
                    "search_context_size": context_size,
                    "columns": validator_columns
                }
            ]
        }

        return validator_config

    def _parse_validator_results(
        self,
        validator_results: Dict,
        discovered_rows: List[Dict],
        requirements: List[Dict],
        min_qc_score: float
    ) -> List[Dict]:
        """
        Parse validator results and apply 2x1 hard/soft weighting.

        Scoring formula:
        - Reject if Entity Exists = False OR any hard requirement < 0
        - Otherwise calculate qc_score with 2x1 weighting:
          - Normalize scores: (score + 2) / 4  (converts -2 to +2 into 0 to 1)
          - Weight: hard * 2, soft * 1
          - qc_score = weighted_sum / total_weight
        - Status:
          - Reject: Entity Exists = False OR any hard < 0
          - Demote: All hard >= 0 but avg hard < 0.5 OR qc_score < 0.5
          - Approve: qc_score >= 0.5

        Args:
            validator_results: Results from validator lambda (TODO: will be populated)
            discovered_rows: Original discovered rows
            requirements: List of requirements
            min_qc_score: Minimum score threshold

        Returns:
            List of reviewed rows with qc_score, keep, priority_adjustment
        """
        # TODO: This will parse actual validator lambda response
        # For now, create placeholder structure
        logger.info("[TODO] Parsing placeholder validator results - will use actual results when integration complete")

        reviewed_rows = []

        # Separate hard and soft requirements for counting
        hard_count = sum(1 for r in requirements if r['type'] == 'hard')
        soft_count = sum(1 for r in requirements if r['type'] == 'soft')

        for idx, row in enumerate(discovered_rows, 1):
            # Create row_id
            id_values = row.get('id_values', {})
            first_id_value = list(id_values.values())[0] if id_values else 'Unknown'
            row_id = f"{idx}-{first_id_value}"

            # TODO: Extract actual validator scores from validator_results
            # For now, use placeholder logic based on discovery score
            row_score = row.get('match_score', 0.5)

            # Placeholder: Simulate validator scoring
            entity_exists = True  # TODO: Get from validator results
            hard_scores = [0.5 + (row_score - 0.5) * 0.8] * hard_count  # TODO: Get from validator
            soft_scores = [0.5 + (row_score - 0.5) * 0.6] * soft_count  # TODO: Get from validator

            # Apply 2x1 weighting formula
            qc_score, keep, priority_adjustment, qc_rationale = self._calculate_weighted_score(
                entity_exists=entity_exists,
                hard_scores=hard_scores,
                soft_scores=soft_scores,
                min_qc_score=min_qc_score
            )

            # Merge with original row data
            merged = row.copy()
            merged['row_id'] = row_id
            merged['qc_score'] = qc_score
            merged['qc_rationale'] = qc_rationale
            merged['keep'] = keep
            merged['priority_adjustment'] = priority_adjustment

            reviewed_rows.append(merged)

        return reviewed_rows

    def _calculate_weighted_score(
        self,
        entity_exists: bool,
        hard_scores: List[float],
        soft_scores: List[float],
        min_qc_score: float
    ) -> tuple[float, bool, str, str]:
        """
        Calculate weighted QC score with 2x1 hard/soft weighting.

        Args:
            entity_exists: Whether entity exists (boolean)
            hard_scores: List of hard requirement scores (-2 to +2)
            soft_scores: List of soft requirement scores (-2 to +2)
            min_qc_score: Minimum score threshold

        Returns:
            Tuple of (qc_score, keep, priority_adjustment, qc_rationale)
        """
        # Check reject conditions
        if not entity_exists:
            return 0.0, False, 'none', 'Entity does not exist'

        if any(score < 0 for score in hard_scores):
            return 0.0, False, 'none', 'Failed hard requirement (score < 0)'

        # Normalize scores from -2 to +2 range into 0 to 1
        hard_normalized = [(score + 2) / 4 for score in hard_scores]
        soft_normalized = [(score + 2) / 4 for score in soft_scores]

        # Calculate weighted sum (hard requirements weighted 2x soft)
        total_weight = len(hard_scores) * 2 + len(soft_scores) * 1
        weighted_sum = sum(h * 2 for h in hard_normalized) + sum(s * 1 for s in soft_normalized)

        # Calculate final QC score
        if total_weight > 0:
            qc_score = weighted_sum / total_weight
        else:
            qc_score = 0.5  # Default if no requirements

        # Calculate average hard score for demote logic
        avg_hard = sum(hard_normalized) / len(hard_normalized) if hard_normalized else 1.0

        # Determine status
        if avg_hard < 0.5 or qc_score < min_qc_score:
            # Demote: meets hard requirements but low score
            keep = True
            priority_adjustment = 'demote'
            qc_rationale = f'Marginal fit (qc_score={qc_score:.2f}, avg_hard={avg_hard:.2f})'
        elif qc_score >= 0.75:
            # Promote: excellent fit
            keep = True
            priority_adjustment = 'promote'
            qc_rationale = f'Excellent fit (qc_score={qc_score:.2f})'
        else:
            # Approve: good fit
            keep = True
            priority_adjustment = 'none'
            qc_rationale = f'Good fit (qc_score={qc_score:.2f})'

        return qc_score, keep, priority_adjustment, qc_rationale
