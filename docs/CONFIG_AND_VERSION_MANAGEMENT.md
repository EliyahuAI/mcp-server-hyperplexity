# Configuration and Version Management System

## Overview

The Perplexity Validator uses a sophisticated configuration and version management system that ensures data integrity, traceability, and seamless user experience across all operations. The system has been optimized for performance with whitelist-based filtering and early termination on perfect matches.

## Configuration ID System

### Clean Format (Current)
Configuration IDs now follow the simplified pattern: `{session_id}_{filename_without_extension}`

**Example**: `session_20250918_150921_ea332116_config_v1_ai_generated`

- `session_20250918_150921_ea332116`: Session identifier with timestamp (32 chars)
- `config_v1_ai_generated`: Original filename without .json extension

### Legacy Format (Deprecated)
Old configuration IDs followed: `{session_id}_v{version}_{description}`

**Example**: `session_20250916_122220_ae6db4b8_v5_Financial_portfolio_analy`

The system maintains backward compatibility with legacy formats for existing configurations.

### Generation Process
1. **Session ID**: Created when user starts new session (fixed 32-character format)
2. **Direct Path Construction**: Config ID directly maps to S3 path for efficient lookup
3. **No Complex Parsing**: Eliminates multi-strategy searches and version parsing

## File Naming Conventions

### Standard Config Files
- **AI Generated**: `config_v{N}_ai_generated.json`
- **User Upload**: `config_v{N}_user.json`  
- **Copied**: `config_v{N}_copied_from_previous.json`
- **Used by ID**: `config_v{N}_used_by_id.json`

### Preserved Original Filenames
When copying configs with preserved names:
- **Format**: `{source_session}_{original_name}.json`
- **Example**: `session_20250915_143022_abc_MarketResearch_Config.json`

This ensures traceability while avoiding filename conflicts.

## Version Detection and Increment

### Multi-Pattern Version Detection
The system detects version numbers from multiple filename patterns:

```python
patterns = [
    r'config_v(\d+)_',      # config_v5_ai_generated.json
    r'_v(\d+)_',            # session_20250916_v5_something.json  
    r'_v(\d+)\.json$',      # filename_v5.json
    r'config_v(\d+)\.json$' # config_v5.json
]
```

### Version Increment Logic
1. **Scan Session**: List all .json files in session directory
2. **Extract Versions**: Apply all patterns to find version numbers
3. **Find Maximum**: Get highest existing version number
4. **Increment**: Next version = max + 1

This ensures version continuity regardless of filename format.

## Configuration Lookup System

### Optimized Direct Lookup (Current)
The system now uses a clean, direct lookup approach:

1. **Parse Config ID**: Extract session ID (first 32 chars) and filename from config ID
2. **Direct Path Construction**: Build S3 path directly: `results/{domain}/{email_prefix}/{session_id}/{filename}.json`
3. **Single S3 Call**: No complex searches or multiple strategies needed
4. **Fallback for Copied Configs**: Uses `_config_v` marker for version parsing when needed

**Example**:
```
Config ID: session_20250918_150921_ea332116_config_v1_ai_generated
S3 Path:   results/company.com/john/session_20250918_150921_ea332116/config_v1_ai_generated.json
```

### Legacy Multi-Strategy Lookup (Deprecated)
The old system used a three-tier fallback strategy that has been replaced for performance:

- Strategy 1: Standard filename patterns
- Strategy 2: Session+name pattern searches  
- Strategy 3: Comprehensive file scanning

Legacy config IDs are still supported but use the optimized lookup where possible.

### Validation
Every config file contains:
```json
{
  "storage_metadata": {
    "config_id": "session_20250918_150921_ea332116_config_v1_ai_generated",
    "version": 1,
    "session_id": "session_20250918_150921_ea332116",
    "email": "user@example.com",
    "stored_at": "2025-09-18T15:09:21.266539",
    "source": "ai_generated",
    "content_hash": "a1b2c3d4e5f6..."
  }
}
```

## Email and Receipt Integration

### Config ID in Communications
- **Emails**: Include config ID for easy reuse
- **Receipts**: Print config ID as "Configuration Code"
- **Preview Notices**: Reference config ID for full processing

### Lookup Compatibility
The email system extracts config IDs from:
```python
config_id = config_data.get('storage_metadata', {}).get('config_id')
```

This matches exactly with our lookup validation:
```python
stored_config_id = config_data.get('storage_metadata', {}).get('config_id')
if stored_config_id == config_id:
    return config_data, key
```

**Result**: Config IDs sent in emails are guaranteed to be findable by the optimized direct lookup system.

## Config Matching System

### Whitelist-Based Filtering
The system now uses an optimized approach for finding matching configurations:

1. **Query Runs Table**: Get all successfully used config IDs from completed Preview/Validation runs
2. **Chronological Ordering**: Sort configs by `start_time` from runs table (most recent first)
3. **Whitelist-First Processing**: Only load configs that have been proven to work
4. **Early Termination**: Stop immediately when first perfect match (100% score) is found

### Performance Optimization
- **Typical Load**: 1-2 configs instead of 10+ for most scenarios
- **Direct S3 Access**: No complex file scanning or pattern matching
- **Smart Filtering**: Only considers configs with successful track record
- **Immediate Response**: Stops on first perfect match instead of checking all configs

### Matching Logic
```python
# Get whitelist ordered by recency
successfully_used_configs = get_successfully_used_config_ids(email)

# Process in chronological order
for config_id in successfully_used_configs:
    config_data = storage_manager.find_config_by_id(config_id, email)
    match_score = calculate_column_match_score(table_columns, config_columns)
    
    if match_score >= 1.0:  # Perfect match
        return [config]  # Early termination
```

This ensures users see only tested configurations and get instant results for perfect matches.

## Results Versioning

### Results Folder Structure
Results are stored in versioned folders:
- **Pattern**: `v{config_version}_results/`
- **Example**: `v5_results/`
- **Contents**: 
  - `validation_results.json` (full results)
  - `preview_results.json` (preview results)
  - Enhanced Excel files

### Version Alignment
Results version always matches the config version that generated them:
- Config version 5 → Results stored in `v5_results/`
- Version detection ensures proper alignment
- Latest results retrieved by highest version number

## Configuration Change Log

### Structure
Each config maintains a detailed change log:
```json
{
  "config_change_log": [
    {
      "timestamp": "2025-09-16T12:24:19.789893",
      "action": "unified_generation", 
      "session_id": "session_20250916_122220_ae6db4b8",
      "instructions": "user instructions here",
      "config_filename": "MarketResearch_Results_input_config_V05.json",
      "version": 5,
      "model_used": "claude-opus-4-1"
    }
  ]
}
```

### Filename Preservation
The change log stores the actual filename used:
- Config Lambda generates filename
- Interface Lambda preserves it in change log entries
- Provides complete audit trail of filename evolution

## File Copying Process

### Source Preservation
When copying configs between sessions:

1. **Extract Original Info**:
   - Original filename from S3 key or metadata
   - Source session ID
   - Original description

2. **Create Session-Prefixed Name**:
   ```python
   if source_session not in base_name:
       source_filename = f"{source_session}_{base_name}.json"
   ```

3. **Preserve Metadata Chain**:
   - Maintain `original_name` through copy operations
   - Track `source_session` for traceability
   - Update `usage_count` and timestamps

### Traceability Chain
```
Original: MarketResearch_Config.json
After Copy: session_20250915_143022_abc_MarketResearch_Config.json
Config ID: session_20250916_122220_ae6db4b8_v5_Financial_portfolio_analy
```

## Error Handling and Fallbacks

### Version Detection Failures
- **Default**: Start at version 1 if no versions found
- **Logging**: Warn but continue with safe defaults
- **Recovery**: System self-corrects on next operation

### Lookup Failures  
- **Multi-Strategy**: Try multiple approaches before failing
- **Comprehensive Search**: Fall back to scanning all files
- **Detailed Logging**: Track which strategy succeeded

### Filename Conflicts
- **Session Prefixes**: Prevent conflicts across sessions
- **Timestamp Suffixes**: Added when descriptions conflict
- **Uniqueness Guarantee**: Config IDs always unique within user scope

## Best Practices

### For Developers
1. **Always Use UnifiedS3Manager**: Handles all complexity automatically
2. **Preserve Original Names**: Use `preserve_original_filename` parameter
3. **Trust the Lookup**: Multi-strategy system finds configs reliably
4. **Log Appropriately**: System provides detailed operation logging

### For Users
1. **Save Config IDs**: From emails for easy reuse
2. **Use Descriptive Names**: Helps with config identification
3. **Reference Session IDs**: For troubleshooting specific operations

## System Components

### Core Files
- **unified_s3_manager.py**: Central config storage and retrieval
- **generate_config_unified.py**: Version management and storage
- **copy_config.py**: Config copying with preservation
- **email_sender.py**: Config ID distribution

### Key Functions
- `store_config_file()`: Stores configs with metadata and clean IDs
- `find_config_by_id()`: Optimized direct lookup with session parsing
- `get_successfully_used_config_ids()`: Whitelist generation from runs table
- `find_matching_configs_optimized()`: Performance-optimized config matching with early termination
- `calculate_column_match_score()`: Column matching algorithm with perfect match detection

## Monitoring and Debugging

### Log Patterns
```
[INFO] Found 15 successfully used configs for filtering
[INFO] Checking configs in order of recency, starting with: session_20250918_150921_ea332116_config_v1_ai_generated
[INFO] Config session_20250918_150921_ea332116_config_v1_ai_generated: match_score=1.000, table_cols=18, config_cols=18
[INFO] PERFECT MATCH: session_20250918_150921_ea332116_config_v1_ai_generated with score 1.000
[INFO] Stopping search after finding perfect match - processed 1 configs
```

### Health Indicators
- **Whitelist Performance**: Number of successfully used configs available
- **Early Termination**: Configs processed before finding perfect match (ideal: 1-2)
- **Direct Lookup Success**: Config IDs resolved without fallback strategies
- **Match Quality**: Percentage of perfect matches vs. partial matches

### Performance Metrics
- **Config Load Efficiency**: Typical 1-2 configs loaded vs. legacy 10+ configs
- **Response Time**: Sub-second config matching due to early termination
- **Memory Usage**: Reduced due to whitelist-first approach
- **S3 API Calls**: Minimized through direct path construction

This optimized system ensures robust, traceable configuration management that scales efficiently with user needs while maintaining data integrity and delivering instant results for perfect matches.