import json
import re
import logging
from typing import Dict, List, Tuple, Any, Optional

# Configure logging
logger = logging.getLogger(__name__)

def parse_multiplex_with_citations(result: Dict) -> Tuple[List[Dict], Dict]:
    """
    Parse a multiplex validation response with citations from the API.
    
    Args:
        result: The raw API response
        
    Returns:
        A tuple of (items, citations) where items is a list of validation results
        and citations is a dict mapping citation numbers to URLs
    """
    items = []
    citations = {}
    
    try:
        # Get content from response
        if not isinstance(result, dict) or 'choices' not in result:
            return [], {}
            
        content = result['choices'][0]['message'].get('content', '')
        if not content:
            return [], {}
        
        # Extract citations from API response if available
        if 'citations' in result and isinstance(result['citations'], list):
            for i, citation in enumerate(result['citations']):
                citations[i + 1] = citation
        
        # Parse JSON from content
        try:
            parsed_json = json.loads(content)
            if isinstance(parsed_json, list):
                items = parsed_json
            else:
                # Try to extract from markdown code block if not a list
                if "```json" in content:
                    json_start = content.find("```json") + 7
                    json_end = content.find("```", json_start)
                    if json_end > json_start:
                        potential_items = json.loads(content[json_start:json_end].strip())
                        if isinstance(potential_items, list):
                            items = potential_items
                
        except json.JSONDecodeError:
            # Try to extract from markdown code block
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                if json_end > json_start:
                    try:
                        potential_items = json.loads(content[json_start:json_end].strip())
                        if isinstance(potential_items, list):
                            items = potential_items
                    except:
                        pass
            
            # If we still don't have items, try to extract using regex
            if not items:
                # Look for an array pattern with objects
                array_pattern = r'\[\s*\{[^]]*\}\s*\]'
                array_match = re.search(array_pattern, content)
                if array_match:
                    try:
                        potential_items = json.loads(array_match.group())
                        if isinstance(potential_items, list):
                            items = potential_items
                    except:
                        pass
    
    except Exception as e:
        logger.error(f"Error parsing multiplex with citations: {str(e)}")
    
    return items, citations

def parse_multiplex_with_references(content: str) -> Tuple[List[Dict], Dict]:
    """
    Parse a multiplex validation response that contains references section.
    
    Args:
        content: The API response content
        
    Returns:
        A tuple of (items, references) where items is a list of validation results
        and references is a dict mapping reference numbers to URLs
    """
    items = []
    references = {}
    
    try:
        # First try to parse as standard JSON
        try:
            parsed_json = json.loads(content)
            if isinstance(parsed_json, list):
                items = parsed_json
        except json.JSONDecodeError:
            # Try to extract from markdown code block
            if "```json" in content:
                json_start = content.find("```json") + 7
                json_end = content.find("```", json_start)
                if json_end > json_start:
                    try:
                        potential_items = json.loads(content[json_start:json_end].strip())
                        if isinstance(potential_items, list):
                            items = potential_items
                    except:
                        pass
        
        # Look for a references section
        ref_pattern = r'References?:\s*\n([\s\S]*?)(?:\n\n|$)'
        ref_match = re.search(ref_pattern, content)
        if ref_match:
            ref_section = ref_match.group(1)
            # Extract individual references
            ref_entries = re.findall(r'\[(\d+)\]:\s*([^\n]+)', ref_section)
            for ref_num, ref_url in ref_entries:
                try:
                    references[int(ref_num)] = ref_url.strip()
                except:
                    pass
    
    except Exception as e:
        logger.error(f"Error parsing multiplex with references: {str(e)}")
    
    return items, references

def apply_references_to_items(items: List[Dict], references: Dict[int, str]) -> List[Dict]:
    """
    Apply reference URLs to items in the validation results.
    
    Args:
        items: List of validation result items
        references: Dictionary mapping reference numbers to URLs
        
    Returns:
        Updated list of items with references resolved to URLs
    """
    updated_items = []
    
    for item in items:
        try:
            # Create a copy of the item to avoid modifying the original
            updated_item = item.copy()
            
            # Check for sources that are numeric references
            if 'sources' in updated_item and isinstance(updated_item['sources'], list):
                resolved_sources = []
                
                for source in updated_item['sources']:
                    # Handle different reference formats
                    source_str = str(source).strip()
                    
                    # Match patterns like [1], 1, etc.
                    ref_match = re.match(r'(?:\[)?(\d+)(?:\])?', source_str)
                    if ref_match:
                        ref_num = int(ref_match.group(1))
                        if ref_num in references:
                            resolved_sources.append(references[ref_num])
                        else:
                            resolved_sources.append(source)
                    else:
                        resolved_sources.append(source)
                
                updated_item['sources'] = resolved_sources
                
                # Set main_source to the first source if it exists
                if resolved_sources:
                    updated_item['main_source'] = resolved_sources[0]
                else:
                    updated_item['main_source'] = ""
            
            updated_items.append(updated_item)
        except Exception as e:
            logger.error(f"Error applying references to item: {str(e)}")
            updated_items.append(item)  # Keep original if error
    
    return updated_items 