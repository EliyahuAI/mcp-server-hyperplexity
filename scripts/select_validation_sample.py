"""
Select 100 representative entries for validation
Ensures coverage across products, columns, and confidence levels
"""

import json
import random
from collections import defaultdict

def select_stratified_sample(tasks, target_count=100, seed=42):
    """
    Select a stratified sample ensuring coverage across:
    - Different products
    - Different column types
    - Different confidence levels
    """
    random.seed(seed)

    # Group tasks by characteristics
    by_confidence = defaultdict(list)
    by_column = defaultdict(list)
    by_product = defaultdict(list)

    for task in tasks:
        by_confidence[task['confidence']].append(task)
        by_column[task['column_name']].append(task)
        by_product[task['product_name']].append(task)

    print(f"Total tasks: {len(tasks)}")
    print(f"\nBy confidence:")
    for conf, items in sorted(by_confidence.items()):
        print(f"  {conf}: {len(items)}")

    print(f"\nBy column:")
    for col, items in sorted(by_column.items()):
        print(f"  {col}: {len(items)}")

    print(f"\nUnique products: {len(by_product)}")

    # Stratified sampling strategy:
    # 1. Ensure all confidence levels are represented proportionally
    # 2. Ensure all column types are represented
    # 3. Diversify across products

    selected = []
    selected_ids = set()

    # First pass: ensure minimum representation from each column
    min_per_column = max(2, target_count // len(by_column))
    for col, col_tasks in by_column.items():
        sample_size = min(min_per_column, len(col_tasks))
        sample = random.sample(col_tasks, sample_size)
        for task in sample:
            if task['task_id'] not in selected_ids:
                selected.append(task)
                selected_ids.add(task['task_id'])

    print(f"\nAfter column-based sampling: {len(selected)} tasks")

    # Second pass: fill remaining slots with stratified random sampling
    remaining_needed = target_count - len(selected)
    if remaining_needed > 0:
        # Pool of unselected tasks
        unselected = [t for t in tasks if t['task_id'] not in selected_ids]

        # Stratify by confidence for remaining slots
        confidence_proportions = {
            conf: len(items) / len(tasks)
            for conf, items in by_confidence.items()
        }

        for conf, proportion in confidence_proportions.items():
            n_to_sample = int(remaining_needed * proportion)
            conf_unselected = [t for t in unselected if t['confidence'] == conf]

            if conf_unselected and n_to_sample > 0:
                sample_size = min(n_to_sample, len(conf_unselected))
                sample = random.sample(conf_unselected, sample_size)
                for task in sample:
                    if task['task_id'] not in selected_ids:
                        selected.append(task)
                        selected_ids.add(task['task_id'])
                        unselected.remove(task)

    # If still under target, randomly fill
    if len(selected) < target_count:
        remaining = [t for t in tasks if t['task_id'] not in selected_ids]
        needed = min(target_count - len(selected), len(remaining))
        extra = random.sample(remaining, needed)
        selected.extend(extra)

    # Trim if over
    if len(selected) > target_count:
        selected = random.sample(selected, target_count)

    return selected

def main():
    # Load validation batch
    with open('validation_batch.json', 'r', encoding='utf-8') as f:
        batch = json.load(f)

    tasks = batch['tasks']

    # Select sample
    sample = select_stratified_sample(tasks, target_count=100)

    # Verify distribution
    print(f"\n{'='*60}")
    print(f"SELECTED SAMPLE: {len(sample)} tasks")
    print(f"{'='*60}")

    sample_by_conf = defaultdict(int)
    sample_by_col = defaultdict(int)
    sample_products = set()

    for task in sample:
        sample_by_conf[task['confidence']] += 1
        sample_by_col[task['column_name']] += 1
        sample_products.add(task['product_name'])

    print(f"\nConfidence distribution:")
    for conf, count in sorted(sample_by_conf.items()):
        print(f"  {conf}: {count}")

    print(f"\nColumn distribution:")
    for col, count in sorted(sample_by_col.items()):
        print(f"  {col}: {count}")

    print(f"\nProducts covered: {len(sample_products)}")

    # Save selected sample
    output = {
        'created_at': batch['created_at'],
        'sample_size': len(sample),
        'total_available': len(tasks),
        'tasks': sample
    }

    with open('validation_sample_100.json', 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2)

    print(f"\nSaved to: validation_sample_100.json")

if __name__ == '__main__':
    main()
