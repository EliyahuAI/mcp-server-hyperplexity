"""
QC Validation Framework for Theranostic Drug Metadata
Validates entries and scores accuracy on a 0-100 scale
"""

import json
import random
from typing import Dict, List, Any
from dataclasses import dataclass, asdict
from collections import defaultdict

@dataclass
class AccuracyScore:
    """
    Accuracy scoring system (0-100) for metadata validation

    Scoring Guidelines:
    100: Perfect - Claim is exactly correct, fully supported by authoritative sources, no issues
    90-99: Excellent - Claim is accurate with minor presentational variations (e.g., formatting)
    80-89: Good - Claim is substantially correct, minor details may be imprecise but not misleading
    70-79: Acceptable - Claim is mostly correct but has some imprecision or minor inaccuracies
    60-69: Marginal - Claim has notable issues but core information is directionally correct
    50-59: Poor - Claim has significant inaccuracies but some elements are correct
    30-49: Very Poor - Claim is mostly incorrect with major factual errors
    10-29: Critical - Claim is almost entirely incorrect or misleading
    0-9: Fail - Claim is completely false or unsupported

    Deductions:
    - Wrong target/mechanism: -30 to -50 points
    - Wrong organization/developer: -20 to -30 points
    - Wrong indication/therapeutic area: -15 to -25 points
    - Wrong development status: -10 to -20 points
    - Outdated information: -5 to -15 points
    - Citation doesn't support claim: -20 to -40 points
    - Missing important qualifier: -5 to -10 points
    """
    score: int  # 0-100
    rationale: str
    issues_found: List[str]
    strengths: List[str]

@dataclass
class ValidationResult:
    """Result of validating a single cell"""
    row_key: str
    product_name: str
    column_name: str
    display_value: str
    confidence: str
    accuracy_score: AccuracyScore
    citation_quality: str  # "STRONG", "MODERATE", "WEAK", "MISSING"
    factual_errors: List[str]
    timestamp: str

class MetadataValidator:
    """Validates metadata entries for factual accuracy"""

    def __init__(self, json_path: str):
        self.json_path = json_path
        self.data = None
        self.validation_results: List[ValidationResult] = []

    def load_data(self):
        """Load the JSON metadata file"""
        with open(self.json_path, 'r', encoding='utf-8') as f:
            self.data = json.load(f)
        print(f"Loaded {len(self.data.get('rows', []))} rows")

    def sample_entries(self, n: int = 100, seed: int = 42) -> List[Dict]:
        """Sample n random entries for validation"""
        random.seed(seed)
        rows = self.data.get('rows', [])
        sample_size = min(n, len(rows))
        sampled_rows = random.sample(rows, sample_size)

        # Extract cells to validate
        entries = []
        for row in sampled_rows:
            row_key = row.get('row_key', '')
            product_name = row.get('cells', {}).get('Product (or Candidate)', {}).get('display_value', '')

            # Select key columns to validate
            key_columns = [
                'Drug Type', 'Target', 'Action', 'Mechanism',
                'Active Indication', 'Active Organization', 'R&D Status'
            ]

            for col_name in key_columns:
                cell = row.get('cells', {}).get(col_name)
                if cell and cell.get('display_value'):
                    entries.append({
                        'row_key': row_key,
                        'product_name': product_name,
                        'column_name': col_name,
                        'cell': cell
                    })

        print(f"Generated {len(entries)} cell validation tasks from {sample_size} rows")
        return entries

    def validate_entry(self, entry: Dict) -> ValidationResult:
        """
        Validate a single entry
        This is a placeholder - actual validation would involve web search/fact checking
        """
        cell = entry['cell']

        # Placeholder scoring logic - would be replaced with actual fact-checking
        accuracy_score = AccuracyScore(
            score=85,  # Placeholder
            rationale="Placeholder - needs actual validation",
            issues_found=[],
            strengths=[]
        )

        return ValidationResult(
            row_key=entry['row_key'],
            product_name=entry['product_name'],
            column_name=entry['column_name'],
            display_value=cell.get('display_value', ''),
            confidence=cell.get('confidence', ''),
            accuracy_score=accuracy_score,
            citation_quality="MODERATE",  # Placeholder
            factual_errors=[],
            timestamp="2024-01-01"  # Would use actual timestamp
        )

    def analyze_confidence_vs_accuracy(self) -> Dict:
        """Analyze correlation between confidence and accuracy scores"""
        by_confidence = defaultdict(list)

        for result in self.validation_results:
            by_confidence[result.confidence].append(result.accuracy_score.score)

        stats = {}
        for conf_level, scores in by_confidence.items():
            if scores:
                stats[conf_level] = {
                    'count': len(scores),
                    'mean_accuracy': sum(scores) / len(scores),
                    'min_accuracy': min(scores),
                    'max_accuracy': max(scores),
                    'below_70': sum(1 for s in scores if s < 70),
                    'below_70_pct': (sum(1 for s in scores if s < 70) / len(scores)) * 100
                }

        return stats

    def generate_report(self) -> Dict:
        """Generate comprehensive QC report"""
        total = len(self.validation_results)
        if total == 0:
            return {"error": "No validation results"}

        scores = [r.accuracy_score.score for r in self.validation_results]

        report = {
            'summary': {
                'total_validated': total,
                'mean_accuracy': sum(scores) / total,
                'median_accuracy': sorted(scores)[total // 2],
                'min_accuracy': min(scores),
                'max_accuracy': max(scores),
                'std_dev': self._calculate_std_dev(scores)
            },
            'score_distribution': {
                'excellent_90_100': sum(1 for s in scores if s >= 90),
                'good_80_89': sum(1 for s in scores if 80 <= s < 90),
                'acceptable_70_79': sum(1 for s in scores if 70 <= s < 80),
                'marginal_60_69': sum(1 for s in scores if 60 <= s < 70),
                'poor_below_60': sum(1 for s in scores if s < 60)
            },
            'confidence_vs_accuracy': self.analyze_confidence_vs_accuracy(),
            'error_rate': (sum(1 for s in scores if s < 70) / total) * 100,
            'problematic_entries': [
                {
                    'product': r.product_name,
                    'column': r.column_name,
                    'confidence': r.confidence,
                    'accuracy': r.accuracy_score.score,
                    'issues': r.accuracy_score.issues_found
                }
                for r in self.validation_results if r.accuracy_score.score < 70
            ]
        }

        return report

    @staticmethod
    def _calculate_std_dev(scores: List[float]) -> float:
        """Calculate standard deviation"""
        mean = sum(scores) / len(scores)
        variance = sum((s - mean) ** 2 for s in scores) / len(scores)
        return variance ** 0.5

def main():
    """Main execution function"""
    validator = MetadataValidator('theranostic_CI_metadata_take6.json')
    validator.load_data()

    # Sample 100 entries
    entries = validator.sample_entries(n=100)

    print(f"\nReady to validate {len(entries)} entries")
    print("Next step: Implement actual validation with web search/fact checking")

    # Save sample for inspection
    with open('validation_sample.json', 'w', encoding='utf-8') as f:
        json.dump(entries[:10], f, indent=2)  # Save first 10 for inspection

    print("\nSaved sample to validation_sample.json")

if __name__ == '__main__':
    main()
