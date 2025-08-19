"""
Module for extracting and normalizing URLs from text.
"""
import re
import logging
from typing import List, Optional, Dict, Any, Tuple, Union

logger = logging.getLogger()

# Regular expression to match URLs
URL_PATTERN = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[-\w%!.~\'*,;:=+()@/&?#[\]]*)?'

# Regular expression to match reference numbers like [1], [2], etc.
REF_NUMBER_PATTERN = r'\[(\d+)\]'

def extract_urls_from_text(text: str) -> List[str]:
    """
    Extract all URLs from a text string.
    
    Args:
        text: The text to extract URLs from
        
    Returns:
        List of extracted URLs
    """
    if not text:
        return []
    
    # Find all matches of the URL pattern
    urls = re.findall(URL_PATTERN, text)
    
    # Clean up URLs (remove trailing punctuation, etc.)
    cleaned_urls = []
    for url in urls:
        # Remove trailing punctuation that might have been included
        url = re.sub(r'[,.;:"\')]$', '', url)
        cleaned_urls.append(url)
    
    return cleaned_urls

def extract_reference_numbers(text: str) -> List[int]:
    """
    Extract reference numbers like [1], [2] from text.
    
    Args:
        text: The text to extract reference numbers from
        
    Returns:
        List of extracted reference numbers as integers
    """
    if not text:
        return []
    
    # Find all matches of the reference pattern
    matches = re.findall(REF_NUMBER_PATTERN, text)
    
    # Convert to integers
    numbers = [int(m) for m in matches]
    
    return numbers

def extract_citations_from_api_response(result: Dict) -> List[str]:
    """
    Extract citations from the Perplexity API response.
    
    Args:
        result: The full API response from Perplexity
        
    Returns:
        List of citation URLs
    """
    if not isinstance(result, dict):
        return []
    
    # Check if the response has a citations field
    if 'citations' in result and isinstance(result['citations'], list):
        return result['citations']
    
    return []

def extract_main_url_from_quote(quote: str) -> Optional[str]:
    """
    Extract the main URL from a quote, typically at the end.
    
    Args:
        quote: The quote text that might contain a URL
        
    Returns:
        The extracted URL, or None if not found
    """
    if not quote:
        return None
    
    # Try to get the last URL in the quote
    urls = extract_urls_from_text(quote)
    if urls:
        return urls[-1]  # Return the last URL found
    
    return None

def extract_references_from_content(content: str) -> Dict[int, str]:
    """
    Extract references section from content and parse it.
    
    Args:
        content: The full API response content
        
    Returns:
        Dictionary mapping reference numbers to URLs
    """
    references = {}
    
    # Look for a REFERENCES section
    matches = re.search(r'REFERENCES:\s*([\s\S]+?)(?:\n\n|\Z)', content, re.IGNORECASE)
    if not matches:
        return references
    
    references_section = matches.group(1)
    
    # Parse each reference line
    # Format is expected to be: [number] URL
    for line in references_section.strip().split('\n'):
        # Find the reference number
        ref_match = re.match(r'\[(\d+)\]\s*(.*)', line.strip())
        if ref_match:
            ref_num = int(ref_match.group(1))
            url = ref_match.group(2).strip()
            # Verify it's a URL
            if re.match(URL_PATTERN, url):
                references[ref_num] = url
    
    return references

def parse_multiplex_with_citations(result: Dict) -> Tuple[List[Dict[str, Any]], Dict[int, str]]:
    """
    Parse a multiplex response with citations from the API response.
    
    Args:
        result: The full API response from Perplexity
        
    Returns:
        Tuple of (parsed JSON array, references dictionary)
    """
    items = []
    citations = extract_citations_from_api_response(result)
    citations_dict = {}
    
    # Convert citations list to dictionary with 1-based index
    for i, citation in enumerate(citations):
        citations_dict[i + 1] = citation
    
    # Extract content from the response
    if 'choices' in result and len(result['choices']) > 0:
        content = result['choices'][0]['message'].get('content', '')
        
        # Try to parse content as individual items
        item_pattern = r'(?:^|\n)(\d+)\.\s+([^:]+):([^\n]+)(?:\n-\s*Correct Answer:([^\n]+))?(?:\n-\s*Confidence:([^\n]+))?(?:\n-\s*Sources:([^\n]+))?'
        items_matches = re.finditer(item_pattern, content)
        
        for match in items_matches:
            item = {
                "column": match.group(2).strip(),
                "answer": match.group(4).strip() if match.group(4) else "",
                "confidence": match.group(5).strip() if match.group(5) else "LOW",
                "quote": match.group(6).strip() if match.group(6) else "",
            }
            items.append(item)
    
    return items, citations_dict

def parse_multiplex_with_references(content: str) -> Tuple[List[Dict[str, Any]], Dict[int, str]]:
    """
    Parse a multiplex response with a references section.
    
    Args:
        content: The full API response content
        
    Returns:
        Tuple of (parsed JSON array, references dictionary)
    """
    # Extract the JSON part (which should be inside a code block)
    json_match = re.search(r'```(?:json)?\s*([\s\S]+?)```', content)
    
    if not json_match:
        # Try to extract any JSON array
        json_match = re.search(r'\[\s*{[\s\S]+?}\s*\]', content)
        if not json_match:
            logger.error("Could not find JSON array in content")
            return [], {}
    
    json_str = json_match.group(1)
    
    # Parse the JSON
    try:
        import json
        items = json.loads(json_str)
        if not isinstance(items, list):
            logger.error(f"Expected list but got {type(items)}")
            return [], {}
    except Exception as e:
        logger.error(f"Error parsing JSON: {str(e)}")
        return [], {}
    
    # Extract references
    references = extract_references_from_content(content)
    
    return items, references

def apply_references_to_items(items: List[Dict[str, Any]], references: Dict[int, str]) -> List[Dict[str, Any]]:
    """
    Apply references to each item in the list.
    
    Args:
        items: List of parsed JSON items
        references: Dictionary mapping reference numbers to URLs
        
    Returns:
        Updated list of items with sources added
    """
    for item in items:
        # Extract reference numbers from quote
        if 'quote' in item and isinstance(item['quote'], str):
            ref_numbers = extract_reference_numbers(item['quote'])
            
            # Add sources field with referenced URLs
            sources = []
            for ref_num in ref_numbers:
                if ref_num in references:
                    sources.append(references[ref_num])
            
            item['sources'] = sources
            
            # Set main_source if we have sources
            if sources:
                item['main_source'] = sources[0]
        
        # If no sources were found, add an empty array
        if 'sources' not in item:
            item['sources'] = []
    
    return items

def ensure_url_sources(result_obj: Dict[str, Any], citations: List[str]) -> Dict[str, Any]:
    """
    Ensure all sources are proper URLs, replacing reference numbers with actual URLs.
    
    Args:
        result_obj: The result object containing sources and main_source
        citations: List of citations from the API
        
    Returns:
        Updated result object with URL sources and main_source
    """
    if not isinstance(result_obj, dict):
        return result_obj
    
    # Process sources array
    if 'sources' in result_obj and isinstance(result_obj['sources'], list):
        # Create a new list for URL sources
        url_sources = []
        
        for source in result_obj['sources']:
            if isinstance(source, str):
                # If it looks like a URL, keep it
                if re.match(URL_PATTERN, source):
                    url_sources.append(source)
                # If it's a number or [number], try to map it to a citation
                elif source.isdigit() or (source.startswith('[') and source.endswith(']')):
                    index = int(source.strip('[]')) - 1  # Convert to 0-based index
                    if 0 <= index < len(citations):
                        url_sources.append(citations[index])
                    else:
                        # If we can't map it, keep it as is
                        url_sources.append(source)
                else:
                    # Keep other strings as-is
                    url_sources.append(source)
        
        # Update sources with URL sources
        result_obj['sources'] = url_sources
    
    # Process main_source
    if 'main_source' in result_obj:
        main_source = result_obj['main_source']
        if isinstance(main_source, str):
            # If it's already a URL, keep it
            if re.match(URL_PATTERN, main_source):
                pass  # No change needed
            # If it's a number or [number], try to map it to a citation
            elif main_source.isdigit() or (main_source.startswith('[') and main_source.endswith(']')):
                index = int(main_source.strip('[]')) - 1  # Convert to 0-based index
                if 0 <= index < len(citations):
                    result_obj['main_source'] = citations[index]
            # If there are sources, use the first one as main_source
            elif result_obj.get('sources') and len(result_obj['sources']) > 0:
                result_obj['main_source'] = result_obj['sources'][0]
    elif result_obj.get('sources') and len(result_obj['sources']) > 0:
        # If there's no main_source but there are sources, use the first one
        result_obj['main_source'] = result_obj['sources'][0]
    
    return result_obj

def normalize_sources(response_obj: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normalize sources in a response object to ensure they are valid URLs.
    
    Args:
        response_obj: The response object containing sources and quotes
        
    Returns:
        The response object with normalized sources
    """
    if not response_obj:
        return response_obj
    
    # Try to extract sources from various fields
    sources = []
    
    # 1. Extract from sources array if it exists and has URLs
    if 'sources' in response_obj and isinstance(response_obj['sources'], list):
        for source in response_obj['sources']:
            if isinstance(source, str):
                urls = extract_urls_from_text(source)
                if urls:
                    sources.extend(urls)
                else:
                    # Keep original source value for reference
                    sources.append(source)
    
    # 2. Extract from quote if it exists
    if 'quote' in response_obj and isinstance(response_obj['quote'], str):
        url = extract_main_url_from_quote(response_obj['quote'])
        if url and url not in sources:
            sources.append(url)
    
    # 3. Extract from explanation if it exists
    if 'explanation' in response_obj and isinstance(response_obj['explanation'], str):
        urls = extract_urls_from_text(response_obj['explanation'])
        for url in urls:
            if url not in sources:
                sources.append(url)
    
    # Update the sources in the response
    response_obj['sources'] = sources
    
    # Set a main_source if we have sources and it's not already set
    if sources and ('main_source' not in response_obj or not response_obj['main_source']):
        response_obj['main_source'] = sources[0]
    
    return response_obj 