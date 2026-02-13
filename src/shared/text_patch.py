#!/usr/bin/env python3
"""
Direct Text Patching API

Apply patch operations directly to plain text strings without JSON wrapper.
Useful for patching markdown documents, reports, logs, and other text content.

Example:
    from shared.text_patch import apply_text_patches

    doc = '''# My Report
    ## Introduction
    Draft content here.
    '''

    patches = [
        {"op": "text_replace", "match": "Draft", "value": "Final"},
        {"op": "text_extend", "value": "\n## Conclusion\nEnd of report"}
    ]

    result = apply_text_patches(doc, patches)
    print(result)
"""

import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Import text operations
try:
    from shared.text_ops import apply_text_replace, apply_text_extend, RegexTimeout
    TEXT_OPS_AVAILABLE = True
except ImportError:
    TEXT_OPS_AVAILABLE = False
    logger.error("text_ops module not available - cannot use text patching")


@dataclass
class TextPatchResult:
    """Result of applying text patches"""
    success: bool
    text: Optional[str] = None
    error: Optional[str] = None
    operations_applied: int = 0


def apply_text_patches(
    text: str,
    patches: List[Dict[str, Any]],
    allow_non_text_ops: bool = False
) -> TextPatchResult:
    """
    Apply patch operations directly to a text string.

    Text operations work on the document itself. The path is ignored
    (or should be "/" for root).

    Supported operations:
    - text_replace: Find and replace within text
    - text_extend: Append or prepend to text

    Args:
        text: Original text document
        patches: List of patch operations
        allow_non_text_ops: If True, allow non-text ops (will be ignored with warning)

    Returns:
        TextPatchResult with modified text or error

    Example:
        >>> doc = "Draft Report\\nContent here"
        >>> patches = [
        ...     {"op": "text_replace", "match": "Draft", "value": "Final"},
        ...     {"op": "text_extend", "value": "\\nEnd"}
        ... ]
        >>> result = apply_text_patches(doc, patches)
        >>> print(result.text)
        Final Report
        Content here
        End
    """
    if not TEXT_OPS_AVAILABLE:
        return TextPatchResult(
            success=False,
            error="text_ops module not available"
        )

    if not isinstance(text, str):
        return TextPatchResult(
            success=False,
            error=f"Input must be string, got {type(text).__name__}"
        )

    if not patches:
        return TextPatchResult(
            success=True,
            text=text,
            operations_applied=0
        )

    # Wrap text in temp dict for processing
    temp_data = {"__text__": text}
    operations_applied = 0

    try:
        for i, patch in enumerate(patches):
            op = patch.get('op')

            # Skip non-text operations
            if op not in ('text_replace', 'text_extend'):
                if allow_non_text_ops:
                    logger.warning(f"Skipping non-text operation: {op}")
                    continue
                else:
                    return TextPatchResult(
                        success=False,
                        error=f"Patch #{i+1}: Operation '{op}' not supported for text documents. Use 'text_replace' or 'text_extend'."
                    )

            # Apply text operation
            if op == 'text_replace':
                match = patch.get('match')
                value = patch.get('value')
                regex = patch.get('regex', False)
                count = patch.get('count', 1)

                if match is None or value is None:
                    return TextPatchResult(
                        success=False,
                        error=f"Patch #{i+1}: text_replace requires 'match' and 'value'"
                    )

                try:
                    apply_text_replace(
                        temp_data,
                        "/__text__",
                        match,
                        value,
                        regex,
                        count
                    )
                    operations_applied += 1
                except Exception as e:
                    return TextPatchResult(
                        success=False,
                        error=f"Patch #{i+1}: {str(e)}"
                    )

            elif op == 'text_extend':
                value = patch.get('value')
                position = patch.get('position', 'end')

                if value is None:
                    return TextPatchResult(
                        success=False,
                        error=f"Patch #{i+1}: text_extend requires 'value'"
                    )

                try:
                    apply_text_extend(
                        temp_data,
                        "/__text__",
                        value,
                        position
                    )
                    operations_applied += 1
                except Exception as e:
                    return TextPatchResult(
                        success=False,
                        error=f"Patch #{i+1}: {str(e)}"
                    )

        return TextPatchResult(
            success=True,
            text=temp_data["__text__"],
            operations_applied=operations_applied
        )

    except Exception as e:
        logger.error(f"Text patching failed: {e}")
        return TextPatchResult(
            success=False,
            error=str(e)
        )


def patch_text_simple(
    text: str,
    find: str,
    replace: str,
    regex: bool = False,
    count: int = 1
) -> str:
    """
    Simple helper for find/replace in text.

    Args:
        text: Original text
        find: Text to find (or regex pattern if regex=True)
        replace: Replacement text
        regex: If True, use regex matching
        count: Number of matches to replace (-1 for all)

    Returns:
        Modified text

    Raises:
        ValueError: If find/replace fails

    Example:
        >>> doc = "Draft Report"
        >>> result = patch_text_simple(doc, "Draft", "Final")
        >>> print(result)
        Final Report
    """
    patches = [{
        "op": "text_replace",
        "match": find,
        "value": replace,
        "regex": regex,
        "count": count
    }]

    result = apply_text_patches(text, patches)

    if not result.success:
        raise ValueError(result.error)

    return result.text


def append_text(text: str, addition: str) -> str:
    """
    Append text to the end of a document.

    Args:
        text: Original text
        addition: Text to append

    Returns:
        Modified text

    Example:
        >>> doc = "Main content"
        >>> result = append_text(doc, "\\n\\nFooter")
        >>> print(result)
        Main content

        Footer
    """
    patches = [{
        "op": "text_extend",
        "value": addition,
        "position": "end"
    }]

    result = apply_text_patches(text, patches)

    if not result.success:
        raise ValueError(result.error)

    return result.text


def prepend_text(text: str, addition: str) -> str:
    """
    Prepend text to the beginning of a document.

    Args:
        text: Original text
        addition: Text to prepend

    Returns:
        Modified text

    Example:
        >>> doc = "Main content"
        >>> result = prepend_text(doc, "Header\\n\\n")
        >>> print(result)
        Header

        Main content
    """
    patches = [{
        "op": "text_extend",
        "value": addition,
        "position": "start"
    }]

    result = apply_text_patches(text, patches)

    if not result.success:
        raise ValueError(result.error)

    return result.text


def patch_markdown_section(
    markdown: str,
    section_header: str,
    new_content: str,
    include_header: bool = False
) -> str:
    """
    Replace content of a markdown section.

    Simple implementation: finds the section and replaces everything until
    the next section header of the same or higher level.

    Args:
        markdown: Original markdown document
        section_header: Header to find (e.g., "## Introduction")
        new_content: New content for the section
        include_header: If True, replace header too

    Returns:
        Modified markdown

    Example:
        >>> doc = '''# Report
        ... ## Section 1
        ... Old content
        ... ## Section 2
        ... More content'''
        >>> result = patch_markdown_section(doc, "## Section 1", "## Section 1\\nNew content")
        >>> print(result)
        # Report
        ## Section 1
        New content
        ## Section 2
        More content
    """
    # For simplicity, use literal string replacement
    # Find the section header
    if section_header not in markdown:
        raise ValueError(f"Section '{section_header}' not found in markdown")

    # Split by the header
    before, rest = markdown.split(section_header, 1)

    # Find the next section header (same or higher level)
    level = section_header.count('#')
    lines = rest.split('\n')

    # Find where next section starts
    content_lines = []
    next_section_start = None

    for i, line in enumerate(lines[1:], 1):  # Skip first line (empty after header)
        if line.startswith('#' * level + ' ') or (level > 1 and line.startswith('#' * (level - 1) + ' ')):
            next_section_start = i
            break
        content_lines.append(line)

    # Build result
    if include_header:
        # Replace header + content with new content
        result = before + new_content
    else:
        # Keep header, replace only content
        result = before + section_header + '\n' + new_content

    # Add remaining sections if any
    if next_section_start is not None:
        result += '\n' + '\n'.join(lines[next_section_start:])

    return result


# Convenience function for AI-generated patches on text
async def refine_text_with_ai(
    text: str,
    instructions: str,
    ai_client,
    model: str = "claude-sonnet-4-5",
    max_tokens: int = 4000
) -> TextPatchResult:
    """
    Use AI to generate and apply patches to text.

    Args:
        text: Original text document
        instructions: Instructions for how to modify the text
        ai_client: AI client instance
        model: Model to use
        max_tokens: Max tokens for response

    Returns:
        TextPatchResult with modified text

    Example:
        >>> doc = "Draft Report\\nContent here"
        >>> result = await refine_text_with_ai(
        ...     doc,
        ...     "Change 'Draft' to 'Final' and add a conclusion",
        ...     ai_client
        ... )
        >>> print(result.text)
    """
    # Import here to avoid circular dependency
    from shared.ai_patch_utils import build_patch_prompt_template, create_patch_schema

    # Wrap text in temp structure
    temp_data = {"document": text}

    # Build prompt
    prompt = f"""You are refining a text document using patch operations.

# USER'S REQUEST

"{instructions}"

# CURRENT DOCUMENT

```
{text}
```

# YOUR TASK

Generate text patch operations to modify the document according to the user's request.

Available operations:
- text_replace: Find and replace text
- text_extend: Append or prepend text

Since this is a plain text document, use path "/__text__" for all operations.
"""

    # Create schema for text patches
    patch_schema = {
        "type": "object",
        "properties": {
            "patch_operations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "required": ["op"],
                    "properties": {
                        "op": {
                            "type": "string",
                            "enum": ["text_replace", "text_extend"]
                        },
                        "match": {"type": "string"},
                        "value": {"type": "string"},
                        "regex": {"type": "boolean"},
                        "count": {"type": "integer"},
                        "position": {"type": "string", "enum": ["start", "end"]}
                    }
                }
            },
            "reasoning": {"type": "string"}
        },
        "required": ["patch_operations", "reasoning"]
    }

    # Call AI
    result = await ai_client.call_structured_api(
        prompt=prompt,
        schema=patch_schema,
        model=model,
        tool_name="text_patches",
        max_tokens=max_tokens
    )

    # Extract patches
    structured_data = ai_client.extract_structured_response(result['response'], "text_patches")
    patches = structured_data.get('patch_operations', [])

    if not patches:
        return TextPatchResult(
            success=False,
            error="No patches generated by AI"
        )

    # Apply patches
    return apply_text_patches(text, patches)


# Export main functions
__all__ = [
    'apply_text_patches',
    'patch_text_simple',
    'append_text',
    'prepend_text',
    'patch_markdown_section',
    'refine_text_with_ai',
    'TextPatchResult'
]
