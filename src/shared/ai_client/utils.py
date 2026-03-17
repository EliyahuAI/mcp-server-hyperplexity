
import json
import logging
import re
from typing import Dict, List, Optional, Any
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


# OpenRouter vendor prefixes (models in the form "vendor/model-name").
# These are NOT handled by other providers, so we route them to OpenRouter.
# anthropic/ is already handled by the anthropic branch below.
_OPENROUTER_VENDOR_PREFIXES = (
    'minimax/',
    'moonshotai/',
    'mistralai/',
    'meta-llama/',
    'qwen/',
    'x-ai/',
    'nousresearch/',
    'microsoft/',
    'nvidia/',
    'cohere/',
    'openrouter/',
    'liquid/',
    'inflection/',
    'sao10k/',
    'neversleep/',
    'undi95/',
    'gryphe/',
    'thedrummer/',
    'eva-unit-01/',
    'sophosympatheia/',
    'latitudegames/',
    'anthracite-org/',
)

# OpenRouter shortform aliases — no vendor prefix, resolved to full id at call time.
_OPENROUTER_SHORTFORMS = {
    'minimax-m2.5': 'minimax/minimax-m2.5',
    'kimi-k2.5': 'moonshotai/kimi-k2.5',
}


def determine_api_provider(model: str) -> str:
    """Determine API provider based on model name."""
    if model.startswith('the-clone'):
        return 'clone'

    if (model.startswith('anthropic/') or
        model.startswith('anthropic.') or
        model.startswith('claude-')):
        return 'anthropic'

    # Gemini models (Google native via Vertex AI)
    if (model.startswith('gemini-') or
        model.startswith('gemini.') or
        model.startswith('vertex.gemini')):
        return 'gemini'

    # Vertex AI provider detection (DeepSeek MaaS)
    if (model.startswith('vertex.') or
        model.startswith('deepseek-') or
        model.startswith('deepseek.')):
        # Check for Baseten specifically
        if 'baseten' in model or 'deepseek-v3.2-baseten' in model:
            return 'baseten'
        return 'vertex'

    # OpenRouter shortform aliases (e.g. minimax-m2.5, kimi-k2.5)
    if model in _OPENROUTER_SHORTFORMS:
        return 'openrouter'

    # OpenRouter models use "vendor/model-name" format
    if any(model.startswith(prefix) for prefix in _OPENROUTER_VENDOR_PREFIXES):
        return 'openrouter'

    return 'perplexity'


def normalize_openrouter_model(model: str) -> str:
    """Expand OpenRouter shortform aliases to full vendor/model-name format."""
    return _OPENROUTER_SHORTFORMS.get(model, model)


# Thinking budget by suffix keyword — applied to gemini-3-flash-preview models only.
# Other Gemini models (2.5 Flash etc.) don't support configurable thinking budgets.
_GEMINI_THINKING_BUDGETS = {
    'min': 0,       # Thinking disabled
    'low': 1024,    # Minimal thinking
    'high': 24576,  # Maximum thinking
}
_GEMINI_THINKING_DEFAULT = 8192  # bare model name = medium thinking


def parse_gemini_thinking_suffix(model: str):
    """
    Parse thinking-level suffix from a Gemini model name.

    Suffix scheme (applied to gemini-3-flash-preview models only):
      -min  → thinkingBudget=0     (disabled)
      -low  → thinkingBudget=1024  (light)
      bare  → thinkingBudget=8192  (medium, default)
      -high → thinkingBudget=24576 (heavy)

    For all other models, returns (model, None) — no thinking config injected.
    Works on names with or without a vendor prefix:
      'gemini-3-flash-preview-high'            → ('gemini-3-flash-preview', 24576)
      'openrouter/gemini-3-flash-preview-high' → ('openrouter/gemini-3-flash-preview', 24576)
      'gemini-2.5-flash-lite'                  → ('gemini-2.5-flash-lite', None)

    Returns:
        Tuple of (base_model_name: str, thinking_budget: int | None)
    """
    if 'gemini-3-flash-preview' not in model and 'gemini-3.1-flash-lite-preview' not in model:
        return model, None

    for suffix, budget in _GEMINI_THINKING_BUDGETS.items():
        if model.endswith(f'-{suffix}'):
            base = model[:-(len(suffix) + 1)]  # strip '-{suffix}'
            return base, budget

    # No suffix → default medium thinking
    return model, _GEMINI_THINKING_DEFAULT


def normalize_anthropic_model(model: str) -> str:
    """Convert anthropic/ format to direct API format if needed."""
    if model.startswith('anthropic/'):
        model = model.replace('anthropic/', '')
    elif model.startswith('anthropic.'):
        model = model.replace('anthropic.', '').replace('-v1:0', '')

    # Normalize dots to hyphens for consistency (e.g., claude-opus-4.6 -> claude-opus-4-6)
    model = model.replace('.', '-')

    return model

def normalize_vertex_model(model: str) -> str:
    """
    Normalize Vertex AI model names to official MaaS model IDs.
    """
    # Strip any vertex. prefix
    normalized = model.replace('vertex.', '')

    # Map simplified names to official Vertex MaaS model IDs
    model_id_map = {
        'deepseek-v3.2-exp': 'deepseek-v3.2-maas',  # V3.2-Exp maps to V3.2
        'deepseek-v3.2': 'deepseek-v3.2-maas',
        'deepseek-v3.1': 'deepseek-v3.1-maas',
        'deepseek-v3': 'deepseek-v3.1-maas',  # V3 alias for V3.1
        'deepseek-r1': 'deepseek-r1-0528-maas',
    }

    # Check if it's a simplified name
    for pattern, model_id in model_id_map.items():
        if normalized.startswith(pattern):
            logger.debug(f"Normalized Vertex model '{model}' to '{model_id}'")
            return model_id

    # If already has -maas suffix, use as-is
    if normalized.endswith('-maas'):
        return normalized

    # Default: add -maas suffix if not present
    if 'deepseek' in normalized and not normalized.endswith('-maas'):
        normalized_with_maas = f"{normalized}-maas"
        logger.debug(f"Added -maas suffix: '{model}' -> '{normalized_with_maas}'")
        return normalized_with_maas

    return normalized

def extract_structured_response(response: Dict, tool_name: str = "structured_response") -> Dict:
    """Extract structured data from Claude, Perplexity, and Vertex AI formats."""
    try:
        # Check if this is unified Perplexity format (from call_structured_api)
        if 'choices' in response and isinstance(response['choices'], list) and len(response['choices']) > 0:
            message = response['choices'][0].get('message', {})
            content = message.get('content', '')
            if isinstance(content, str) and content.strip():
                # Use improved extraction with balanced brace matching
                extracted = extract_json_from_text(content)
                if extracted:
                    return extracted
                logger.warning(f"Failed to extract JSON from unified format, trying fallback")

        # Claude tool use format — check FIRST before text extraction to prevent web search
        # result snippets (embedded in text blocks) from being mistakenly parsed as the answer.
        for content_item in response.get('content', []):
            if content_item.get('type') == 'tool_use' and content_item.get('name') == tool_name:
                return content_item.get('input', {})

        # Vertex AI format (DeepSeek, etc.) — only reached if no matching tool_use block found
        if 'content' in response and isinstance(response['content'], list):
            for content_item in response['content']:
                if content_item.get('type') == 'text':
                    text = content_item.get('text', '')
                    if isinstance(text, str) and text.strip():
                        # Use improved extraction with balanced brace matching
                        extracted = extract_json_from_text(text)
                        if extracted:
                            return extracted
                        # Log preview of text to help debug extraction failures
                        text_preview = text[:200].replace('\n', ' ')
                        logger.warning(f"Failed to extract JSON from Vertex AI format. Text preview: {text_preview}...")

        # Fallback: extract from text content (original Claude format)
        for content_item in response.get('content', []):
            if content_item.get('type') == 'text':
                text = content_item.get('text', '')
                if '{' in text and '}' in text:
                    # Strip markdown code fences first
                    cleaned_text = re.sub(r'^```(?:json)?\s*|\s*```$', '', text.strip(), flags=re.MULTILINE)

                    # Find balanced JSON object
                    start = cleaned_text.find('{')
                    if start == -1:
                        continue

                    brace_count = 0
                    in_string = False
                    escape_next = False

                    for i in range(start, len(cleaned_text)):
                        char = cleaned_text[i]

                        # Handle string escaping
                        if escape_next:
                            escape_next = False
                            continue
                        if char == '\\':
                            escape_next = True
                            continue
                        if char == '"':
                            in_string = not in_string
                            continue

                        # Count braces outside strings
                        if not in_string:
                            if char == '{':
                                brace_count += 1
                            elif char == '}':
                                brace_count -= 1
                                if brace_count == 0:
                                    # Found complete JSON object
                                    end = i + 1
                                    try:
                                        return json.loads(cleaned_text[start:end])
                                    except json.JSONDecodeError:
                                        # Invalid JSON, continue searching
                                        continue

                    # Fallback: try parsing the whole cleaned text
                    try:
                        return json.loads(cleaned_text)
                    except json.JSONDecodeError:
                        pass

        # Log detailed information about the response format before raising error
        logger.error(f"[EXTRACT_ERROR] Could not extract structured response from any format")
        logger.error(f"[EXTRACT_ERROR] Response type: {type(response)}")
        if isinstance(response, dict):
            logger.error(f"[EXTRACT_ERROR] Response keys: {list(response.keys())}")
            logger.error(f"[EXTRACT_ERROR] Has 'choices': {'choices' in response}")
            logger.error(f"[EXTRACT_ERROR] Has 'content': {'content' in response}")
            if 'content' in response:
                logger.error(f"[EXTRACT_ERROR] Content type: {type(response['content'])}")
                if isinstance(response['content'], list) and response['content']:
                    logger.error(f"[EXTRACT_ERROR] First content item: {response['content'][0]}")
                    if response['content'][0].get('type') == 'text':
                        text_preview = response['content'][0].get('text', '')[:200]
                        logger.error(f"[EXTRACT_ERROR] Text preview: {text_preview}")

        raise ValueError("Could not extract structured response from response format")

    except Exception as e:
        logger.error(f"Failed to extract structured response: {str(e)}")
        logger.error(f"Response format: {type(response)}, keys: {list(response.keys()) if isinstance(response, dict) else 'N/A'}")
        raise

def extract_text_response(response: Dict) -> str:
    """Extract text content from Claude's response."""
    try:
        content = ""
        for item in response.get('content', []):
            if item.get('type') == 'text':
                content += item.get('text', '')
        return content
    except Exception as e:
        logger.error(f"Failed to extract text response: {str(e)}")
        raise

def extract_citations_from_response(response: Dict) -> List[Dict]:
    """Extract citations from Claude's web search response."""
    citations = []
    try:
        # Handle non-dict responses gracefully
        if not isinstance(response, dict):
            logger.debug(f"[CITATION_EXTRACT] Response is not a dict (type: {type(response).__name__}), skipping extraction")
            return []

        # Look for web_search_tool_result blocks (new format)
        for content_item in response.get('content', []):
            if content_item.get('type') == 'web_search_tool_result':
                tool_content = content_item.get('content', [])
                for result_item in tool_content:
                    if result_item.get('type') == 'web_search_result':
                        # Extract from Anthropic web search result
                        citation = {
                            'url': result_item.get('url', ''),
                            'title': result_item.get('title', ''),
                            'cited_text': '',  # Anthropic provides only encrypted_content (not usable)
                            'page_age': result_item.get('page_age', ''),
                            'p': result_item.get('p', '')  # Reliability score like "p85", "p50", etc.
                        }
                        citations.append(citation)
            
            # Legacy format support - tool_use blocks with web_search
            elif content_item.get('type') == 'tool_use' and content_item.get('name') == 'web_search':
                tool_result = content_item.get('input', {})
                if 'citations' in tool_result:
                    for citation in tool_result['citations']:
                        if isinstance(citation, dict):
                            citations.append({
                                'url': citation.get('url', ''),
                                'title': citation.get('title', ''),
                                'cited_text': citation.get('cited_text', ''),
                                'p': citation.get('p', '')  # Reliability score like "p85", "p50", etc.
                            })
                        elif isinstance(citation, str):
                            citations.append({
                                'url': '',
                                'title': citation,
                                'cited_text': '',
                                'p': ''
                            })
            
            # Legacy format support - tool_result blocks
            elif content_item.get('type') == 'tool_result':
                tool_content = content_item.get('content', [])
                for tool_item in tool_content:
                    if isinstance(tool_item, dict) and 'citations' in tool_item:
                        for citation in tool_item['citations']:
                            if isinstance(citation, dict):
                                citations.append({
                                    'url': citation.get('url', ''),
                                    'title': citation.get('title', ''),
                                    'cited_text': citation.get('cited_text', ''),
                                    'p': citation.get('p', '')  # Reliability score like "p85", "p50", etc.
                                })
                            elif isinstance(citation, str):
                                citations.append({
                                    'url': '',
                                    'title': citation,
                                    'cited_text': '',
                                    'p': ''
                                })
        
        return citations
        
    except Exception as e:
        logger.error(f"Failed to extract citations from response: {str(e)}")
        return []

def extract_citations_from_perplexity_response(response: Dict) -> List[Dict]:
    """Extract citations from Perplexity's search_results response."""
    citations = []
    try:
        # Handle non-dict responses gracefully
        if not isinstance(response, dict):
            logger.debug(f"[CITATION_EXTRACT] Response is not a dict (type: {type(response).__name__}), skipping extraction")
            return []

        # Extract from search_results array (contains snippets/quotes)
        search_results = response.get('search_results', [])
        for result in search_results:
            citation = {
                'url': result.get('url', ''),
                'title': result.get('title', ''),
                'cited_text': result.get('snippet', ''),  # This is the quote/snippet
                'date': result.get('date', ''),
                'last_updated': result.get('last_updated', ''),
                'p': result.get('p', '')  # Reliability score like "p85", "p50", etc.
            }
            citations.append(citation)

        # Also extract from citations array (just URLs)
        citation_urls = response.get('citations', [])
        existing_urls = {c['url'] for c in citations}
        for url in citation_urls:
            if url not in existing_urls:
                citations.append({
                    'url': url,
                    'title': '',
                    'cited_text': '',
                    'date': '',
                    'last_updated': '',
                    'p': ''
                })
        
        return citations
        
    except Exception as e:
        logger.error(f"Failed to extract citations from Perplexity response: {str(e)}")
        return []

def validate_against_schema(data: dict, schema: dict) -> bool:
    """
    Simple schema validation - checks if required fields are present.
    Returns True if valid, False if missing required fields.
    """
    try:
        if not isinstance(data, dict) or not isinstance(schema, dict):
            return False

        # Check required fields
        required = schema.get('required', [])
        for field in required:
            if field not in data:
                logger.debug(f"[SCHEMA_VALIDATION] Missing required field: {field}")
                return False

        # Check if all values are empty (indicates failure)
        if all(not v for v in data.values()):
            logger.debug(f"[SCHEMA_VALIDATION] All values empty")
            return False

        return True

    except Exception as e:
        logger.error(f"[SCHEMA_VALIDATION] Validation error: {e}")
        return False

def fuzzy_match_keys(data: Dict, schema_properties: Dict, threshold: float = 0.8) -> Dict:
    """
    Fuzzy match keys in data to schema property names.
    """
    def similarity(a: str, b: str) -> float:
        """Calculate string similarity (0.0-1.0)."""
        # Normalize for comparison
        a_norm = a.lower().replace('_', ' ').replace('-', ' ').strip()
        b_norm = b.lower().replace('_', ' ').replace('-', ' ').strip()
        return SequenceMatcher(None, a_norm, b_norm).ratio()

    if not isinstance(data, dict):
        return data

    normalized = {}
    matched_keys = set()

    # First pass: exact matches (case-insensitive)
    for key, value in data.items():
        exact_match = None
        for schema_key in schema_properties.keys():
            if key.lower() == schema_key.lower():
                exact_match = schema_key
                break

        if exact_match:
            normalized[exact_match] = value
            matched_keys.add(key)

    # Second pass: fuzzy matches for unmatched keys
    for key, value in data.items():
        if key in matched_keys:
            continue

        best_match = None
        best_score = 0.0

        for schema_key in schema_properties.keys():
            if schema_key in normalized:  # Already matched
                continue

            score = similarity(key, schema_key)
            if score > best_score and score >= threshold:
                best_score = score
                best_match = schema_key

        if best_match:
            logger.debug(f"[FUZZY_MATCH] Matched '{key}' -> '{best_match}' (similarity: {best_score:.2f})")
            normalized[best_match] = value
        else:
            # Keep original key if no match found
            normalized[key] = value

    return normalized

def is_url(value: str) -> bool:
    """Check if a string looks like a URL."""
    if not isinstance(value, str):
        return False
    return value.startswith('http://') or value.startswith('https://') or value.startswith('www.')

def normalize_url_for_comparison(url: str) -> str:
    """
    Normalize URL for fuzzy matching.
    """
    normalized = url.lower().strip()
    # Remove protocol
    normalized = re.sub(r'^https?://', '', normalized)
    # Remove www
    normalized = re.sub(r'^www\.', '', normalized)
    # Remove trailing slashes
    normalized = normalized.rstrip('/')
    # Remove query params and fragments for comparison
    normalized = re.sub(r'[?#].*$', '', normalized)
    return normalized

def fuzzy_match_url_to_citations(url: str, citations: list) -> tuple[bool, str]:
    """
    Fuzzy match a URL to citations list.
    """
    if not is_url(url):
        return (True, url)

    url_normalized = normalize_url_for_comparison(url)

    # Extract URLs from citations
    citation_urls = []
    for citation in citations:
        if isinstance(citation, dict):
            citation_urls.append(citation.get('url', ''))
        elif isinstance(citation, str):
            citation_urls.append(citation)

    # Try exact normalized match first
    for citation_url in citation_urls:
        if not citation_url:
            continue

        citation_normalized = normalize_url_for_comparison(citation_url)

        if url_normalized == citation_normalized:
            if url == citation_url:
                return (True, url)
            else:
                return (True, f"{url} (Citation: {citation_url})")

    best_match = None
    best_score = 0.0

    for citation_url in citation_urls:
        if not citation_url:
            continue

        citation_normalized = normalize_url_for_comparison(citation_url)

        if url_normalized in citation_normalized or citation_normalized in url_normalized:
            score = 0.95
        else:
            url_domain = url_normalized.split('/')[0]
            citation_domain = citation_normalized.split('/')[0]

            if url_domain == citation_domain:
                url_path = '/'.join(url_normalized.split('/')[1:])
                citation_path = '/'.join(citation_normalized.split('/')[1:])
                domain_score = 0.5
                if url_path and citation_path:
                    path_similarity = SequenceMatcher(None, url_path, citation_path).ratio()
                    score = domain_score + (path_similarity * 0.5)
                else:
                    score = domain_score
            else:
                score = SequenceMatcher(None, url_normalized, citation_normalized).ratio()

        if score > best_score:
            best_score = score
            best_match = citation_url

    if best_score >= 0.6:
        logger.debug(f"[URL_VALIDATION] Fuzzy match: {url} -> {best_match} (similarity: {best_score:.2f})")
        return (True, f"{url} (Citation: {best_match})")

    logger.warning(f"[URL_VALIDATION] URL not in citations: {url}")
    return (False, f"{url} (Warning: Not in citations!)")

def validate_urls_in_response(data: any, citations: list) -> any:
    """
    Post-processing function to validate all URLs in response against citations.
    """
    if isinstance(data, dict):
        validated = {}
        for key, value in data.items():
            if isinstance(value, str) and is_url(value):
                found, canonical_or_warning = fuzzy_match_url_to_citations(value, citations)
                validated[key] = canonical_or_warning
            elif isinstance(value, (dict, list)):
                validated[key] = validate_urls_in_response(value, citations)
            else:
                validated[key] = value
        return validated
    elif isinstance(data, list):
        validated = []
        for item in data:
            if isinstance(item, str) and is_url(item):
                found, canonical_or_warning = fuzzy_match_url_to_citations(item, citations)
                validated.append(canonical_or_warning)
            elif isinstance(item, (dict, list)):
                validated.append(validate_urls_in_response(item, citations))
            else:
                validated.append(item)
        return validated
    else:
        if isinstance(data, str) and is_url(data):
            found, canonical_or_warning = fuzzy_match_url_to_citations(data, citations)
            return canonical_or_warning
        return data

def coerce_value_to_type(value: any, expected_type: str) -> any:
    """Coerce a value to the expected type."""
    if value is None:
        return value

    try:
        if expected_type == 'number' or expected_type == 'float':
            if isinstance(value, str):
                return float(value)
            return float(value)
        elif expected_type == 'integer':
            if isinstance(value, str):
                return int(float(value))
            return int(value)
        elif expected_type == 'boolean':
            if isinstance(value, str):
                return value.lower() in ('true', 'yes', '1', 't', 'y')
            return bool(value)
        elif expected_type == 'string':
            return str(value)
        elif expected_type == 'array':
            if not isinstance(value, list):
                return [value]
            return value
        elif expected_type == 'object':
            if not isinstance(value, dict):
                logger.warning(f"[TYPE_COERCE] Cannot coerce {type(value)} to object")
            return value
        else:
            return value
    except Exception as e:
        logger.warning(f"[TYPE_COERCE] Failed to coerce {value} to {expected_type}: {e}")
        return value

def validate_and_normalize_soft_schema(data: Dict, schema: Dict, fuzzy_keys: bool = True, citations: list = None) -> tuple[Dict, list]:
    """
    Validate and normalize data against schema with flexible matching.
    """
    warnings = []
    if not isinstance(data, dict) or not isinstance(schema, dict):
        return data, warnings

    schema_properties = schema.get('properties', {})
    required_fields = schema.get('required', [])

    if fuzzy_keys and schema_properties:
        data = fuzzy_match_keys(data, schema_properties)

    normalized = {}
    for key, value in data.items():
        if key in schema_properties:
            prop_schema = schema_properties[key]
            expected_type = prop_schema.get('type')

            if expected_type and not isinstance(value, dict) and not isinstance(value, list):
                coerced = coerce_value_to_type(value, expected_type)
                if coerced != value:
                    logger.debug(f"[TYPE_COERCE] Coerced '{key}': {value} -> {coerced} ({expected_type})")
                normalized[key] = coerced

                # Check enum constraint for simple values
                enum_values = prop_schema.get('enum')
                if enum_values and coerced not in enum_values:
                    warnings.append(f"Invalid enum value for '{key}': '{coerced}' not in {enum_values}")
                    logger.warning(f"[SOFT_SCHEMA] Invalid enum value for '{key}': '{coerced}' not in {enum_values}")
            elif expected_type == 'object' and isinstance(value, dict):
                nested_normalized, nested_warnings = validate_and_normalize_soft_schema(value, prop_schema, fuzzy_keys)
                normalized[key] = nested_normalized
                warnings.extend([f"{key}.{w}" for w in nested_warnings])
            elif expected_type == 'array' and isinstance(value, list):
                item_schema = prop_schema.get('items', {})
                if item_schema.get('type') == 'object':
                    normalized_items = []
                    for i, item in enumerate(value):
                        if isinstance(item, dict):
                            norm_item, item_warnings = validate_and_normalize_soft_schema(item, item_schema, fuzzy_keys)
                            normalized_items.append(norm_item)
                            warnings.extend([f"{key}[{i}].{w}" for w in item_warnings])
                        else:
                            normalized_items.append(item)
                    normalized[key] = normalized_items
                else:
                    normalized[key] = value
            else:
                normalized[key] = value
        else:
            normalized[key] = value

    # Auto-calculate missing fields (match_score, qc_summary)
    if 'match_score' in required_fields and 'match_score' not in normalized:
        if 'score_breakdown' in normalized:
            try:
                breakdown = normalized['score_breakdown']
                relevancy = float(breakdown.get('relevancy', 0))
                reliability = float(breakdown.get('reliability', 0))
                recency = float(breakdown.get('recency', 0))
                match_score = (relevancy * 0.4) + (reliability * 0.3) + (recency * 0.3)
                normalized['match_score'] = round(match_score, 3)
                logger.debug(f"[AUTO_CALCULATE] Calculated match_score={match_score:.3f}")
            except Exception as e:
                logger.warning(f"[AUTO_CALCULATE] Failed to calculate match_score: {e}")

    if 'qc_summary' in required_fields and 'qc_summary' not in normalized:
        if 'reviewed_rows' in normalized:
            try:
                reviewed_rows = normalized['reviewed_rows']
                total_reviewed = len(reviewed_rows)
                kept = sum(1 for row in reviewed_rows if row.get('keep', False))
                rejected = sum(1 for row in reviewed_rows if not row.get('keep', True))
                promoted = sum(1 for row in reviewed_rows if row.get('priority_adjustment') == 'promote')
                demoted = sum(1 for row in reviewed_rows if row.get('priority_adjustment') == 'demote')

                normalized['qc_summary'] = {
                    'total_reviewed': total_reviewed,
                    'kept': kept,
                    'rejected': rejected,
                    'promoted': promoted,
                    'demoted': demoted,
                    'reasoning': f"Reviewed {total_reviewed} rows: {kept} kept, {rejected} rejected"
                }
                logger.debug(f"[AUTO_CALCULATE] Calculated qc_summary from {total_reviewed} reviewed_rows")
            except Exception as e:
                logger.warning(f"[AUTO_CALCULATE] Failed to calculate qc_summary: {e}")

    for field in required_fields:
        if field not in normalized:
            warnings.append(f"Missing required field: {field}")
            logger.warning(f"[SOFT_SCHEMA] Missing required field: {field}")

    return normalized, warnings

def extract_content_description(request_data: Dict) -> str:
    """Extract a short description from the content for use in filename."""
    try:
        if 'data' in request_data and 'messages' in request_data['data']:
            for message in request_data['data']['messages']:
                if isinstance(message, dict) and 'content' in message and message.get('role') == 'user':
                    content = message['content']
                    if isinstance(content, str) and content.strip():
                        words = []
                        for word in content.split():
                            clean_word = ''.join(c for c in word if c.isalnum())
                            if clean_word and len(clean_word) > 2:
                                words.append(clean_word)
                            if len(words) >= 4:
                                break
                        if words:
                            return '_'.join(words)[:50]
        return 'request'
    except Exception:
        return 'request'

def extract_json_from_text(text: str) -> Optional[Dict]:
    """
    Extract and parse JSON from text, handling markdown code blocks and surrounding whitespace.

    Uses multiple extraction strategies in order:
    1. Extract from markdown code fences (```json ... ```)
    2. Find balanced JSON object with proper brace matching
    3. Try simple first { to last } as fallback
    """

    def find_balanced_json(text: str, start_char: str = '{', end_char: str = '}') -> Optional[str]:
        """Find a balanced JSON object/array by counting braces/brackets."""
        start_idx = text.find(start_char)
        if start_idx == -1:
            return None

        count = 0
        in_string = False
        escape = False

        for i in range(start_idx, len(text)):
            char = text[i]

            # Handle string escaping
            if escape:
                escape = False
                continue
            if char == '\\':
                escape = True
                continue

            # Track if we're inside a string
            if char == '"':
                in_string = not in_string
                continue

            # Only count braces/brackets outside strings
            if not in_string:
                if char == start_char:
                    count += 1
                elif char == end_char:
                    count -= 1
                    if count == 0:
                        # Found balanced JSON
                        return text[start_idx:i+1]

        return None

    try:
        text = text.strip()

        # Strategy 1: Extract from markdown code fences
        # Look for ```json ... ``` or ``` ... ```
        code_fence_pattern = r'```(?:json)?\s*\n?(.*?)\n?```'
        code_match = re.search(code_fence_pattern, text, re.DOTALL)
        if code_match:
            json_text = code_match.group(1).strip()
            try:
                return json.loads(json_text)
            except:
                # Code fence content wasn't valid JSON, try other strategies
                pass

        # Strategy 2: Find balanced JSON object (handles extra text before/after)
        balanced = find_balanced_json(text, '{', '}')
        if balanced:
            try:
                return json.loads(balanced)
            except:
                # Balanced braces but not valid JSON, continue
                pass

        # Strategy 3: Try balanced array (less common but possible)
        balanced_array = find_balanced_json(text, '[', ']')
        if balanced_array:
            try:
                parsed = json.loads(balanced_array)
                # If it's an array, wrap it in a dict with 'items' key
                if isinstance(parsed, list):
                    return {'items': parsed}
                return parsed
            except:
                pass

        # Strategy 4: Fallback to simple first { to last } (original behavior)
        match = re.search(r'(\{.*\})', text, re.DOTALL)
        if match:
            return json.loads(match.group(1))

        # No JSON found
        return None

    except Exception as e:
        logger.warning(f"Failed to extract JSON from text: {e}")
        return None

async def repair_json_with_haiku(malformed_text: str, schema: Dict, ai_client) -> tuple[Optional[Dict], Optional[Dict], Optional[str]]:
    """
    Use Claude Haiku to repair/extract JSON from malformed text.

    Args:
        malformed_text: The text containing malformed or embedded JSON
        schema: Expected schema for the JSON
        ai_client: AIAPIClient instance for making the repair call

    Returns:
        Tuple of (Repaired JSON dict or None, Full API response dict or None, Repair explanation or None)
    """
    try:
        # Create enhanced schema with repair explanation field
        enhanced_schema = json.loads(json.dumps(schema))  # Deep copy
        if 'properties' not in enhanced_schema:
            enhanced_schema['properties'] = {}

        enhanced_schema['properties']['_repair_explanation'] = {
            'type': 'string',
            'description': 'A concise 1-2 sentence explanation of why the schema failed and how you fixed it'
        }

        # Add _repair_explanation to required fields (deduplicate to prevent recursive accumulation)
        if 'required' not in enhanced_schema:
            enhanced_schema['required'] = []
        if '_repair_explanation' not in enhanced_schema['required']:
            enhanced_schema['required'].append('_repair_explanation')

        # Anthropic requires additionalProperties: false for JSON Schema 2020-12 compliance
        if enhanced_schema.get('type') == 'object':
            enhanced_schema['additionalProperties'] = False

        # Escape section symbols to prevent Gemini from misinterpreting them
        # Use double § as escape sequence during repair
        escaped_text = malformed_text.replace('§', '{{SECTION}}')

        cleanup_prompt = f"""Extract and reformat JSON to match schema. Preserve all information.

Replace all {{{{SECTION}}}} with § in output. Keep § symbols as-is (they are location codes).

Text:
{escaped_text}

Schema:
{json.dumps(schema, indent=2)}

Add _repair_explanation field (1-2 sentences): why original failed and how you fixed it.

Return raw JSON (first char {{, last char }}, parseable by json.loads() as-is)."""

        # Call Gemini 2.0 Flash (stable, FREE!) with hard schema to extract/repair (using enhanced schema with explanation)
        cleanup_result = await ai_client.call_structured_api(
            prompt=cleanup_prompt,
            schema=enhanced_schema,
            model="gemini-2.5-flash-lite",  # Stable production model, FREE tier available!
            use_cache=False,
            max_web_searches=0,
            soft_schema=False  # Use hard schema to ensure valid output
        )

        # Extract the repaired JSON
        repaired = extract_structured_response(cleanup_result['response'], "structured_response")

        # Restore section symbols if Gemini didn't convert escape sequence (fallback safety)
        repaired_str = json.dumps(repaired)
        if '{{SECTION}}' in repaired_str or '{SECTION}' in repaired_str:
            repaired_str = repaired_str.replace('{{SECTION}}', '§').replace('{SECTION}', '§')
            repaired = json.loads(repaired_str)

        # Extract and remove the repair explanation
        repair_explanation = repaired.pop('_repair_explanation', 'No explanation provided')

        logger.info(f"[HAIKU_REPAIR] Successfully repaired JSON - {repair_explanation}")
        return repaired, cleanup_result, repair_explanation

    except Exception as e:
        logger.error(f"[HAIKU_REPAIR] Repair failed: {e}")
        return None, None, None
