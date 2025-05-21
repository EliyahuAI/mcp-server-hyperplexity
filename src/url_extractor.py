"""
Module for extracting and normalizing URLs from text.
"""
import re
import logging
from typing import List, Optional, Dict, Any

logger = logging.getLogger()

# Regular expression to match URLs
URL_PATTERN = r'https?://(?:[-\w.]|(?:%[\da-fA-F]{2}))+(?:/[-\w%!.~\'*,;:=+()@/&?#[\]]*)?'

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