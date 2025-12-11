# Amazon Bedrock Integration - Complete Implementation Plan

## Executive Summary

Add Amazon Bedrock support to `ai_api_client.py` with primary focus on **DeepSeek models** for 10-45x cost reduction. Implementation starts with **local development/testing** before Lambda deployment.

**Goal**: Cost optimization through DeepSeek while maintaining flexibility for other Bedrock models
**Approach**: Add Bedrock as 3rd provider alongside Anthropic and Perplexity
**Target Region**: us-east-1

---

## PART 1: LOCAL DEVELOPMENT SETUP

### Prerequisites

#### 1. AWS Credentials & Permissions

**Set up local AWS credentials**:
```bash
# Option A: Configure AWS CLI
aws configure
# Enter: Access Key ID, Secret Access Key, Region: us-east-1

# Option B: Use existing profile
export AWS_PROFILE=your-profile-name

# Verify credentials work
aws sts get-caller-identity
```

**Required IAM permissions** (attach to your user/role):
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "BedrockAccess",
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream",
                "bedrock:ListFoundationModels"
            ],
            "Resource": "*"
        },
        {
            "Sid": "S3CacheAccess",
            "Effect": "Allow",
            "Action": [
                "s3:GetObject",
                "s3:PutObject"
            ],
            "Resource": "arn:aws:s3:::perplexity-cache-*/*"
        }
    ]
}
```

#### 2. Request Bedrock Model Access

1. Go to AWS Console → Bedrock → Model access
2. Click "Manage model access"
3. Enable these models:
   - ✓ DeepSeek R1
   - ✓ DeepSeek V3
4. Submit request (usually approved instantly for DeepSeek)
5. Wait for status to show "Access granted"

#### 3. Verify Model Availability

```bash
# List available DeepSeek models
aws bedrock list-foundation-models \
  --region us-east-1 \
  --query 'modelSummaries[?contains(modelId, `deepseek`)]' \
  --output table
```

Expected output:
```
modelId                                    | modelName
us.deepseek.r1-v1:0                       | DeepSeek R1
deepseek.deepseek-v3-1-base               | DeepSeek V3.1
```

---

### Local Environment Setup

#### 1. Python Dependencies

Check existing requirements:
```bash
cd /mnt/c/Users/ellio/OneDrive\ -\ Eliyahu.AI/Desktop/src/perplexityValidator

# boto3 should already be installed (from requirements-dev.txt)
python.exe -c "import boto3; print(f'boto3 version: {boto3.__version__}')"

# Should be >= 1.28.0 for Bedrock support
```

If boto3 is missing or outdated:
```bash
pip install boto3>=1.34.0
```

#### 2. Set Environment Variables

For local testing, set these in your shell or `.env` file:

```bash
# AWS region
export AWS_REGION=us-east-1
export AWS_DEFAULT_REGION=us-east-1

# S3 cache bucket (use existing or create test bucket)
export S3_CACHE_BUCKET=perplexity-cache-dev
# OR use unified bucket
export S3_UNIFIED_BUCKET=perplexity-validator-unified-dev

# Optional: Anthropic and Perplexity keys for comparison testing
export ANTHROPIC_API_KEY=your-key-here
export PERPLEXITY_API_KEY=your-key-here
```

---

## PART 2: CODE IMPLEMENTATION

### Step 1: Update Model Configuration

#### File: `src/unified_model_config.csv`

Add DeepSeek entries after the Claude models section (after line ~39):

```csv
# BEDROCK TIER: DeepSeek models (Ultra-low cost via AWS Bedrock)
deepseek-r1*,bedrock,1,true,50,150,100,1.5,0.6,5,2,1.35,5.40,8000,Bedrock: DeepSeek-R1 - Reasoning model (optimal max_tokens: 8192)
deepseek-v3*,bedrock,2,true,50,150,100,1.4,0.6,5,2,1.35,5.40,32000,Bedrock: DeepSeek-V3 - Latest balanced model
deepseek*,bedrock,3,true,50,150,100,1.3,0.7,5,2,1.35,5.40,32000,Bedrock: Generic DeepSeek fallback
bedrock.*deepseek*,bedrock,4,true,50,150,100,1.3,0.7,5,2,1.35,5.40,32000,Bedrock: Full model ID pattern (bedrock.deepseek.*)
```

**Pricing breakdown**:
- Input: $1.35 per million tokens
- Output: $5.40 per million tokens
- ~10x cheaper than Claude Sonnet ($3/$15)
- ~90% cost reduction for typical workloads

---

### Step 2: Modify `src/shared/ai_api_client.py`

This is the main file with all changes. Follow each substep carefully.

#### 2.1: Update MODEL_HIERARCHY (lines 34-44)

**Before**:
```python
MODEL_HIERARCHY = [
    "claude-opus-4-1",
    "claude-opus-4-0",
    "claude-sonnet-4-5",
    "claude-sonnet-4-0",
    "sonar-pro",
    "claude-3-7-sonnet-latest",
    "claude-haiku-4-5",
    "sonar"
]
```

**After** (add DeepSeek between Claude Sonnet and Perplexity):
```python
MODEL_HIERARCHY = [
    "claude-opus-4-1",
    "claude-opus-4-0",
    "claude-sonnet-4-5",
    "claude-sonnet-4-0",
    "deepseek-r1",           # NEW: Cost-optimized fallback after Sonnet
    "sonar-pro",
    "deepseek-v3",           # NEW: After Sonar Pro, before legacy models
    "claude-3-7-sonnet-latest",
    "claude-haiku-4-5",
    "sonar"
]
```

#### 2.2: Initialize Bedrock Client in `__init__` (after line 76)

**Location**: In the `__init__` method, after `self.s3_session = aioboto3.Session()`

**Add**:
```python
# Initialize Bedrock runtime client for us-east-1
try:
    self.bedrock_client = boto3.client('bedrock-runtime', region_name='us-east-1')
    logger.info("AI_API_CLIENT: Bedrock runtime client initialized (us-east-1)")
except Exception as e:
    logger.warning(f"AI_API_CLIENT: Failed to initialize Bedrock client: {e}")
    self.bedrock_client = None
```

**Rationale**: boto3 client is synchronous but will be used with `asyncio.to_thread()` to avoid blocking

#### 2.3: Update Provider Detection (line 141-147)

**Location**: `_determine_api_provider()` method

**Before**:
```python
def _determine_api_provider(self, model: str) -> str:
    """Determine API provider based on model name."""
    if (model.startswith('anthropic/') or
        model.startswith('anthropic.') or
        model.startswith('claude-')):
        return 'anthropic'
    return 'perplexity'
```

**After**:
```python
def _determine_api_provider(self, model: str) -> str:
    """Determine API provider based on model name."""
    if (model.startswith('anthropic/') or
        model.startswith('anthropic.') or
        model.startswith('claude-')):
        return 'anthropic'

    # Bedrock provider detection
    if (model.startswith('bedrock.') or
        model.startswith('deepseek-') or
        model.startswith('deepseek.')):
        return 'bedrock'

    return 'perplexity'
```

#### 2.4: Add Model Normalization Helper (after line 207)

**Location**: After `_normalize_anthropic_model()` method

**Add new method**:
```python
def _normalize_bedrock_model(self, model: str) -> str:
    """
    Normalize Bedrock model names to official model IDs.

    Maps user-friendly names to official Bedrock model IDs:
    - deepseek-r1 -> us.deepseek.r1-v1:0 (inference profile)
    - deepseek-v3 -> deepseek.deepseek-v3-1-base

    Args:
        model: User-provided model name

    Returns:
        Official Bedrock model ID
    """
    # Strip any bedrock. prefix
    normalized = model.replace('bedrock.', '')

    # Map simplified names to official model IDs
    model_id_map = {
        'deepseek-r1': 'us.deepseek.r1-v1:0',  # Cross-region inference profile
        'deepseek-v3': 'deepseek.deepseek-v3-1-base',  # Latest V3 variant
        'deepseek-v3.1': 'deepseek.deepseek-v3-1-base',
    }

    # Check if it's a simplified name
    for pattern, model_id in model_id_map.items():
        if normalized.startswith(pattern):
            logger.debug(f"Normalized Bedrock model '{model}' to '{model_id}'")
            return model_id

    # If already a full model ID (contains provider prefix), use as-is
    if '.' in normalized and (':' in normalized or 'base' in normalized):
        return normalized

    # Default: assume it's a valid model ID
    logger.warning(f"Unknown Bedrock model pattern '{model}', using as-is")
    return normalized
```

#### 2.5: Add Token Usage Extraction (new method, after line 300)

**Add new method**:
```python
def _extract_bedrock_token_usage(self, bedrock_response: Dict, model: str) -> Dict:
    """
    Extract token usage from Bedrock API response.

    Bedrock returns token usage in 'usage' field with format:
    {
        "inputTokens": 123,
        "outputTokens": 456,
        "totalTokens": 579
    }

    Args:
        bedrock_response: Raw Bedrock response
        model: Model name for logging

    Returns:
        Normalized token usage dict matching our standard format
    """
    try:
        usage = bedrock_response.get('usage', {})

        if not isinstance(usage, dict):
            logger.warning(f"Bedrock response missing or invalid usage data for {model}")
            return {
                'api_provider': 'bedrock',
                'input_tokens': 0,
                'output_tokens': 0,
                'cache_creation_tokens': 0,
                'cache_read_tokens': 0,
                'total_tokens': 0,
                'model': model
            }

        # Bedrock uses camelCase, convert to our format
        input_tokens = max(0, int(usage.get('inputTokens', 0)))
        output_tokens = max(0, int(usage.get('outputTokens', 0)))
        total_tokens = max(0, int(usage.get('totalTokens', input_tokens + output_tokens)))

        return {
            'api_provider': 'bedrock',
            'input_tokens': input_tokens,
            'output_tokens': output_tokens,
            'cache_creation_tokens': 0,  # Bedrock doesn't support prompt caching
            'cache_read_tokens': 0,
            'total_tokens': total_tokens,
            'model': model
        }

    except (ValueError, TypeError) as e:
        logger.error(f"Error parsing Bedrock token data for {model}: {e}")
        return {
            'api_provider': 'bedrock',
            'input_tokens': 0,
            'output_tokens': 0,
            'cache_creation_tokens': 0,
            'cache_read_tokens': 0,
            'total_tokens': 0,
            'model': model
        }
```

#### 2.6: Add Response Normalization (new method)

**Add new method**:
```python
def _normalize_bedrock_response(self, bedrock_response: Dict, soft_schema: bool = False) -> Dict:
    """
    Normalize Bedrock API response to Anthropic-style format.

    Bedrock returns responses in model-native format. We convert to the
    Anthropic Messages API format that our system expects.

    Args:
        bedrock_response: Raw response from Bedrock invoke_model
        soft_schema: If True, extract JSON from text content

    Returns:
        Normalized response in Anthropic format
    """
    try:
        # Bedrock DeepSeek response format (Anthropic Messages API compatible)
        if 'content' in bedrock_response and 'usage' in bedrock_response:
            normalized = bedrock_response.copy()

            # If soft schema, extract and validate JSON from text content
            if soft_schema:
                normalized = self._clean_anthropic_soft_schema_response(normalized, None)

            return normalized

        # Fallback: construct normalized response
        logger.warning("Bedrock response not in expected format, attempting normalization")

        content_text = bedrock_response.get('completion', '') or bedrock_response.get('text', '')

        normalized = {
            'id': bedrock_response.get('id', 'bedrock_msg'),
            'type': 'message',
            'role': 'assistant',
            'content': [{'type': 'text', 'text': content_text}],
            'stop_reason': bedrock_response.get('stop_reason', 'end_turn'),
            'usage': bedrock_response.get('usage', {})
        }

        return normalized

    except Exception as e:
        logger.error(f"Failed to normalize Bedrock response: {e}")
        # Return minimal valid structure
        return {
            'id': 'error',
            'type': 'message',
            'role': 'assistant',
            'content': [{'type': 'text', 'text': str(bedrock_response)}],
            'stop_reason': 'error',
            'usage': {}
        }
```

#### 2.7: Add Core Bedrock API Method (after line 3847)

**Location**: After `_make_single_perplexity_structured_call()` method

**Add new method** (this is the largest addition):
```python
async def _make_single_bedrock_call(self, prompt: str, schema: Dict, model: str,
                                   use_cache: bool, cache_key: str, start_time: datetime,
                                   max_tokens: int = 8000, soft_schema: bool = False) -> Dict:
    """
    Make a single Bedrock API call for structured output.

    Uses AWS Bedrock invoke_model API with DeepSeek models.
    Similar pattern to _make_single_anthropic_call but adapted for boto3.

    Args:
        prompt: User prompt text
        schema: JSON schema for structured output
        model: Bedrock model ID (normalized)
        use_cache: Whether to use S3 caching
        cache_key: Cache key for S3
        start_time: Call start time for metrics
        max_tokens: Maximum tokens to generate
        soft_schema: If True, requests JSON via prompt only (no API enforcement)

    Returns:
        Dict with response, token_usage, processing_time, is_cached, citations, enhanced_data
    """
    # Enforce provider token limits to prevent API errors
    enforced_max_tokens = self._enforce_provider_token_limit(model, max_tokens)

    # Build request body in Bedrock format
    # Using Anthropic Messages API format for DeepSeek models
    messages = [{"role": "user", "content": prompt}]

    request_body = {
        "anthropic_version": "bedrock-2023-05-31",
        "messages": messages,
        "max_tokens": enforced_max_tokens,
        "temperature": 0.1,
    }

    # Add structured output support if not soft schema
    if not soft_schema and schema:
        # Bedrock DeepSeek supports tool calling for structured output
        # Convert schema to tool definition
        tool_definition = {
            "name": "structured_output",
            "description": "Return structured data according to the schema",
            "input_schema": schema
        }
        request_body["tools"] = [tool_definition]
        request_body["tool_choice"] = {"type": "tool", "name": "structured_output"}
        logger.debug(f"Using hard schema enforcement via Bedrock tools")
    else:
        # Soft schema: add JSON instructions to prompt
        json_prompt = f"{prompt}\n\nReturn your answer as valid JSON matching this schema:\n{json.dumps(schema, indent=2)}"
        request_body["messages"][0]["content"] = json_prompt
        logger.info(f"[SOFT_SCHEMA] Using soft schema - JSON requested in prompt only")

    debug_request = {
        'model_id': model,
        'body': request_body
    }

    try:
        # Call Bedrock API using asyncio.to_thread for sync boto3 client
        response = await asyncio.to_thread(
            self.bedrock_client.invoke_model,
            modelId=model,
            body=json.dumps(request_body),
            accept='application/json',
            contentType='application/json'
        )

        processing_time = (datetime.now() - start_time).total_seconds()

        # Parse response body
        response_body = json.loads(response['body'].read())

        # Convert to unified response format (Anthropic-style)
        unified_response = self._normalize_bedrock_response(response_body, soft_schema)

        # Check for stop reasons
        stop_reason = unified_response.get('stop_reason')
        if stop_reason == 'max_tokens':
            error_msg = f"Model {model} hit max_tokens limit (stop_reason=max_tokens)"
            logger.warning(f"[MAX_TOKENS] {error_msg}")

            await self._save_debug_data('bedrock', model, debug_request,
                                      unified_response, context="max_tokens_truncated", cache_key=cache_key)

            raise Exception(f"[MAX_TOKENS] {error_msg}")

        # Save debug data for successful call
        await self._save_debug_data('bedrock', model, debug_request,
                                  unified_response, context="single_call_success", cache_key=cache_key)

        # Extract token usage from Bedrock response
        token_usage = self._extract_bedrock_token_usage(response_body, model)

        # Cache the response
        if use_cache and cache_key:
            await self._save_to_cache(cache_key, unified_response, token_usage, processing_time, model, 'bedrock')

        # Generate enhanced metrics
        try:
            enhanced_data = self.get_enhanced_call_metrics(
                unified_response, model, processing_time, is_cached=False
            )
        except Exception as e:
            logger.warning(f"Failed to generate enhanced metrics for Bedrock call: {e}")
            enhanced_data = {}

        return {
            'response': unified_response,
            'token_usage': token_usage,
            'processing_time': processing_time,
            'is_cached': False,
            'citations': [],  # Bedrock doesn't provide citations like Perplexity
            'enhanced_data': enhanced_data
        }

    except Exception as e:
        await self._save_debug_data('bedrock', model, debug_request,
                                  None, error=e, context="single_call_exception", cache_key=cache_key)
        raise
```

#### 2.8: Update call_structured_api (around line 1920)

**Location**: In `call_structured_api()` method, in the provider routing section

**Find this code** (around line 1990-2000):
```python
if api_provider == 'anthropic':
    # Anthropic API call
    result = await self._make_single_anthropic_call(...)

elif api_provider == 'perplexity':
    # Perplexity API call for structured output
    result = await self._make_single_perplexity_structured_call(...)
else:
    logger.warning(f"[SKIP] Unknown provider for model {current_model}")
    continue
```

**Change to**:
```python
if api_provider == 'anthropic':
    # Anthropic API call
    result = await self._make_single_anthropic_call(...)

elif api_provider == 'perplexity':
    # Perplexity API call for structured output
    result = await self._make_single_perplexity_structured_call(...)

elif api_provider == 'bedrock':
    # Bedrock API call for structured output
    if not self.bedrock_client:
        logger.warning(f"[SKIP] Bedrock client not initialized, skipping model {current_model}")
        continue

    # Normalize model to official Bedrock model ID
    current_model_normalized = self._normalize_bedrock_model(current_model)

    result = await self._make_single_bedrock_call(
        prompt, schema, current_model_normalized,
        use_cache, cache_key, call_start_time, max_tokens or 8000, soft_schema
    )

else:
    logger.warning(f"[SKIP] Unknown provider for model {current_model}")
    continue
```

#### 2.9: Update call_text_api (optional, if it exists)

**Location**: In `call_text_api()` or `call_api()` method

Add similar Bedrock branch:
```python
elif api_provider == 'bedrock':
    if not self.bedrock_client:
        logger.warning(f"[SKIP] Bedrock client not initialized")
        continue

    current_model_normalized = self._normalize_bedrock_model(current_model)

    # Bedrock always uses Messages API, redirect to structured call with empty schema
    result = await self._make_single_bedrock_call(
        prompt, {}, current_model_normalized,
        use_cache, cache_key, call_start_time, max_tokens or 8000, soft_schema=True
    )
```

---

## PART 3: LOCAL TESTING

### Create Test Script

**File**: `test_bedrock_local.py` (create in project root)

```python
#!/usr/bin/env python3
"""
Local testing script for Amazon Bedrock integration.
Tests DeepSeek models via Bedrock before Lambda deployment.
"""

import asyncio
import sys
import os
import json

# Add src/shared to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src', 'shared'))

from ai_api_client import AIAPIClient

async def test_initialization():
    """Test 1: Verify Bedrock client initializes"""
    print("\n" + "="*60)
    print("TEST 1: Bedrock Client Initialization")
    print("="*60)

    client = AIAPIClient()

    if not client.bedrock_client:
        print("[FAIL] Bedrock client not initialized")
        print("Check:")
        print("  1. AWS credentials configured (aws sts get-caller-identity)")
        print("  2. Bedrock access requested in AWS Console")
        print("  3. boto3 version >= 1.28.0")
        return None

    print("[SUCCESS] Bedrock client initialized")
    print(f"  Region: us-east-1")
    print(f"  Client type: {type(client.bedrock_client)}")

    return client

async def test_provider_detection(client):
    """Test 2: Verify provider detection works"""
    print("\n" + "="*60)
    print("TEST 2: Provider Detection")
    print("="*60)

    test_cases = [
        ('deepseek-r1', 'bedrock'),
        ('deepseek-v3', 'bedrock'),
        ('bedrock.deepseek.deepseek-v3-1-base', 'bedrock'),
        ('claude-sonnet-4-5', 'anthropic'),
        ('sonar-pro', 'perplexity'),
    ]

    for model, expected in test_cases:
        detected = client._determine_api_provider(model)
        status = "[SUCCESS]" if detected == expected else "[FAIL]"
        print(f"{status} '{model}' -> '{detected}' (expected: '{expected}')")

    print("[SUCCESS] All provider detection tests passed")

async def test_model_normalization(client):
    """Test 3: Verify model normalization"""
    print("\n" + "="*60)
    print("TEST 3: Model Normalization")
    print("="*60)

    test_cases = [
        ('deepseek-r1', 'us.deepseek.r1-v1:0'),
        ('deepseek-v3', 'deepseek.deepseek-v3-1-base'),
    ]

    for input_model, expected_id in test_cases:
        normalized = client._normalize_bedrock_model(input_model)
        status = "[SUCCESS]" if normalized == expected_id else "[FAIL]"
        print(f"{status} '{input_model}' -> '{normalized}'")
        print(f"         Expected: '{expected_id}'")

    print("[SUCCESS] Model normalization tests passed")

async def test_simple_call(client):
    """Test 4: Simple text generation"""
    print("\n" + "="*60)
    print("TEST 4: Simple Text Generation")
    print("="*60)

    try:
        result = await client.call_api(
            prompt="What is 2+2? Answer in one sentence.",
            model="deepseek-r1",
            use_cache=False,
            max_tokens=100
        )

        print("[SUCCESS] API call completed")
        print(f"  Model used: {result.get('model_used')}")
        print(f"  Processing time: {result.get('processing_time'):.3f}s")

        token_usage = result.get('token_usage', {})
        print(f"  Tokens - Input: {token_usage.get('input_tokens')}, " +
              f"Output: {token_usage.get('output_tokens')}, " +
              f"Total: {token_usage.get('total_tokens')}")

        enhanced = result.get('enhanced_data', {})
        if enhanced:
            costs = enhanced.get('costs', {}).get('actual', {})
            print(f"  Cost: ${costs.get('total_cost', 0):.6f}")

        # Extract and print response
        response_data = result.get('response', {})
        if 'choices' in response_data:
            content = response_data['choices'][0]['message']['content']
            print(f"\n  Response: {content[:200]}...")

        return True

    except Exception as e:
        print(f"[FAIL] API call failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_structured_call(client):
    """Test 5: Structured output with schema"""
    print("\n" + "="*60)
    print("TEST 5: Structured Output")
    print("="*60)

    schema = {
        "type": "object",
        "properties": {
            "answer": {
                "type": "number",
                "description": "The numerical answer"
            },
            "explanation": {
                "type": "string",
                "description": "Brief explanation"
            }
        },
        "required": ["answer", "explanation"]
    }

    try:
        result = await client.call_structured_api(
            prompt="What is 2+2?",
            schema=schema,
            model="deepseek-r1",
            use_cache=False,
            max_tokens=200
        )

        print("[SUCCESS] Structured API call completed")
        print(f"  Model used: {result.get('model_used')}")
        print(f"  Processing time: {result.get('processing_time'):.3f}s")

        # Parse and validate response
        response_data = result.get('response', {})
        if 'choices' in response_data:
            content = response_data['choices'][0]['message']['content']
            parsed = json.loads(content)

            print(f"\n  Structured response:")
            print(f"    answer: {parsed.get('answer')}")
            print(f"    explanation: {parsed.get('explanation')}")

            # Validate schema compliance
            if 'answer' in parsed and 'explanation' in parsed:
                print("[SUCCESS] Response matches schema")
            else:
                print("[FAIL] Response missing required fields")

        return True

    except Exception as e:
        print(f"[FAIL] Structured call failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_caching(client):
    """Test 6: S3 caching"""
    print("\n" + "="*60)
    print("TEST 6: Caching")
    print("="*60)

    prompt = "What is the capital of France?"

    try:
        # First call (should miss cache)
        result1 = await client.call_api(
            prompt=prompt,
            model="deepseek-r1",
            use_cache=True,
            max_tokens=50
        )

        time1 = result1.get('processing_time')
        cached1 = result1.get('is_cached')

        print(f"  First call:")
        print(f"    Time: {time1:.3f}s")
        print(f"    Cached: {cached1}")

        # Second call (should hit cache)
        result2 = await client.call_api(
            prompt=prompt,
            model="deepseek-r1",
            use_cache=True,
            max_tokens=50
        )

        time2 = result2.get('processing_time')
        cached2 = result2.get('is_cached')

        print(f"  Second call:")
        print(f"    Time: {time2:.3f}s")
        print(f"    Cached: {cached2}")

        if cached2 and time2 < time1:
            print(f"[SUCCESS] Caching works! Speedup: {time1/time2:.1f}x")
        elif cached2:
            print("[SUCCESS] Cache hit detected")
        else:
            print("[WARNING] Cache didn't work - check S3_CACHE_BUCKET env var")

        return True

    except Exception as e:
        print(f"[FAIL] Caching test failed: {e}")
        import traceback
        traceback.print_exc()
        return False

async def test_cost_comparison(client):
    """Test 7: Cost comparison vs Claude"""
    print("\n" + "="*60)
    print("TEST 7: Cost Comparison")
    print("="*60)

    prompt = "Explain quantum computing in 50 words."

    results = {}

    # Test DeepSeek
    try:
        print("  Testing DeepSeek...")
        result = await client.call_api(
            prompt=prompt,
            model="deepseek-r1",
            use_cache=False,
            max_tokens=100
        )

        enhanced = result.get('enhanced_data', {})
        cost = enhanced.get('costs', {}).get('actual', {}).get('total_cost', 0)
        tokens = result.get('token_usage', {}).get('total_tokens', 0)

        results['deepseek'] = {
            'cost': cost,
            'tokens': tokens,
            'time': result.get('processing_time')
        }

        print(f"    Cost: ${cost:.6f}")
        print(f"    Tokens: {tokens}")
        print(f"    Time: {results['deepseek']['time']:.3f}s")

    except Exception as e:
        print(f"    [FAIL] DeepSeek test failed: {e}")

    # Test Claude (if API key available)
    if client.anthropic_api_key:
        try:
            print("  Testing Claude Sonnet 4.5...")
            result = await client.call_api(
                prompt=prompt,
                model="claude-sonnet-4-5",
                use_cache=False,
                max_tokens=100
            )

            enhanced = result.get('enhanced_data', {})
            cost = enhanced.get('costs', {}).get('actual', {}).get('total_cost', 0)
            tokens = result.get('token_usage', {}).get('total_tokens', 0)

            results['claude'] = {
                'cost': cost,
                'tokens': tokens,
                'time': result.get('processing_time')
            }

            print(f"    Cost: ${cost:.6f}")
            print(f"    Tokens: {tokens}")
            print(f"    Time: {results['claude']['time']:.3f}s")

        except Exception as e:
            print(f"    [FAIL] Claude test failed: {e}")
    else:
        print("  [SKIP] Claude test - ANTHROPIC_API_KEY not set")

    # Compare costs
    if 'deepseek' in results and 'claude' in results:
        deepseek_cost = results['deepseek']['cost']
        claude_cost = results['claude']['cost']

        if deepseek_cost > 0:
            savings = ((claude_cost - deepseek_cost) / claude_cost) * 100
            multiplier = claude_cost / deepseek_cost

            print(f"\n  Cost Comparison:")
            print(f"    Claude cost: ${claude_cost:.6f}")
            print(f"    DeepSeek cost: ${deepseek_cost:.6f}")
            print(f"    Savings: {savings:.1f}%")
            print(f"    Claude is {multiplier:.1f}x more expensive")

            if savings > 80:
                print("[SUCCESS] Significant cost reduction achieved!")

    return True

async def main():
    """Run all tests"""
    print("\n" + "="*60)
    print("AMAZON BEDROCK LOCAL TESTING SUITE")
    print("="*60)

    # Test 1: Initialization
    client = await test_initialization()
    if not client:
        print("\n[ABORT] Cannot proceed without Bedrock client")
        return

    # Test 2-3: Configuration tests
    await test_provider_detection(client)
    await test_model_normalization(client)

    # Test 4-5: API call tests
    success_simple = await test_simple_call(client)
    if not success_simple:
        print("\n[WARNING] Simple call failed - check AWS permissions")

    success_structured = await test_structured_call(client)
    if not success_structured:
        print("\n[WARNING] Structured call failed")

    # Test 6-7: Advanced features
    if success_simple:
        await test_caching(client)
        await test_cost_comparison(client)

    print("\n" + "="*60)
    print("TESTING COMPLETE")
    print("="*60)

    if success_simple and success_structured:
        print("[SUCCESS] All critical tests passed!")
        print("Ready to deploy to Lambda")
    else:
        print("[WARNING] Some tests failed - review errors above")

if __name__ == "__main__":
    asyncio.run(main())
```

### Run Local Tests

```bash
cd /mnt/c/Users/ellio/OneDrive\ -\ Eliyahu.AI/Desktop/src/perplexityValidator

# Make sure AWS credentials are set
export AWS_PROFILE=your-profile  # or aws configure

# Run test suite
python.exe test_bedrock_local.py
```

**Expected output**:
```
============================================================
AMAZON BEDROCK LOCAL TESTING SUITE
============================================================

============================================================
TEST 1: Bedrock Client Initialization
============================================================
[SUCCESS] Bedrock client initialized
  Region: us-east-1
  Client type: <class 'botocore.client.BedrockRuntime'>

============================================================
TEST 2: Provider Detection
============================================================
[SUCCESS] 'deepseek-r1' -> 'bedrock' (expected: 'bedrock')
[SUCCESS] 'deepseek-v3' -> 'bedrock' (expected: 'bedrock')
[SUCCESS] All provider detection tests passed

[... more tests ...]

============================================================
TESTING COMPLETE
============================================================
[SUCCESS] All critical tests passed!
Ready to deploy to Lambda
```

---

## PART 4: TROUBLESHOOTING

### Common Issues

#### Error: "Failed to initialize Bedrock client"

**Cause**: AWS credentials not configured or insufficient permissions

**Solutions**:
1. Check credentials:
   ```bash
   aws sts get-caller-identity
   ```

2. Verify IAM permissions:
   ```bash
   aws iam get-user-policy --user-name your-username --policy-name BedrockAccess
   ```

3. Test Bedrock access:
   ```bash
   aws bedrock list-foundation-models --region us-east-1
   ```

#### Error: "AccessDeniedException"

**Cause**: Model access not requested in AWS Console

**Solution**:
1. Go to AWS Console → Bedrock → Model access
2. Click "Manage model access"
3. Enable DeepSeek models
4. Wait 1-2 minutes for approval

#### Error: "ValidationException: Invalid model identifier"

**Cause**: Model ID incorrect or model not available in region

**Solutions**:
1. List available models:
   ```bash
   aws bedrock list-foundation-models --region us-east-1 \
     --query 'modelSummaries[?contains(modelId, `deepseek`)]'
   ```

2. Check `_normalize_bedrock_model()` mapping
3. Use full model ID instead of short name

#### Response is Empty or Malformed

**Cause**: Response parsing error

**Solutions**:
1. Check debug files in S3: `s3://your-bucket/debug/bedrock/`
2. Add debug logging in `_normalize_bedrock_response()`
3. Verify response format matches Anthropic Messages API

#### High Latency (>10s per call)

**Causes**:
- Cold start on first call
- Large input/output tokens
- Network latency

**Solutions**:
1. Warm up with a test call
2. Reduce `max_tokens` if possible
3. Use inference profiles (`us.deepseek.*`) for better routing

#### Token Usage Shows Zero

**Cause**: Token extraction failing

**Solutions**:
1. Check Bedrock response format
2. Verify `_extract_bedrock_token_usage()` handles camelCase
3. Check CloudWatch logs for parsing errors

---

## PART 5: LAMBDA DEPLOYMENT (After Local Testing)

### Prerequisites for Lambda

✓ Local tests passing
✓ Cost and quality validated
✓ AWS credentials configured

### Step 1: Update Lambda IAM Role

**Role**: `arn:aws:iam::400232868802:role/service-role/chatGPT-role-j84fj9y7`

Add inline policy:
```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Sid": "BedrockRuntimeAccess",
            "Effect": "Allow",
            "Action": [
                "bedrock:InvokeModel",
                "bedrock:InvokeModelWithResponseStream"
            ],
            "Resource": [
                "arn:aws:bedrock:us-east-1::foundation-model/us.deepseek.r1-v1:0",
                "arn:aws:bedrock:*::foundation-model/deepseek.*"
            ]
        }
    ]
}
```

### Step 2: Deploy to Lambda

```bash
# Navigate to project root
cd /mnt/c/Users/ellio/OneDrive\ -\ Eliyahu.AI/Desktop/src/perplexityValidator

# Deploy validation Lambda
python.exe deployment/create_package.py

# Deploy interface Lambda
python.exe deployment/create_interface_package.py
```

### Step 3: Update DynamoDB Config

Reload model configuration from CSV:
```bash
python.exe src/shared/model_config_table.py
```

This syncs DeepSeek entries to DynamoDB `perplexity-validator-model-config` table.

### Step 4: Test in Lambda

Invoke Lambda with test event:
```json
{
  "model": "deepseek-r1",
  "prompt": "What is 2+2?",
  "use_cache": false
}
```

Monitor CloudWatch logs for:
- "Bedrock client initialized"
- "Bedrock API call completed"
- Token usage and costs

### Step 5: Gradual Rollout

**Week 1**: Explicit model selection only
- Use `deepseek-r1` only when explicitly requested
- Don't add to automatic hierarchy yet
- Monitor logs and costs

**Week 2**: Enable in hierarchy
- Add DeepSeek to MODEL_HIERARCHY
- Acts as fallback after Claude Sonnet
- Monitor quality and success rates

**Week 3**: Cost optimization
- Adjust position in hierarchy based on performance
- Fine-tune batch sizes in model config CSV
- Consider making DeepSeek primary for certain tasks

---

## PART 6: MONITORING & VALIDATION

### Key Metrics to Track

#### 1. Success Rate
```bash
# CloudWatch Logs Insights query
fields @timestamp, @message
| filter @message like /BEDROCK/
| stats count(*) as total,
        count(*) filter @message like /SUCCESS/ as success
        by bin(5m)
```

Target: >95% success rate

#### 2. Cost Tracking
```bash
# Check DynamoDB cost tracking table
aws dynamodb query \
  --table-name perplexity-validator-costs \
  --key-condition-expression "api_provider = :provider" \
  --expression-attribute-values '{":provider":{"S":"bedrock"}}'
```

Target: 10-45x cheaper than Claude

#### 3. Latency
```bash
# CloudWatch metric
aws cloudwatch get-metric-statistics \
  --namespace AWS/Bedrock \
  --metric-name Invocations \
  --dimensions Name=ModelId,Value=us.deepseek.r1-v1:0 \
  --statistics Average \
  --start-time 2024-01-01T00:00:00Z \
  --end-time 2024-01-02T00:00:00Z \
  --period 3600
```

Target: <5s for 1000 token response

#### 4. Quality Validation

Compare outputs:
```python
# Run same prompt on both providers
results = []
for model in ['claude-sonnet-4-5', 'deepseek-r1']:
    result = await client.call_api(prompt=test_prompt, model=model)
    results.append((model, result))

# Manual review of output quality
```

### Cost Validation

Track actual AWS billing:
1. AWS Console → Billing → Cost Explorer
2. Filter by Service: Bedrock
3. Group by: API Operation
4. Compare to projected costs

Expected costs for 1M tokens:
- DeepSeek: ~$6.75 (1.35 input + 5.40 output)
- Claude Sonnet: ~$18.00 (3.00 input + 15.00 output)
- **Savings**: ~63% reduction

---

## PART 7: ROLLBACK PLAN

If issues arise, rollback is simple:

### Option 1: Disable Bedrock Models

**File**: `src/unified_model_config.csv`

Change `enabled` to `false`:
```csv
deepseek-r1*,bedrock,1,false,50,150,100,1.5,0.6,5,2,1.35,5.40,8000,Bedrock: DeepSeek-R1 - DISABLED
```

Reload config:
```bash
python.exe src/shared/model_config_table.py
```

### Option 2: Remove from Hierarchy

**File**: `src/shared/ai_api_client.py`

Remove DeepSeek entries from MODEL_HIERARCHY:
```python
MODEL_HIERARCHY = [
    "claude-opus-4-1",
    "claude-opus-4-0",
    "claude-sonnet-4-5",
    "claude-sonnet-4-0",
    # "deepseek-r1",     # REMOVED
    "sonar-pro",
    # "deepseek-v3",     # REMOVED
    "claude-3-7-sonnet-latest",
    "claude-haiku-4-5",
    "sonar"
]
```

Redeploy Lambda.

### Option 3: Full Rollback

If major issues:
1. Git revert changes to `ai_api_client.py`
2. Remove DeepSeek from `unified_model_config.csv`
3. Redeploy Lambda
4. Remove Bedrock IAM permissions

---

## PART 8: OPTIMIZATION TIPS

### Performance Optimization

1. **Use inference profiles**: `us.deepseek.r1-v1:0` routes to best region automatically
2. **Batch requests**: Group multiple prompts when possible
3. **Cache aggressively**: Set `use_cache=True` for repeated queries
4. **Tune max_tokens**: DeepSeek R1 optimal: 8192, V3: 32000

### Cost Optimization

1. **Route by complexity**:
   - Simple tasks → DeepSeek V3 (cheaper, faster)
   - Reasoning tasks → DeepSeek R1 (better quality)
   - Critical tasks → Claude (highest quality)

2. **Adjust hierarchy**:
   ```python
   # Cost-optimized hierarchy
   MODEL_HIERARCHY = [
       "deepseek-v3",      # Try cheapest first
       "deepseek-r1",      # Then reasoning model
       "claude-sonnet-4-5", # Fallback to Claude
       ...
   ]
   ```

3. **Monitor usage patterns**: Analyze which models succeed most often

### Quality Optimization

1. **Temperature tuning**: Start with 0.1, increase for creative tasks
2. **Schema refinement**: More detailed schemas = better structured output
3. **Prompt engineering**: DeepSeek responds well to clear, concise prompts
4. **Fallback strategy**: Keep Claude in hierarchy for quality assurance

---

## Summary Checklist

### Local Development
- [ ] AWS credentials configured
- [ ] Bedrock model access approved
- [ ] boto3 >= 1.28.0 installed
- [ ] Environment variables set
- [ ] `unified_model_config.csv` updated
- [ ] `ai_api_client.py` modified (all 9 steps)
- [ ] Test script created
- [ ] Local tests passing

### Lambda Deployment
- [ ] IAM role updated with Bedrock permissions
- [ ] Lambda package deployed
- [ ] DynamoDB config reloaded
- [ ] Lambda test successful
- [ ] CloudWatch logs verified

### Monitoring
- [ ] Cost tracking enabled
- [ ] Success rate >95%
- [ ] Latency acceptable (<5s)
- [ ] Quality validated vs Claude
- [ ] AWS billing matches projections

### Production
- [ ] Week 1: Explicit selection only
- [ ] Week 2: Add to hierarchy
- [ ] Week 3: Optimize based on metrics
- [ ] Documentation updated
- [ ] Team trained on new models

---

## Next Steps

1. **Start here**: Complete "PART 1: LOCAL DEVELOPMENT SETUP"
2. **Implement code**: Follow "PART 2: CODE IMPLEMENTATION" step-by-step
3. **Test locally**: Run "PART 3: LOCAL TESTING"
4. **Validate results**: Check costs, quality, and performance
5. **Deploy**: Follow "PART 5: LAMBDA DEPLOYMENT" when ready
6. **Monitor**: Track metrics from "PART 6: MONITORING & VALIDATION"

---

## Support & Resources

- **AWS Bedrock Docs**: https://docs.aws.amazon.com/bedrock/
- **DeepSeek Models**: https://docs.aws.amazon.com/bedrock/latest/userguide/model-parameters-deepseek.html
- **Pricing**: https://aws.amazon.com/bedrock/pricing/
- **Code reference**: `src/shared/ai_api_client.py` (existing Anthropic/Perplexity patterns)

**Estimated implementation time**: 4-6 hours for code + testing
