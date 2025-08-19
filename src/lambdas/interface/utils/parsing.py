"""
Utility for parsing multipart/form-data from an API Gateway event body.
"""

import base64
import logging
import json

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def parse_multipart_form_data(body, content_type, is_base64_encoded=False):
    """Parse multipart form data from the request body."""
    try:
        # Decode base64 if needed
        if is_base64_encoded:
            body = base64.b64decode(body)
        elif isinstance(body, str):
            body = body.encode('utf-8')
        
        # Extract boundary from content type
        boundary = None
        if content_type and 'boundary=' in content_type:
            boundary = content_type.split('boundary=')[1]
            if boundary.startswith('"') and boundary.endswith('"'):
                boundary = boundary[1:-1]
        
        if not boundary:
            raise ValueError("No boundary found in Content-Type header")
        
        # Simple multipart parser
        boundary_bytes = ('--' + boundary).encode('utf-8')
        end_boundary_bytes = ('--' + boundary + '--').encode('utf-8')
        
        files = {}
        form_data = {}
        
        # Split by boundary
        parts = body.split(boundary_bytes)
        
        for part in parts[1:]:  # Skip first empty part
            if end_boundary_bytes[2:] in part:  # End boundary
                break
            
            if not part.strip():
                continue
            
            # Find headers and content
            if b'\r\n\r\n' in part:
                headers_part, content = part.split(b'\r\n\r\n', 1)
                content = content.rstrip(b'\r\n')
            else:
                continue
            
            headers = headers_part.decode('utf-8', errors='ignore')
            
            # Parse Content-Disposition header
            name = None
            filename = None
            for line in headers.split('\r\n'):
                if line.lower().startswith('content-disposition:'):
                    # Extract name and filename
                    if 'name="' in line:
                        name = line.split('name="')[1].split('"')[0]
                    if 'filename="' in line:
                        filename = line.split('filename="')[1].split('"')[0]
            
            if name:
                if filename:  # File field
                    files[name] = {
                        'filename': filename,
                        'content': content  # Keep binary content as-is
                    }
                else:  # Regular form field (text only)
                    # Special handling for config_file field
                    if name == 'config_file':
                        try:
                            # Try to decode as UTF-8 first
                            decoded_content = content.decode('utf-8')
                            form_data[name] = decoded_content
                        except UnicodeDecodeError:
                            # If UTF-8 fails, try other encodings
                            for encoding in ['latin-1', 'cp1252', 'iso-8859-1']:
                                try:
                                    decoded_content = content.decode(encoding)
                                    form_data[name] = decoded_content
                                    logger.warning(f"Decoded config_file using {encoding} encoding")
                                    break
                                except UnicodeDecodeError:
                                    continue
                            else:
                                # If all encodings fail, try to extract JSON-like content
                                try:
                                    # Find JSON boundaries in the raw bytes
                                    start_idx = content.find(b'{')
                                    end_idx = content.rfind(b'}')
                                    if start_idx != -1 and end_idx != -1:
                                        json_bytes = content[start_idx:end_idx+1]
                                        decoded_content = json_bytes.decode('utf-8', errors='ignore')
                                        form_data[name] = decoded_content
                                        logger.warning("Extracted JSON content from config_file with errors ignored")
                                    else:
                                        # Last resort: store as base64
                                        form_data[name] = base64.b64encode(content).decode('ascii')
                                        logger.error(f"Could not decode config_file, stored as base64")
                                except Exception as e:
                                    logger.error(f"Failed to extract JSON from config_file: {e}")
                                    form_data[name] = str(content)  # Store raw representation
                    else:
                        # For other form fields, use standard UTF-8 decoding
                        try:
                            form_data[name] = content.decode('utf-8')
                        except UnicodeDecodeError:
                                logger.warning(f"Could not decode form field '{name}' as UTF-8. Trying latin-1.")
                                try:
                                    form_data[name] = content.decode('latin-1')
                                except Exception:
                                    logger.error(f"Could not decode form field '{name}'. Storing as hex.")
                                    form_data[name] = content.hex()
        
        # Log parsed data for debugging (keep only counts)
        logger.info(f"Parsed form data fields: {list(form_data.keys())}")
        logger.info(f"Parsed files: {[f for f in files.keys()]}")
        
        # Validate config_file JSON without verbose logging
        if 'config_file' in form_data:
            try:
                json.loads(form_data['config_file'])
            except json.JSONDecodeError as e:
                logger.warning(f"config_file contains invalid JSON: {e}")
        
        return files, form_data
        
    except Exception as e:
        logger.error(f"Error parsing multipart data: {str(e)}")
        raise 