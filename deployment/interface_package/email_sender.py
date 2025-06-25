#!/usr/bin/env python3
"""
Email sender module for Perplexity Validator results
Sends enhanced validation results via Amazon SES
"""
import boto3
from botocore.exceptions import ClientError
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from io import BytesIO
import json
from datetime import datetime
import re
import logging

logger = logging.getLogger(__name__)

# Email configuration
SENDER = "eliyahu@eliyahu.ai"
BCC_ADDRESS = "ppp@eliyahu.ai"  # For tracking/analytics
CHARSET = "UTF-8"

def create_email_body(session_id, total_rows, fields_validated, confidence_distribution, processing_time=None, reference_pin=None, token_usage=None):
    """Create HTML email body for validation results"""
    
    # Format confidence distribution
    confidence_html = ""
    for level, count in confidence_distribution.items():
        confidence_html += f"<li><b>{level}:</b> {count} fields</li>"
    
    # Format fields list
    fields_html = ", ".join(fields_validated) if fields_validated else "No fields validated"
    
    # Processing time info
    time_info = f"<p><b>Processing Time:</b> {processing_time:.2f} seconds</p>" if processing_time else ""
    
    # Reference pin info
    pin_info = f"<p><b>Reference PIN:</b> <span style='font-family: Courier New, monospace; background-color: #f8f9fa; padding: 2px 6px; border-radius: 3px; font-weight: bold; color: #007bff;'>{reference_pin}</span></p>" if reference_pin else ""
    
    # Token usage info
    token_info = ""
    if token_usage:
        total_tokens = token_usage.get('total_tokens', 0)
        total_cost = token_usage.get('total_cost', 0.0)
        api_calls = token_usage.get('api_calls', 0)
        cached_calls = token_usage.get('cached_calls', 0)
        
        token_info = f"""
        <div class="token-usage">
            <h4>API Usage & Cost Analysis</h4>
            <p><b>Total Tokens:</b> {total_tokens:,}</p>
            <p><b>Total Cost:</b> ${total_cost:.6f}</p>
            <p><b>API Calls:</b> {api_calls} new, {cached_calls} cached</p>
        """
        
        # Add provider breakdown
        if 'by_provider' in token_usage:
            for provider, provider_data in token_usage['by_provider'].items():
                if provider_data.get('calls', 0) > 0:
                    if provider == 'perplexity':
                        token_info += f"""
            <p><b>Perplexity API:</b> {provider_data.get('prompt_tokens', 0):,} prompt + {provider_data.get('completion_tokens', 0):,} completion = {provider_data.get('total_tokens', 0):,} tokens (${provider_data.get('total_cost', 0.0):.6f})</p>
                        """
                    elif provider == 'anthropic':
                        token_info += f"""
            <p><b>Anthropic API:</b> {provider_data.get('input_tokens', 0):,} input + {provider_data.get('output_tokens', 0):,} output + {provider_data.get('cache_creation_tokens', 0):,} cache creation + {provider_data.get('cache_read_tokens', 0):,} cache read = {provider_data.get('total_tokens', 0):,} tokens (${provider_data.get('total_cost', 0.0):.6f})</p>
                        """
        
        token_info += "</div>"
    
    body_html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .header {{ background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin-bottom: 20px; }}
            .summary {{ background-color: #e9ecef; padding: 15px; border-radius: 5px; margin: 20px 0; }}
            .confidence {{ margin: 15px 0; }}
            .token-usage {{ background-color: #f0f8ff; padding: 15px; border-radius: 5px; margin: 20px 0; border-left: 4px solid #007bff; }}
            ul {{ margin: 10px 0; padding-left: 25px; }}
            .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; font-size: 0.9em; }}
            .logo {{ color: #007bff; font-weight: bold; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2>Perplexity Validation Results from <span class="logo">Eliyahu.AI</span></h2>
            <p>Your validation has been completed successfully!</p>
        </div>
        
        <p>Hello,</p>
        
        <p>Thank you for using the <a href="https://www.eliyahu.ai">Eliyahu.AI</a> Perplexity Validator. 
        Your validation results are attached to this email as an enhanced Excel file with color-coded confidence levels.</p>
        
        <div class="summary">
            <h3>Validation Summary</h3>
            <p><b>Session ID:</b> {session_id}</p>
            {pin_info}
            <p><b>Total Rows Processed:</b> {total_rows}</p>
            <p><b>Fields Validated:</b> {len(fields_validated) if fields_validated else 0}</p>
            <p><small>({fields_html})</small></p>
            {time_info}
            
            <div class="confidence">
                <p><b>Confidence Distribution:</b></p>
                <ul>
                    {confidence_html}
                </ul>
            </div>
        </div>
        
        {token_info}
        
        <h3>About Your Results</h3>
        <p>The attached Excel file contains:</p>
        <ul>
            <li><b>Color-coded cells</b> based on confidence levels:
                <ul>
                    <li>🟢 <b>Green:</b> HIGH confidence</li>
                    <li>🟡 <b>Yellow:</b> MEDIUM confidence</li>
                    <li>🔴 <b>Red:</b> LOW confidence</li>
                </ul>
            </li>
            <li><b>Cell comments</b> with validation details, quotes, and sources</li>
            <li><b>Multiple worksheets</b> for comprehensive analysis</li>
            <li><b>Validation tracking</b> showing which fields were updated</li>
        </ul>
        
        <p><b>Questions or need help?</b> Simply reply to this email and our team will assist you.</p>
        
        <div class="footer">
            <p>Best regards,<br>
            The <a href="https://www.eliyahu.ai">Eliyahu.AI</a> Team</p>
            
            <p><small>This email was sent because you requested validation results. 
            Your data is processed securely and is not stored beyond the validation session.</small></p>
        </div>
    </body>
    </html>
    """
    
    return body_html

def send_validation_results_email(email_address, zip_content, session_id, summary_data, processing_time=None, reference_pin=None, metadata=None):
    """
    Send validation results via email with ZIP attachment
    
    Args:
        email_address: Recipient email
        zip_content: Bytes content of the ZIP file
        session_id: Unique session identifier
        summary_data: Dictionary with validation summary info
        processing_time: Optional processing time in seconds
        
    Returns:
        dict: Response with status and message ID
    """
    try:
        # Create message with reference pin
        message = MIMEMultipart()
        message["From"] = SENDER
        message["To"] = email_address
        
        # Include reference pin in subject if available
        if reference_pin:
            message["Subject"] = f"Perplexity Validation Results - Reference #{reference_pin}"
        else:
            message["Subject"] = f"Perplexity Validation Results - Session {session_id[:8]}"
        
        # Extract summary data
        total_rows = summary_data.get('total_rows', 0)
        fields_validated = summary_data.get('fields_validated', [])
        confidence_distribution = summary_data.get('confidence_distribution', {})
        
        # Extract token usage from metadata
        token_usage = None
        if metadata and 'token_usage' in metadata:
            token_usage = metadata['token_usage']
        
        # Create email body
        body_html = create_email_body(
            session_id, 
            total_rows, 
            fields_validated, 
            confidence_distribution,
            processing_time,
            reference_pin,
            token_usage
        )
        
        # Attach HTML body
        part = MIMEText(body_html, 'html', CHARSET)
        message.attach(part)
        
        # Attach ZIP file with reference pin in filename
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        if reference_pin:
            filename = f"validation_results_{timestamp}_{reference_pin}.zip"
        else:
            filename = f"validation_results_{timestamp}.zip"
        
        part = MIMEApplication(zip_content)
        part.add_header("Content-Disposition", f"attachment; filename={filename}")
        message.attach(part)
        
        # Send email via SES
        ses_client = boto3.client('ses')
        
        # Send to recipient with BCC
        destinations = [email_address]
        if BCC_ADDRESS and BCC_ADDRESS != email_address:
            destinations.append(BCC_ADDRESS)
            
        response = ses_client.send_raw_email(
            Source=SENDER,
            Destinations=destinations,
            RawMessage={
                'Data': message.as_string()
            }
        )
        
        message_id = response['MessageId']
        logger.info(f"Email sent successfully! Message ID: {message_id}")
        
        # Log email metadata to S3 (optional tracking)
        try:
            email_metadata = {
                'MessageID': message_id,
                'SessionID': session_id,
                'Recipient': email_address,
                'Timestamp': datetime.utcnow().isoformat(),
                'Subject': message["Subject"],
                'TotalRows': total_rows,
                'FieldsValidated': fields_validated,
                'ConfidenceDistribution': confidence_distribution,
                'AttachmentSize': len(zip_content)
            }
            
            s3_client = boto3.client('s3')
            s3_client.put_object(
                Bucket='perplexity-cache',  # Using existing bucket
                Key=f'email_logs/{session_id}/email_metadata.json',
                Body=json.dumps(email_metadata, indent=2),
                ContentType='application/json'
            )
            logger.info("Email metadata saved to S3")
            
        except Exception as e:
            logger.warning(f"Failed to save email metadata: {e}")
            # Don't fail the email send if metadata save fails
        
        return {
            'success': True,
            'message_id': message_id,
            'message': f"Results sent successfully to {email_address}"
        }
        
    except ClientError as e:
        error_message = e.response['Error']['Message']
        logger.error(f"SES error: {error_message}")
        
        # Check for common SES errors
        if 'MessageRejected' in str(e):
            if 'Email address is not verified' in error_message:
                return {
                    'success': False,
                    'error': 'Email address not verified',
                    'message': 'The sender or recipient email is not verified in SES. Please verify email addresses.'
                }
            elif 'Sending rate exceeded' in error_message:
                return {
                    'success': False,
                    'error': 'Rate limit exceeded',
                    'message': 'Email sending rate limit exceeded. Please try again later.'
                }
        
        return {
            'success': False,
            'error': error_message,
            'message': f"Failed to send email: {error_message}"
        }
        
    except Exception as e:
        logger.error(f"Unexpected error sending email: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'message': f"Unexpected error: {str(e)}"
        }

def create_preview_email_body(markdown_table, total_rows, processing_time):
    """Create email body for preview mode results"""
    
    body_html = f"""
    <html>
    <head>
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .header {{ background-color: #f8f9fa; padding: 20px; border-radius: 5px; margin-bottom: 20px; }}
            table {{ border-collapse: collapse; width: 100%; margin: 20px 0; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: left; }}
            th {{ background-color: #f2f2f2; font-weight: bold; }}
            .footer {{ margin-top: 30px; padding-top: 20px; border-top: 1px solid #ddd; color: #666; font-size: 0.9em; }}
            .logo {{ color: #007bff; font-weight: bold; }}
            pre {{ background-color: #f5f5f5; padding: 10px; border-radius: 5px; overflow-x: auto; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h2>Perplexity Validation Preview from <span class="logo">Eliyahu.AI</span></h2>
            <p>Preview of first row validation results</p>
        </div>
        
        <p>This is a preview showing validation results for the first row of your data.</p>
        
        <p><b>Total rows in file:</b> {total_rows}<br>
        <b>Processing time for first row:</b> {processing_time:.2f} seconds<br>
        <b>Estimated time for full validation:</b> {(total_rows * processing_time):.1f} seconds</p>
        
        <h3>Preview Results</h3>
        <pre>{markdown_table}</pre>
        
        <p>To validate the complete dataset, please use the normal mode.</p>
        
        <div class="footer">
            <p>Best regards,<br>
            The <a href="https://www.eliyahu.ai">Eliyahu.AI</a> Team</p>
        </div>
    </body>
    </html>
    """
    
    return body_html 