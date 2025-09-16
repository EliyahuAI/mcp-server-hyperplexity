# Configuration and Version Management System

## Overview

The Perplexity Validator uses a sophisticated configuration and version management system that ensures data integrity, traceability, and seamless user experience across all operations.

## Configuration ID System

### Format
Configuration IDs follow the pattern: `{session_id}_v{version}_{description}`

**Example**: `session_20250916_122220_ae6db4b8_v5_Financial_portfolio_analy`

- `session_20250916_122220_ae6db4b8`: Session identifier with timestamp
- `v5`: Version number
- `Financial_portfolio_analy`: Truncated description (max 25 chars)

### Generation Process
1. **Session ID**: Created when user starts new session
2. **Version**: Auto-incremented based on existing configs in session
3. **Description**: Derived from:
   - User-provided `description` parameter
   - Config's `general_notes` field
   - First validation target column name
   - Fallback: "validation" + timestamp

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

### Multi-Strategy Lookup
When looking up configs by ID, the system uses a three-tier strategy:

#### Strategy 1: Standard Patterns
Try predefined filename patterns first:
- `config_v{version}_user.json`
- `config_v{version}_ai_generated.json`
- `config_v{version}_copied_from_previous.json`
- etc.

#### Strategy 2: Session+Name Pattern  
Search for preserved filenames with session prefix:
- Files starting with `session_id` are prioritized
- Handles copied configs with original names

#### Strategy 3: Comprehensive Search
Fallback to searching all .json files in session:
- Validates each file's `storage_metadata.config_id`
- Ensures no config is missed regardless of filename

### Validation
Every config file contains:
```json
{
  "storage_metadata": {
    "config_id": "session_20250916_122220_ae6db4b8_v5_Financial_portfolio_analy",
    "version": 5,
    "session_id": "session_20250916_122220_ae6db4b8",
    "email": "user@example.com",
    "stored_at": "2025-09-16T12:24:20.266539",
    "source": "ai_generated",
    "original_name": "MarketResearch_Config",
    "source_session": "session_20250915_143022_abc"
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

**Result**: Config IDs sent in emails are guaranteed to be findable by the lookup system.

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
- `store_config_file()`: Stores configs with metadata
- `get_config_by_id()`: Multi-strategy lookup
- `get_next_config_version()`: Version increment logic
- `copy_config_to_session()`: Preserved copying

## Monitoring and Debugging

### Log Patterns
```
[SUCCESS] Config stored: session_20250916_v5_ai_generated.json
[INFO] Found config by ID: session_20250916_v5_desc in file: session_20250915_original.json
[DEBUG] Detected versions: [1, 3, 5], next version: 6
```

### Health Indicators
- Config ID format validation
- Version increment continuity  
- Successful email→lookup roundtrips
- Results version alignment

This system ensures robust, traceable configuration management that scales with user needs while maintaining data integrity and user experience quality.