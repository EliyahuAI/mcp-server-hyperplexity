#!/usr/bin/env python3
"""
Verification script for interview handler two-phase workflow changes.
Checks that all files have been updated correctly without running full tests.
"""

import json
import sys
from pathlib import Path


def verify_schema():
    """Verify interview_response.json schema has trigger_execution"""
    print("[1/3] Verifying interview_response.json schema...")

    schema_path = Path(__file__).parent / 'src' / 'lambdas' / 'interface' / 'actions' / 'table_maker' / 'schemas' / 'interview_response.json'

    with open(schema_path, 'r') as f:
        schema = json.load(f)

    # Check required fields
    assert 'trigger_execution' in schema['required'], "trigger_execution not in required fields"
    assert 'trigger_preview' not in schema['required'], "Old trigger_preview still in required fields"

    # Check properties
    assert 'trigger_execution' in schema['properties'], "trigger_execution not in properties"

    # Check description
    desc = schema['properties']['trigger_execution']['description']
    assert '3-4 minute' in desc, "Description doesn't mention 3-4 minute pipeline"
    assert 'approved' in desc.lower(), "Description doesn't mention approval"

    # Check follow_up_question description
    follow_up_desc = schema['properties']['follow_up_question']['description']
    assert 'trigger_execution' in follow_up_desc, "follow_up_question still references old field name"

    print("  [SUCCESS] Schema correctly updated with trigger_execution")
    return True


def verify_prompt():
    """Verify interview.md prompt has two-phase workflow guidance"""
    print("[2/3] Verifying interview.md prompt...")

    prompt_path = Path(__file__).parent / 'src' / 'lambdas' / 'interface' / 'actions' / 'table_maker' / 'prompts' / 'interview.md'

    with open(prompt_path, 'r', encoding='utf-8') as f:
        prompt = f.read()

    # Check for two-phase workflow section
    assert 'Two-Phase Workflow' in prompt, "Missing 'Two-Phase Workflow' section"
    assert 'Phase 2 will:' in prompt, "Missing Phase 2 description"

    # Check for trigger_execution in examples
    assert 'trigger_execution: true' in prompt, "Examples don't use trigger_execution"
    assert 'trigger_execution: false' in prompt, "Examples don't use trigger_execution"

    # Check old field removed
    assert 'trigger_preview: true' not in prompt, "Old trigger_preview still in examples"

    # Check timing mentioned
    assert '3-4 minutes' in prompt, "Missing 3-4 minute timing"

    # Check approval language
    assert 'Does this match your needs?' in prompt, "Missing approval question"

    print("  [SUCCESS] Prompt correctly updated for two-phase workflow")
    return True


def verify_implementation():
    """Verify interview.py implementation uses trigger_execution"""
    print("[3/3] Verifying interview.py implementation...")

    impl_path = Path(__file__).parent / 'src' / 'lambdas' / 'interface' / 'actions' / 'table_maker' / 'interview.py'

    with open(impl_path, 'r', encoding='utf-8') as f:
        code = f.read()

    # Check docstrings updated
    assert 'triggers execution' in code.lower() or 'trigger_execution' in code, "Docstring not updated"

    # Check return values use trigger_execution
    assert "'trigger_execution':" in code, "Return values don't use trigger_execution"

    # Check backward compatibility
    assert 'trigger_preview' in code, "No backward compatibility handling"
    assert 'trigger_execution' in code, "trigger_execution not in code"

    # Check logging updated
    assert 'Trigger execution' in code or 'trigger_execution' in code, "Logging not updated"

    # Count occurrences - should have both for backward compat
    trigger_execution_count = code.count("'trigger_execution'")
    assert trigger_execution_count >= 5, f"Only {trigger_execution_count} occurrences of 'trigger_execution'"

    print("  [SUCCESS] Implementation correctly uses trigger_execution")
    return True


def main():
    print("="*60)
    print("INTERVIEW HANDLER TWO-PHASE WORKFLOW - VERIFICATION")
    print("="*60)
    print()

    try:
        verify_schema()
        verify_prompt()
        verify_implementation()

        print()
        print("="*60)
        print("[SUCCESS] ALL VERIFICATIONS PASSED")
        print("="*60)
        print()
        print("Summary of changes:")
        print("1. Schema: trigger_preview -> trigger_execution")
        print("2. Prompt: Added two-phase workflow guidance")
        print("3. Implementation: Updated with backward compatibility")
        print()
        print("Ready for deployment and testing!")
        return 0

    except AssertionError as e:
        print()
        print("="*60)
        print(f"[FAILED] Verification failed: {e}")
        print("="*60)
        return 1

    except Exception as e:
        print()
        print("="*60)
        print(f"[ERROR] Unexpected error: {e}")
        print("="*60)
        import traceback
        traceback.print_exc()
        return 1


if __name__ == '__main__':
    sys.exit(main())
