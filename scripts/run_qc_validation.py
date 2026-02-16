"""
Team-based QC Validation Runner
Coordinates multiple validation agents to fact-check metadata entries
"""

import json
import random
from datetime import datetime
from typing import Dict, List
from pathlib import Path

class ValidationCoordinator:
    """Coordinates team-based validation of metadata entries"""

    def __init__(self, json_path: str):
        self.json_path = json_path
        self.data = None
        self.validation_tasks = []
        self.results = []

    def load_and_sample(self, n_rows: int = 20, seed: int = 42):
        """Load data and create validation tasks"""
        with open(self.json_path, 'r', encoding='utf-8') as f:
            self.data = json.load(f)

        random.seed(seed)
        rows = self.data.get('rows', [])
        sampled_rows = random.sample(rows, min(n_rows, len(rows)))

        # Create validation tasks - focus on most important columns
        priority_columns = [
            'Drug Type',
            'Target',
            'Action',
            'Mechanism',
            'Active Indication',
            'Active Organization',
            'R&D Status',
            'Therapeutic Areas'
        ]

        task_id = 1
        for row_idx, row in enumerate(sampled_rows, 1):
            row_key = row.get('row_key', '')
            cells = row.get('cells', {})
            product_cell = cells.get('Product (or Candidate)', {})
            product_name = product_cell.get('display_value', f'Row_{row_idx}')

            for col_name in priority_columns:
                cell = cells.get(col_name)
                if not cell or not cell.get('display_value'):
                    continue

                # Create validation task
                task = {
                    'task_id': f'VAL_{task_id:03d}',
                    'row_number': row_idx,
                    'row_key': row_key,
                    'product_name': product_name,
                    'column_name': col_name,
                    'claim': cell.get('display_value', ''),
                    'confidence': cell.get('confidence', 'UNKNOWN'),
                    'validator_explanation': cell.get('comment', {}).get('validator_explanation', ''),
                    'sources': cell.get('comment', {}).get('sources', []),
                    'key_citation_text': cell.get('comment', {}).get('key_citation', ''),
                }

                self.validation_tasks.append(task)
                task_id += 1

        print(f"Created {len(self.validation_tasks)} validation tasks from {len(sampled_rows)} rows")
        return self.validation_tasks

    def create_validation_prompts(self) -> List[Dict]:
        """Create structured prompts for validation agents"""
        prompts = []

        for task in self.validation_tasks:
            prompt = f"""Validate this drug metadata claim for factual accuracy:

**Product:** {task['product_name']}
**Field:** {task['column_name']}
**Claim:** {task['claim']}
**Stated Confidence:** {task['confidence']}

**Existing Explanation:** {task['validator_explanation']}

**Existing Sources ({len(task['sources'])}):**
{self._format_sources(task['sources'])}

Your task:
1. Search for authoritative sources (PubMed, ClinicalTrials.gov, FDA, company websites)
2. Verify if the claim is factually accurate
3. Check if the existing sources actually support the claim
4. Identify any factual errors, outdated information, or misleading statements

Provide:
- ACCURACY_SCORE (0-100): Use the scoring rubric
- ISSUES: List of specific factual problems found (or "None")
- CITATION_QUALITY: STRONG/MODERATE/WEAK/MISSING
- VERIFICATION_NOTES: Your fact-checking findings
- RECOMMENDED_SCORE: What confidence level this should have (HIGH/MEDIUM/LOW)

Scoring Rubric:
100: Perfect - Claim is exactly correct, fully supported by authoritative sources
90-99: Excellent - Accurate with minor presentational variations
80-89: Good - Substantially correct, minor details may be imprecise
70-79: Acceptable - Mostly correct but has some imprecision
60-69: Marginal - Notable issues but core information is directionally correct
50-59: Poor - Significant inaccuracies but some elements correct
30-49: Very Poor - Mostly incorrect with major factual errors
10-29: Critical - Almost entirely incorrect or misleading
0-9: Fail - Completely false or unsupported"""

            prompts.append({
                'task_id': task['task_id'],
                'product_name': task['product_name'],
                'column_name': task['column_name'],
                'prompt': prompt
            })

        return prompts

    def _format_sources(self, sources: List[Dict]) -> str:
        """Format sources for display"""
        if not sources:
            return "No sources provided"

        formatted = []
        for i, src in enumerate(sources[:3], 1):  # Show top 3
            title = src.get('title', 'No title')
            url = src.get('url', 'No URL')
            snippet = src.get('snippet', '')[:150]
            formatted.append(f"[{i}] {title}\n    URL: {url}\n    Snippet: {snippet}...")

        return "\n".join(formatted)

    def save_validation_batch(self, batch_file: str = 'validation_batch.json'):
        """Save validation tasks for processing"""
        output = {
            'created_at': datetime.now().isoformat(),
            'total_tasks': len(self.validation_tasks),
            'tasks': self.validation_tasks,
            'prompts': self.create_validation_prompts()
        }

        with open(batch_file, 'w', encoding='utf-8') as f:
            json.dump(output, f, indent=2)

        print(f"Saved {len(self.validation_tasks)} tasks to {batch_file}")
        return batch_file

def main():
    """Main execution"""
    coordinator = ValidationCoordinator('theranostic_CI_metadata_take6.json')

    # Sample 20 rows (will generate ~100-120 validation tasks across multiple columns)
    tasks = coordinator.load_and_sample(n_rows=20)

    # Save for batch processing
    batch_file = coordinator.save_validation_batch()

    print(f"\n{'='*60}")
    print("VALIDATION BATCH READY")
    print(f"{'='*60}")
    print(f"Total tasks: {len(tasks)}")
    print(f"Batch file: {batch_file}")
    print(f"\nNext: Process these tasks with validation agents")

    # Show sample task
    if tasks:
        print(f"\nSample task:")
        print(f"  Product: {tasks[0]['product_name']}")
        print(f"  Field: {tasks[0]['column_name']}")
        print(f"  Claim: {tasks[0]['claim'][:100]}...")

if __name__ == '__main__':
    main()
