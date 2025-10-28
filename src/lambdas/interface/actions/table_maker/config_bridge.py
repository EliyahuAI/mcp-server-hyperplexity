"""
Config bridge for table maker.

Converts table maker conversation and table structure data into the format
expected by the existing config generation lambda, with enhanced conversation context.
"""
import logging
import json
from typing import Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def build_table_analysis_from_conversation(
    conversation_state: Dict[str, Any],
    preview_data: Dict[str, Any],
    table_rows: List[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Build enhanced table_analysis structure for config generation.

    This function transforms table maker data into the format expected by
    handle_generate_config_unified(), adding a new conversation_context field.

    Args:
        conversation_state: Conversation state from S3 containing messages and context
        preview_data: Preview data containing columns and sample rows
        table_rows: Optional full table rows (if available)

    Returns:
        {
            'basic_info': {...},
            'column_analysis': {...},
            'domain_info': {...},
            'metadata': {...},
            'conversation_context': {  # NEW - enriches existing config generation
                'research_purpose': str,
                'ai_reasoning': str,
                'column_details': [...],
                'identification_columns': [...]
            }
        }
    """
    logger.info("Building table_analysis from conversation and preview data")

    try:
        # Extract data from inputs
        columns = preview_data.get('columns', [])
        sample_rows = preview_data.get('sample_rows', [])
        messages = conversation_state.get('messages', [])
        context_research = conversation_state.get('context_research', {})

        # Use provided table_rows if available, otherwise use sample_rows
        rows = table_rows if table_rows is not None else sample_rows

        # Extract identification columns
        identification_columns = [
            col['name'] for col in columns if col.get('is_identification', False)
        ]

        # Build basic_info
        basic_info = {
            'filename': f"table_{conversation_state.get('session_id', 'unknown')}.csv",
            'total_rows': len(rows),
            'total_columns': len(columns),
            'has_header': True,
            'file_type': 'csv',
            'generated_by': 'table_maker',
            'generated_at': datetime.utcnow().isoformat() + 'Z'
        }

        # Build column_analysis
        column_analysis = {}
        for col in columns:
            col_name = col['name']

            # For ID columns, check if researchable for quality validation
            importance = col.get('importance', 'MEDIUM')
            is_id = col.get('is_identification', False)

            if is_id and importance == 'ID':
                # Check if this ID column can be researched on the web
                if _is_researchable_id_column(col):
                    # Mark as CRITICAL to enable validation (verifies row generation quality)
                    importance = 'CRITICAL'
                    logger.info(f"Marking researchable ID column '{col_name}' as CRITICAL for validation")

            column_analysis[col_name] = {
                'name': col_name,
                'description': col.get('description', ''),
                'data_type': infer_data_type(col.get('format', 'String')),
                'importance': importance,
                'sample_values': [row.get(col_name, '') for row in rows[:5]],
                'is_identification': col.get('is_identification', False),
                'validation_hints': col.get('validation_hints', []),
                'expected_format': col.get('format', 'String')
            }

        # Build domain_info
        domain_info = {
            'domain': context_research.get('domain', 'research'),
            'insights': context_research.get('insights', ''),
            'inferred_domain': context_research.get('domain', 'research'),
            'confidence': context_research.get('confidence', 0.5),
            'sources': context_research.get('sources', [])
        }

        # Build metadata
        metadata = {
            'file_type': 'csv',
            'generated_by': 'table_maker',
            'conversation_id': conversation_state.get('conversation_id', 'unknown'),
            'session_id': conversation_state.get('session_id', 'unknown'),
            'email': conversation_state.get('email', 'unknown'),
            'created_at': conversation_state.get('created_at', datetime.utcnow().isoformat() + 'Z'),
            'turn_count': conversation_state.get('turn_count', 0)
        }

        # Extract tablewide_research from conversation state
        # This is the concise research summary from the LLM's table generation
        tablewide_research = conversation_state.get('tablewide_research', '')

        # Extract search_strategy with rich context about requirements, subdomains, discovered lists
        search_strategy = conversation_state.get('search_strategy', {})

        # Build conversation_context (NEW FIELD)
        # This enriches the existing config generation without breaking compatibility
        conversation_context = {
            'research_purpose': extract_research_purpose(messages),
            'ai_reasoning': extract_ai_reasoning(messages),
            'column_details': columns,
            'identification_columns': identification_columns,
            'conversation_history': messages,
            'context_research': context_research,
            'user_requirements': extract_user_requirements(messages),
            'clarifying_questions_asked': extract_clarifying_questions(messages),
            'readiness_confidence': conversation_state.get('readiness_confidence', 0.0),
            'tablewide_research': tablewide_research,  # Research to embed in general/column notes
            'search_strategy': search_strategy  # Requirements, subdomains, discovered lists, candidates
        }

        # Assemble complete table_analysis
        table_analysis = {
            'basic_info': basic_info,
            'column_analysis': column_analysis,
            'domain_info': domain_info,
            'metadata': metadata,
            'conversation_context': conversation_context
        }

        logger.info(f"Built table_analysis with {len(columns)} columns and {len(rows)} sample rows")
        logger.info(f"Identified {len(identification_columns)} ID columns: {identification_columns}")

        # Log rich search_strategy context being passed
        if search_strategy:
            num_subdomains = len(search_strategy.get('subdomains', []))
            num_requirements = len(search_strategy.get('requirements', []))
            has_discovered_lists = any(
                sd.get('discovered_list_url') or sd.get('candidates')
                for sd in search_strategy.get('subdomains', [])
            )
            logger.info(
                f"Search strategy context: {num_subdomains} subdomains, "
                f"{num_requirements} requirements, "
                f"discovered_lists={has_discovered_lists}"
            )

        return table_analysis

    except Exception as e:
        logger.error(f"Failed to build table_analysis: {e}", exc_info=True)
        raise


def extract_research_purpose(messages: List[Dict[str, str]]) -> str:
    """
    Extract the research purpose from conversation messages.

    Args:
        messages: List of conversation messages

    Returns:
        Research purpose string
    """
    if not messages:
        return "Unknown research purpose"

    # First user message typically contains the research purpose
    for msg in messages:
        if msg.get('role') == 'user':
            return msg.get('content', 'Unknown research purpose')

    return "Unknown research purpose"


def extract_ai_reasoning(messages: List[Dict[str, str]]) -> str:
    """
    Extract AI's reasoning for the table structure.

    Args:
        messages: List of conversation messages

    Returns:
        AI reasoning string
    """
    if not messages:
        return "No AI reasoning available"

    # Last assistant message typically contains final reasoning
    for msg in reversed(messages):
        if msg.get('role') == 'assistant':
            content = msg.get('content', '')
            # Look for reasoning patterns
            if 'designed' in content.lower() or 'structure' in content.lower():
                return content

    # Fallback to last assistant message
    for msg in reversed(messages):
        if msg.get('role') == 'assistant':
            return msg.get('content', 'No AI reasoning available')

    return "No AI reasoning available"


def extract_user_requirements(messages: List[Dict[str, str]]) -> List[str]:
    """
    Extract specific requirements mentioned by the user.

    Args:
        messages: List of conversation messages

    Returns:
        List of user requirements
    """
    requirements = []

    for msg in messages:
        if msg.get('role') == 'user':
            content = msg.get('content', '')
            # Simple extraction - look for requirement keywords
            if any(keyword in content.lower() for keyword in ['need', 'want', 'require', 'must', 'should', 'include']):
                requirements.append(content)

    return requirements


def extract_clarifying_questions(messages: List[Dict[str, str]]) -> List[str]:
    """
    Extract clarifying questions asked by the AI.

    Args:
        messages: List of conversation messages

    Returns:
        List of clarifying questions
    """
    questions = []

    for msg in messages:
        if msg.get('role') == 'assistant':
            content = msg.get('content', '')
            # Look for questions (ending with ?)
            sentences = content.split('?')
            for sentence in sentences[:-1]:  # Exclude last element (after final ?)
                question = sentence.strip() + '?'
                if question:
                    questions.append(question)

    return questions


def infer_data_type(format_string: str) -> str:
    """
    Infer validation data type from column format specification.

    Args:
        format_string: Format specification (e.g., "Integer", "URL", "Date")

    Returns:
        Data type for validation
    """
    format_map = {
        'integer': 'number',
        'float': 'number',
        'number': 'number',
        'url': 'url',
        'email': 'email',
        'date': 'date',
        'datetime': 'datetime',
        'boolean': 'boolean',
        'string': 'string',
        'text': 'string'
    }

    return format_map.get(format_string.lower(), 'string')


def _is_researchable_id_column(column: Dict[str, Any]) -> bool:
    """
    Determine if an ID column can be researched/validated on the web.

    Researchable ID columns should be marked as CRITICAL to enable validation,
    which adds quality control for row generation.

    Args:
        column: Column definition with name, format, description

    Returns:
        True if researchable (URLs, names, companies), False otherwise
    """
    col_name = column.get('name', '').lower()
    col_format = column.get('format', '').lower()
    col_desc = column.get('description', '').lower()

    combined = f"{col_name} {col_format} {col_desc}"

    # Researchable patterns
    researchable = [
        'url', 'website', 'link', 'site', 'homepage',
        'company', 'organization', 'firm', 'business', 'institution',
        'person', 'researcher', 'author', 'name', 'scientist',
        'email', 'contact', 'location', 'address'
    ]

    # Non-researchable patterns
    non_researchable = [
        'id', 'uuid', 'guid', 'key', 'index', 'number',
        'date', 'time', 'timestamp', 'code', 'serial'
    ]

    # Check researchable first
    for pattern in researchable:
        if pattern in combined:
            return True

    # Then check non-researchable
    for pattern in non_researchable:
        if pattern in combined:
            return False

    # Default: not researchable
    return False


def validate_table_analysis(table_analysis: Dict[str, Any]) -> bool:
    """
    Validate that table_analysis has all required fields.

    Args:
        table_analysis: The table analysis dictionary

    Returns:
        True if valid, raises ValueError if invalid
    """
    required_fields = ['basic_info', 'column_analysis', 'domain_info', 'metadata']

    for field in required_fields:
        if field not in table_analysis:
            raise ValueError(f"Missing required field: {field}")

    # Validate basic_info
    if not table_analysis['basic_info'].get('filename'):
        raise ValueError("basic_info missing filename")

    # Validate column_analysis
    if not table_analysis['column_analysis']:
        raise ValueError("column_analysis is empty")

    logger.info("table_analysis validation passed")
    return True
