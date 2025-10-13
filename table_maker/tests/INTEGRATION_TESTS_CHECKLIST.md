# Integration Tests Pre-Run Checklist

## Before Running Tests

### Environment Setup
- [ ] ANTHROPIC_API_KEY is set in environment
  ```bash
  echo $ANTHROPIC_API_KEY
  ```
- [ ] API key has sufficient credits
- [ ] Python 3.8+ is installed
- [ ] All dependencies are installed (`pip install -r requirements.txt`)
- [ ] Current directory is `table_maker/`

### File Verification
- [ ] `tests/test_integration.py` exists
- [ ] `tests/conftest.py` exists with fixtures
- [ ] `pytest.ini` exists
- [ ] `prompts/` directory has template files
- [ ] `schemas/` directory has schema files

### Expected Test Files
- [ ] test_integration.py (integration tests)
- [ ] conftest.py (fixtures)
- [ ] README.md (documentation)

## Running Tests

### Quick Commands
```bash
# All integration tests
pytest -m integration tests/test_integration.py -v

# With helper script
./run_integration_tests.sh

# Single test
pytest tests/test_integration.py::test_full_conversation_flow -v -s
```

### Expected Behavior
- [ ] Tests start without import errors
- [ ] API key validation passes
- [ ] Fixtures load successfully
- [ ] Tests show progress logs
- [ ] Temporary directories created
- [ ] Tests complete (may take 10-15 min)
- [ ] Temporary files cleaned up

## Post-Run Verification

### Success Indicators
- [ ] All tests show PASSED status
- [ ] No ERROR messages in logs
- [ ] [SUCCESS] markers visible
- [ ] Summary shows test count
- [ ] No leftover temporary files

### Failure Investigation
If tests fail:
1. Check error message in test output
2. Review detailed logs (use -v -s flags)
3. Verify API key is valid
4. Check API rate limits
5. Ensure prompts/schemas exist
6. Verify network connectivity

## Test-by-Test Checklist

### Test 1: Full Conversation Flow
- [ ] Starts conversation
- [ ] Performs 2 refinements
- [ ] Generates table structure
- [ ] Saves conversation
- [ ] Runtime: ~2-3 minutes

### Test 2: Row Expansion
- [ ] Creates initial table
- [ ] Expands rows
- [ ] Validates structure
- [ ] Merges rows
- [ ] Runtime: ~1-2 minutes

### Test 3: CSV Generation
- [ ] Generates CSV file
- [ ] Reads CSV back
- [ ] Appends rows
- [ ] Validates structure
- [ ] Runtime: ~1 minute

### Test 4: Config Generation
- [ ] Creates research table
- [ ] Generates config
- [ ] Validates structure
- [ ] Exports to file
- [ ] Runtime: ~1 minute

### Test 5: Save/Load Conversation
- [ ] Saves conversation
- [ ] Loads in new handler
- [ ] Verifies state
- [ ] Continues conversation
- [ ] Runtime: ~1-2 minutes

### Test 6: Error Handling
- [ ] Tests invalid operations
- [ ] Verifies error messages
- [ ] Handles edge cases
- [ ] Runtime: <1 minute

### Test 7: Iterative Row Expansion
- [ ] Expands in batches
- [ ] Validates all batches
- [ ] Maintains structure
- [ ] Runtime: ~3-4 minutes

## Troubleshooting

### Common Issues

#### "ANTHROPIC_API_KEY not set"
```bash
export ANTHROPIC_API_KEY="sk-ant-..."
```

#### "No module named 'src'"
```bash
cd table_maker  # Ensure you're in correct directory
```

#### "pytest: command not found"
```bash
pip install pytest pytest-asyncio
```

#### Import errors
```bash
pip install -r requirements.txt
```

#### Tests timeout
```bash
pytest --timeout=300  # Increase timeout
```

## Cost Tracking

### Estimated Costs per Run
- Full test suite: ~$0.65
- Single test: ~$0.05-$0.20
- Monitor usage in Anthropic dashboard

### Token Usage
- Varies by test
- Logged in test output
- Check token_usage in responses

## CI/CD Integration

### GitHub Actions
- [ ] Add ANTHROPIC_API_KEY to secrets
- [ ] Configure workflow file
- [ ] Set up test schedule
- [ ] Configure notifications

### Pre-commit Hook
```bash
#!/bin/bash
pytest -m integration tests/test_integration.py
```

## Documentation

### Files to Review
- [ ] INTEGRATION_TESTS_SUMMARY.md
- [ ] tests/README.md
- [ ] TESTING.md
- [ ] pytest.ini

### Understanding Tests
1. Read test docstrings
2. Review test flow comments
3. Check fixture definitions
4. Understand markers

## Final Checklist

Before considering tests complete:
- [ ] All 7 tests pass
- [ ] No warnings in output
- [ ] Documentation reviewed
- [ ] Run time acceptable
- [ ] Costs within budget
- [ ] Tests isolated (no side effects)
- [ ] Cleanup verified

## Next Steps

After successful test run:
1. [ ] Review test coverage
2. [ ] Document any issues
3. [ ] Update tests as needed
4. [ ] Integrate into CI/CD
5. [ ] Share results with team

---

**Last Updated:** 2024-10-13
**Test File:** tests/test_integration.py
**Total Tests:** 7 integration tests
**Estimated Runtime:** 10-15 minutes
**Estimated Cost:** ~$0.65 per full run
