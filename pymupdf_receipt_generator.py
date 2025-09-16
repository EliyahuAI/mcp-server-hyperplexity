#!/usr/bin/env python3
"""
PyMuPDF-based PDF receipt generator for Lambda - NO PIL dependencies!
"""

import os
import logging
from datetime import datetime
from io import BytesIO

logger = logging.getLogger(__name__)

def generate_receipt_pdf_pymupdf(session_id: str, email: str, amount: float, 
                                transaction_details: dict) -> bytes:
    """Generate PDF receipt using PyMuPDF - works without PIL dependencies"""
    try:
        import fitz  # PyMuPDF
        logger.info("PyMuPDF imported successfully for PDF generation")
            
    except ImportError as import_e:
        logger.error(f"PyMuPDF not available: {import_e}")
        logger.info("Falling back to simple text-based receipt")
        return generate_simple_text_receipt(session_id, email, amount, transaction_details)
    
    try:
        # Create new PDF document
        doc = fitz.open()
        page = doc.new_page()
        
        # Page dimensions (Letter size) - match ReportLab exactly
        page_width = 612  # 8.5 inches * 72 points/inch
        page_height = 792  # 11 inches * 72 points/inch
        
        # Convert inches to points (1 inch = 72 points)
        inch = 72
        
        y_position = page_height - 2 * inch  # Start 2 inches from top
        
        # Logo paths to try (same as ReportLab version)
        logo_fallback_paths = [
            # New hyperplexity logo - Lambda function package root
            "/var/task/hyperplexity-logo-2.png",
            # New hyperplexity logo - current working directory
            "./hyperplexity-logo-2.png",
            "./frontend/hyperplexity-logo-2.png",
            # Development paths for testing
            "../deployment/package/hyperplexity-logo-2.png",
            "../../deployment/package/hyperplexity-logo-2.png",
            # AWS Lambda layer paths for new logo
            "/opt/hyperplexity-logo-2.png",
            # Legacy logo paths for backward compatibility
            "/var/task/EliyahuLogo_NoText_Crop.png",
            "./EliyahuLogo_NoText_Crop.png",
            "./src/lambdas/config/EliyahuLogo_NoText_Crop.png",
            "../config/EliyahuLogo_NoText_Crop.png",
            "../EliyahuLogo_NoText_Crop.png",
            "../../EliyahuLogo_NoText_Crop.png",
            # Temporary directory fallback
            "/tmp/hyperplexity-logo-2.png",
            "/tmp/EliyahuLogo_NoText_Crop.png"
        ]
        
        # Try to insert logo
        logo_found = False
        for path in logo_fallback_paths:
            if os.path.exists(path):
                try:
                    # Read image file
                    with open(path, 'rb') as f:
                        image_data = f.read()
                    
                    # Insert logo at top center - match ReportLab exactly
                    logo_size = 1.5 * inch  # 1.5 inch square logo
                    logo_x = (page_width - logo_size) / 2
                    logo_y = y_position - logo_size  # Logo at top
                    
                    img_rect = fitz.Rect(logo_x, logo_y, logo_x + logo_size, logo_y + logo_size)
                    page.insert_image(img_rect, stream=image_data)
                    
                    logo_found = True
                    logger.info(f"Logo loaded successfully from {path}")
                    break
                    
                except Exception as logo_e:
                    logger.warning(f"Could not load logo from {path}: {logo_e}")
                    continue
        
        if not logo_found:
            logger.warning("Logo files not found, proceeding without logo")
        
        # Company name and receipt title - match ReportLab positioning exactly
        y_position = page_height - 2.6 * inch  # Match ReportLab y_position
        
        # Company name (centered, Helvetica-Bold 20)
        company_text = "Hyperplexity.AI Table Research"
        # Calculate text width for centering (approximate)
        text_width_approx = len(company_text) * 10  # Rough approximation for fontsize 20
        x_centered = (page_width - text_width_approx) / 2
        page.insert_text((x_centered, y_position), company_text, fontsize=20, color=(0, 0, 0))
        
        y_position -= 0.4 * inch
        
        # Receipt title (centered, Helvetica 16)  
        receipt_text = "Payment Receipt"
        text_width_approx = len(receipt_text) * 8  # Rough approximation for fontsize 16
        x_centered = (page_width - text_width_approx) / 2
        page.insert_text((x_centered, y_position), receipt_text, fontsize=16, color=(0, 0, 0))
        
        # Receipt information section
        y_position -= 0.8 * inch
        
        receipt_date = datetime.now().strftime("%B %d, %Y at %I:%M %p UTC")
        
        # Left column labels, right column values - match ReportLab margins exactly
        left_margin = 1.5 * inch
        right_margin = page_width - 1.5 * inch
        
        def draw_info_row(label, value, y_pos):
            """Draw a label-value row exactly like ReportLab version"""
            # Bold label on left
            page.insert_text((left_margin, y_pos), label, fontsize=11, color=(0, 0, 0))
            
            # Value right-aligned at right margin
            value_str = str(value)
            # Approximate text width for right alignment
            value_width_approx = len(value_str) * 6  # Rough approximation for fontsize 11
            x_right_aligned = right_margin - value_width_approx
            page.insert_text((x_right_aligned, y_pos), value_str, fontsize=11, color=(0, 0, 0))
            
            return y_pos - 0.25 * inch  # Match ReportLab spacing exactly
        
        # Draw all info rows exactly like ReportLab
        y_position = draw_info_row("Receipt Date:", receipt_date, y_position)
        y_position = draw_info_row("Session ID:", session_id, y_position)
        y_position = draw_info_row("Customer Email:", email, y_position)
        y_position = draw_info_row("Service:", "Table Validation", y_position)
        
        # Add table name if available
        table_name = transaction_details.get('table_name', transaction_details.get('input_filename', 'N/A'))
        if table_name and table_name != 'N/A':
            y_position = draw_info_row("Input Table:", table_name, y_position)
        
        # Add configuration code if available
        config_id = transaction_details.get('config_id', 'N/A')
        if config_id and config_id != 'N/A':
            y_position = draw_info_row("Configuration Code:", config_id, y_position)
        
        # Service details section - match ReportLab exactly
        y_position -= 0.4 * inch
        page.insert_text((left_margin, y_position), "Service Details", fontsize=14, color=(0, 0, 0))
        
        y_position -= 0.3 * inch
        
        # Service details in requested order: Rows, Fields, Perplexity Calls, Claude Calls
        rows_processed = transaction_details.get('rows_processed', 0)
        fields_validated = transaction_details.get('columns_validated_count', 0)
        perplexity_calls = transaction_details.get('perplexity_api_calls', 0)
        claude_calls = transaction_details.get('anthropic_api_calls', 0)
        
        y_position = draw_info_row("Rows Processed:", f"{rows_processed:,}", y_position)
        y_position = draw_info_row("Columns Validated:", f"{fields_validated:,}", y_position)
        y_position = draw_info_row("Perplexity API Calls:", f"{perplexity_calls:,}", y_position)
        y_position = draw_info_row("Claude API Calls:", f"{claude_calls:,}", y_position)
        
        # Total section - match ReportLab exactly
        y_position -= 0.4 * inch
        
        # Draw line exactly like ReportLab
        line_y = y_position + 0.1 * inch
        line_start = fitz.Point(left_margin, line_y)
        line_end = fitz.Point(right_margin, line_y)
        page.draw_line(line_start, line_end, width=1, color=(0, 0, 0))
        
        y_position -= 0.2 * inch
        
        # Total charged line (bold, fontsize 14)
        page.insert_text((left_margin, y_position), "Total Charged:", fontsize=14, color=(0, 0, 0))
        # Right-align the amount
        amount_str = f"${amount:.2f}"
        amount_width_approx = len(amount_str) * 8  # Rough approximation for fontsize 14
        x_right_aligned = right_margin - amount_width_approx
        page.insert_text((x_right_aligned, y_position), amount_str, fontsize=14, color=(0, 0, 0))
        
        # Footer - match ReportLab positioning exactly
        footer_y = 2 * inch  # 2 inches from bottom
        footer_texts = [
            "Thank you for using Hyperplexity!",
            "For support, contact: eliyahu@eliyahu.ai", 
            "This receipt is for your records."
        ]
        
        for text in footer_texts:
            # Center the text (approximate)
            text_width_approx = len(text) * 5  # Rough approximation for fontsize 10
            x_centered = (page_width - text_width_approx) / 2
            page.insert_text((x_centered, footer_y), text, fontsize=10, color=(0, 0, 0))
            footer_y -= 0.25 * inch  # Match ReportLab spacing
        
        # Save PDF to bytes
        pdf_bytes = doc.write()
        doc.close()
        
        logger.info(f"PyMuPDF PDF generation successful! Size: {len(pdf_bytes):,} bytes")
        return pdf_bytes
        
    except Exception as e:
        logger.error(f"Error generating PyMuPDF PDF receipt: {e}")
        import traceback
        logger.error(f"PyMuPDF PDF generation traceback: {traceback.format_exc()}")
        
        # Log current working directory and available files for debugging
        logger.error(f"Current working directory: {os.getcwd()}")
        try:
            logger.error(f"Files in current directory: {os.listdir('.')}")
        except:
            logger.error("Could not list current directory")
        
        # Fallback to text receipt
        logger.warning("PyMuPDF PDF generation failed, falling back to text receipt")
        return generate_simple_text_receipt(session_id, email, amount, transaction_details)

def generate_simple_text_receipt(session_id: str, email: str, amount: float, 
                                transaction_details: dict) -> bytes:
    """Generate a simple text-based receipt when PDF generation is not available"""
    from datetime import datetime
    
    receipt_date = datetime.now().strftime("%B %d, %Y at %I:%M %p UTC")
    
    # Extract transaction details with defaults
    rows_processed = transaction_details.get('rows_processed', 0)
    fields_validated = transaction_details.get('columns_validated_count', 0)
    perplexity_calls = transaction_details.get('perplexity_api_calls', 0)
    claude_calls = transaction_details.get('anthropic_api_calls', 0)
    table_name = transaction_details.get('table_name', transaction_details.get('input_filename', 'N/A'))
    config_id = transaction_details.get('config_id', 'N/A')
    
    receipt_text = f"""
======================================================================
                    HYPERPLEXITY.AI TABLE RESEARCH
                           PAYMENT RECEIPT
======================================================================

Receipt Date:          {receipt_date}
Session ID:            {session_id}
Customer Email:        {email}
Service:               Table Validation

{f'Input Table:            {table_name}' if table_name and table_name != 'N/A' else ''}
{f'Configuration Code:     {config_id}' if config_id and config_id != 'N/A' else ''}

----------------------------------------------------------------------
                            SERVICE DETAILS
----------------------------------------------------------------------

Rows Processed:        {rows_processed:,}
Columns Validated:      {fields_validated:,}
Perplexity API Calls:  {perplexity_calls:,}
Claude API Calls:      {claude_calls:,}

----------------------------------------------------------------------
                               TOTAL
----------------------------------------------------------------------

Total Charged:         ${amount:.2f}

======================================================================

Thank you for using Hyperplexity!
For support, contact: eliyahu@eliyahu.ai
This receipt is for your records.

======================================================================
    """.strip()
    
    logger.info(f"Generated simple text receipt for session {session_id}: ${amount:.2f}")
    return receipt_text.encode('utf-8')

# Test the function
if __name__ == "__main__":
    # Test data
    session_id = "pymupdf_test_20250910_123456"
    email = "test@hyperplexity.ai"
    amount = 29.99
    transaction_details = {
        'rows_processed': 250,
        'description': "PyMuPDF test - 250 rows processed",
        'session_id': session_id,
        'perplexity_api_calls': 45,
        'anthropic_api_calls': 32,
        'columns_validated_count': 15,
        'table_name': 'PyMuPDF Test Table.xlsx',
        'input_filename': 'PyMuPDF Test Table.xlsx',
        'config_id': 'CONFIG_PYMUPDF_FINAL'
    }
    
    print("Testing PyMuPDF Receipt Generation")
    print("=" * 50)
    
    try:
        receipt_bytes = generate_receipt_pdf_pymupdf(session_id, email, amount, transaction_details)
        
        receipt_type = "PDF" if receipt_bytes.startswith(b'%PDF') else "Text"
        print(f"Receipt generated successfully!")
        print(f"Type: {receipt_type}")
        print(f"Size: {len(receipt_bytes):,} bytes")
        
        # Save to file
        filename = f"pymupdf_receipt_test.{'pdf' if receipt_type == 'PDF' else 'txt'}"
        with open(filename, 'wb') as f:
            f.write(receipt_bytes)
        
        print(f"Saved to: {filename}")
        
    except Exception as e:
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()