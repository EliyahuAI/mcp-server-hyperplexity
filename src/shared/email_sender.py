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

def get_excel_features_text():
    """Common language about Excel file features used in all validation emails."""
    return ""  # Removed to avoid duplication in email body
from datetime import datetime
import re
import logging

logger = logging.getLogger(__name__)

# Email configuration
SENDER = "eliyahu@eliyahu.ai"
BCC_ADDRESS = "ppp@eliyahu.ai"  # For tracking/analytics
CHARSET = "UTF-8"


def generate_receipt(session_id: str, email: str, amount: float, raw_cost: float, 
                    multiplier: float, transaction_details: dict) -> str:
    """Generate HTML receipt for validation charges"""
    try:
        receipt_date = datetime.now().strftime("%B %d, %Y at %I:%M %p UTC")
        receipt_content = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
                .receipt {{ max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .header {{ text-align: center; border-bottom: 2px solid #4a90e2; padding-bottom: 20px; margin-bottom: 30px; }}
                .logo {{ font-size: 24px; font-weight: bold; color: #4a90e2; margin-bottom: 5px; }}
                .receipt-title {{ font-size: 18px; color: #666; }}
                .receipt-info {{ margin-bottom: 30px; }}
                .info-row {{ display: flex; justify-content: space-between; margin: 8px 0; }}
                .label {{ font-weight: bold; color: #333; }}
                .value {{ color: #666; }}
                .cost-breakdown {{ background: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0; }}
                .cost-row {{ display: flex; justify-content: space-between; margin: 5px 0; }}
                .total-row {{ border-top: 2px solid #ddd; padding-top: 10px; font-weight: bold; font-size: 16px; }}
                .footer {{ text-align: center; margin-top: 30px; padding-top: 20px; border-top: 1px solid #eee; color: #888; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="receipt">
                <div class="header">
                    <div class="logo">HYPERPLEXITY VALIDATION</div>
                    <div class="receipt-title">Payment Receipt</div>
                </div>
                
                <div class="receipt-info">
                    <div class="info-row">
                        <span class="label">Receipt Date:</span>
                        <span class="value">{receipt_date}</span>
                    </div>
                    <div class="info-row">
                        <span class="label">Session ID:</span>
                        <span class="value">{session_id}</span>
                    </div>
                    <div class="info-row">
                        <span class="label">Customer Email:</span>
                        <span class="value">{email}</span>
                    </div>
                    <div class="info-row">
                        <span class="label">Service:</span>
                        <span class="value">Table Validation</span>
                    </div>
                </div>
                
                <div class="cost-breakdown">
                    <h3 style="margin-top: 0; color: #333;">Cost Breakdown</h3>
                    <div class="cost-row">
                        <span>Raw Processing Cost:</span>
                        <span>${raw_cost:.6f}</span>
                    </div>
                    <div class="cost-row">
                        <span>Domain Multiplier:</span>
                        <span>{multiplier:.1f}x</span>
                    </div>
                    <div class="cost-row">
                        <span>Rows Processed:</span>
                        <span>{transaction_details.get('rows_processed', 'N/A')}</span>
                    </div>
                    <div class="cost-row total-row">
                        <span>Total Charged:</span>
                        <span>${amount:.4f}</span>
                    </div>
                </div>
                
                <div class="footer">
                    <p>Thank you for using Hyperplexity!</p>
                    <p>For support, contact: eliyahu@eliyahu.ai</p>
                    <p>This receipt is for your records.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        return receipt_content.strip()
        
    except Exception as e:
        logger.error(f"Error generating receipt: {e}")
        # Return simple text receipt as fallback
        return f"""
HYPERPLEXITY VALIDATION RECEIPT
==============================
Session: {session_id}
Date: {datetime.now().isoformat()}
Email: {email}

Service: Table Validation
Raw Processing Cost: ${raw_cost:.6f}
Domain Multiplier: {multiplier}x
Total Charged: ${amount:.4f}

Thank you for using Hyperplexity!
        """.strip()


def send_credit_confirmation_email(email_address: str, amount_purchased: float, new_balance: float, transaction_id: str) -> dict:
    """Send confirmation email for credit purchase."""
    try:
        # Create message
        message = MIMEMultipart()
        message["From"] = SENDER
        message["To"] = email_address
        message["Subject"] = f"💳 Credits Added - ${amount_purchased:.2f} - Hyperplexity"
        
        # Create email body
        purchase_date = datetime.now().strftime("%B %d, %Y at %I:%M %p UTC")
        
        body_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f5f5f5; }}
                .email-container {{ max-width: 600px; margin: 0 auto; background: white; border-radius: 8px; overflow: hidden; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #4a90e2, #357abd); color: white; padding: 30px; text-align: center; }}
                .header h1 {{ margin: 0; font-size: 24px; }}
                .content {{ padding: 30px; }}
                .purchase-info {{ background: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0; }}
                .info-row {{ display: flex; justify-content: space-between; margin: 10px 0; }}
                .label {{ font-weight: bold; color: #333; }}
                .value {{ color: #666; }}
                .balance-highlight {{ background: #e8f5e8; padding: 15px; border-radius: 5px; text-align: center; margin: 20px 0; }}
                .balance-amount {{ font-size: 24px; font-weight: bold; color: #27ae60; }}
                .footer {{ background: #f8f9fa; padding: 20px; text-align: center; color: #666; font-size: 12px; }}
            </style>
        </head>
        <body>
            <div class="email-container">
                <div class="header">
                    <h1>🎉 Credits Successfully Added!</h1>
                </div>
                
                <div class="content">
                    <p>Thank you for your purchase! Your credits have been successfully added to your Hyperplexity account.</p>
                    
                    <div class="purchase-info">
                        <h3 style="margin-top: 0; color: #333;">Purchase Details</h3>
                        <div class="info-row">
                            <span class="label">Purchase Date:</span>
                            <span class="value">{purchase_date}</span>
                        </div>
                        <div class="info-row">
                            <span class="label">Amount Purchased:</span>
                            <span class="value">${amount_purchased:.2f}</span>
                        </div>
                        <div class="info-row">
                            <span class="label">Transaction ID:</span>
                            <span class="value">{transaction_id}</span>
                        </div>
                    </div>
                    
                    <div class="balance-highlight">
                        <p style="margin: 0; color: #333;">Your Current Balance:</p>
                        <div class="balance-amount">${new_balance:.4f}</div>
                    </div>
                    
                    <p>Your credits are ready to use! You can now process table validations and the costs will be automatically deducted from your account balance.</p>
                    
                    <p><strong>What's Next?</strong></p>
                    <ul>
                        <li>Upload your Excel or CSV files for validation</li>
                        <li>Generate AI-powered configuration files</li>
                        <li>Monitor your usage and balance in real-time</li>
                    </ul>
                </div>
                
                <div class="footer">
                    <p>Thank you for using Hyperplexity!</p>
                    <p>For support, contact: eliyahu@eliyahu.ai</p>
                    <p>Keep this email for your records.</p>
                </div>
            </div>
        </body>
        </html>
        """
        
        # Attach HTML body
        part = MIMEText(body_html, 'html', CHARSET)
        message.attach(part)
        
        # Send email via SES
        ses_client = boto3.client('ses')
        
        response = ses_client.send_raw_email(
            Source=SENDER,
            Destinations=[email_address, BCC_ADDRESS],
            RawMessage={
                'Data': message.as_string()
            }
        )
        
        message_id = response['MessageId']
        logger.info(f"Credit confirmation email sent successfully! Message ID: {message_id}")
        
        return {
            'success': True,
            'message_id': message_id,
            'message': f"Credit confirmation sent to {email_address}"
        }
        
    except Exception as e:
        logger.error(f"Failed to send credit confirmation email: {str(e)}")
        return {
            'success': False,
            'error': str(e),
            'message': f"Failed to send confirmation to {email_address}"
        }


def send_validation_results_email(email_address, excel_content, config_content, enhanced_excel_content, input_filename, config_filename, enhanced_excel_filename, session_id, summary_data, processing_time=None, reference_pin=None, metadata=None, preview_email=False, billing_info=None, config_id=None):
    """
    Send validation results via email with individual file attachments
    
          Args:
          email_address: Recipient email
          excel_content: Bytes content of the original Excel file
          config_content: Bytes content of the config JSON file
          enhanced_excel_content: Bytes content of the enhanced Excel file
          input_filename: Original input filename
          config_filename: Config filename
          enhanced_excel_filename: Enhanced Excel filename with timestamp
          session_id: Unique session identifier
          summary_data: Dictionary with validation summary info
          processing_time: Optional processing time in seconds
          reference_pin: Reference PIN for the validation
          metadata: Optional metadata including token usage
          billing_info: Optional billing information for receipt generation
          config_id: Configuration ID to reference instead of exposing filename
        
    Returns:
        dict: Response with status and message ID
    """
    try:
        # Create message with reference pin
        message = MIMEMultipart()
        message["From"] = SENDER
        message["To"] = email_address
        
        # Clean filename by removing excel_ prefix and VerifiedX suffix
        def clean_filename(filename):
            if not filename:
                return "Table"
            # Remove file extension
            base_name = filename.rsplit('.', 1)[0] if '.' in filename else filename
            # Remove excel_ prefix
            if base_name.startswith('excel_'):
                base_name = base_name[6:]
            # Remove VerifiedX suffix (where X is a number)
            import re
            base_name = re.sub(r'_Verified\d*$', '', base_name)
            return base_name or "Table"
        
        # Create subject line based on email type
        base_filename = clean_filename(input_filename)
        subject_type = "Preview Results" if preview_email else "Validation Results"
        
        # Extract version from config filename (e.g., "RatioCompetitiveIntelligence_Verified1_input_config_V03.json" -> "v3")
        config_version = ""
        if config_filename:
            import re
            version_match = re.search(r'_V(\d+)\.json$', config_filename)
            if version_match:
                config_version = f" (v{int(version_match.group(1))})"
        
        if reference_pin:
            message["Subject"] = f"🟩 {subject_type}{config_version} - {base_filename} #{reference_pin}"
        else:
            message["Subject"] = f"🟩 {subject_type}{config_version} - {base_filename}"
        
        # Extract summary data
        total_rows = summary_data.get('total_rows', 0)
        fields_validated = summary_data.get('fields_validated', [])
        confidence_distribution = summary_data.get('confidence_distribution', {})
        
        # Extract token usage from metadata
        token_usage = None
        if metadata and 'token_usage' in metadata:
            token_usage = metadata['token_usage']
        
        # Create clean email body following style guide
        body_html = create_validation_results_email_body(
            session_id, 
            total_rows, 
            fields_validated, 
            confidence_distribution,
            processing_time,
            reference_pin,
            token_usage,
            enhanced_excel_filename,
            input_filename,
            config_filename,
            preview_email,
            config_id
        )
        
        # Attach HTML body
        part = MIMEText(body_html, 'html', CHARSET)
        message.attach(part)
        
        # Attach enhanced Excel file first (this is the main result)
        part = MIMEApplication(enhanced_excel_content)
        part.add_header("Content-Disposition", f'attachment; filename="{enhanced_excel_filename}"')
        message.attach(part)
        
        # Attach original input file
        part = MIMEApplication(excel_content)
        part.add_header("Content-Disposition", f'attachment; filename="{input_filename}"')
        message.attach(part)
        
        # Note: Config JSON file attachment removed - only provide configuration code for reuse
        
        # Generate and attach receipt if there are charges
        if billing_info and billing_info.get('amount_charged', 0) > 0 and not preview_email:
            try:
                transaction_details = {
                    'rows_processed': summary_data.get('total_rows', 0),
                    'description': f"Full validation - {summary_data.get('total_rows', 0)} rows processed",
                    'session_id': session_id
                }
                
                receipt_html = generate_receipt(
                    session_id=session_id,
                    email=email_address,
                    amount=billing_info.get('amount_charged', 0),
                    raw_cost=billing_info.get('raw_cost', 0),
                    multiplier=billing_info.get('multiplier', 1.0),
                    transaction_details=transaction_details
                )
                
                # Create receipt filename
                receipt_filename = f"receipt_{session_id}.html"
                
                # Attach receipt as HTML file
                receipt_part = MIMEApplication(receipt_html.encode('utf-8'))
                receipt_part.add_header("Content-Disposition", f'attachment; filename="{receipt_filename}"')
                receipt_part.add_header("Content-Type", "text/html; charset=utf-8")
                message.attach(receipt_part)
                
                logger.info(f"Receipt attached to email for session {session_id}: ${billing_info.get('amount_charged', 0):.4f}")
                
            except Exception as e:
                logger.error(f"Failed to generate/attach receipt for session {session_id}: {e}")
                # Don't fail the email if receipt generation fails
        
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
            attachments_list = [enhanced_excel_filename, input_filename, config_filename]
            
            # Add receipt to attachments list if billing info was provided and charges applied
            if billing_info and billing_info.get('amount_charged', 0) > 0 and not preview_email:
                receipt_filename = f"receipt_{session_id}.html"
                attachments_list.append(receipt_filename)
            
            email_metadata = {
                'MessageID': message_id,
                'SessionID': session_id,
                'Recipient': email_address,
                'Timestamp': datetime.utcnow().isoformat(),
                'Subject': message["Subject"],
                'TotalRows': total_rows,
                'FieldsValidated': fields_validated,
                'ConfidenceDistribution': confidence_distribution,
                'Attachments': attachments_list,
                'BillingInfo': billing_info if billing_info else None,
                'PreviewEmail': preview_email
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


def create_validation_results_email_body(session_id, total_rows, fields_validated, confidence_distribution, processing_time=None, reference_pin=None, token_usage=None, enhanced_excel_filename=None, input_filename=None, config_filename=None, preview_email=False, config_id=None):
    """Create clean validation results email body following Eliyahu.AI style guide"""
    
    # Format fields list
    if fields_validated:
        if len(fields_validated) <= 5:
            fields_html = ", ".join(fields_validated)
        else:
            fields_html = ", ".join(fields_validated[:5]) + f" and {len(fields_validated) - 5} more"
    else:
        fields_html = "No fields processed"
    
    # Format confidence distribution
    confidence_html = ""
    total_validations = sum(confidence_distribution.values())
    for level, count in confidence_distribution.items():
        if count > 0:
            percentage = (count / total_validations * 100) if total_validations > 0 else 0
            emoji = "🟢" if level == "HIGH" else "🟡" if level == "MEDIUM" else "🔴"
            confidence_html += f"<li>{emoji} <b>{level}:</b> {count} fields ({percentage:.1f}%)</li>"
    
    if not confidence_html:
        confidence_html = "<li>No confidence data available</li>"
    
    # Format processing time
    time_info = ""
    if processing_time:
        if processing_time < 60:
            time_info = f"<p><b>Processing time:</b> {processing_time:.1f} seconds</p>"
        else:
            minutes = processing_time / 60
            time_info = f"<p><b>Processing time:</b> {minutes:.1f} minutes</p>"
    
    # Token usage info removed from user-facing emails
    token_info = ""
    
    # Format reference pin
    pin_info = ""
    if reference_pin:
        pin_info = f"<p><b>Reference #:</b> {reference_pin}</p>"
    
    # Preview email notice
    preview_notice = ""
    if preview_email:
        preview_notice = f"""
        <div style="background: #FFF3CD; border: 1px solid #FFEAA7; padding: 15px; border-radius: 6px; margin: 15px 0;">
            <p><b>📋 Preview Results</b></p>
            <p>This email contains validation results for a preview of your data ({total_rows} rows). To process your full table, please use the Hyperplexity Tool with your original table and Configuration ID: {config_id or 'N/A'}.</p>
        </div>
        """
    
    # Create email body following Eliyahu.AI style guide
    body_html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <title>Validation Complete - Hyperplexity Table Validation</title>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                line-height: 1.6;
                color: #000000;
                max-width: 600px;
                margin: 0 auto;
                padding: 20px;
                background-color: #ffffff;
            }}
            .header {{
                background: #000000;
                color: white;
                padding: 30px;
                text-align: center;
                border-radius: 8px 8px 0 0;
            }}
            .content {{
                background: #ffffff;
                padding: 30px;
                border: 1px solid #E5E5E5;
                border-radius: 0 0 8px 8px;
            }}
            .summary {{
                background: #ffffff;
                border: 1px solid #E5E5E5;
                border-left: 4px solid #00FF00;
                padding: 20px;
                border-radius: 8px;
                margin: 20px 0;
            }}
            .confidence {{
                background: #F8F9FA;
                border: 1px solid #E5E5E5;
                padding: 15px;
                border-radius: 8px;
                margin: 15px 0;
            }}
            .confidence ul {{
                margin: 10px 0;
                padding-left: 20px;
            }}
            .confidence li {{
                margin: 5px 0;
            }}
            .attachments {{
                background: #ffffff;
                border: 2px solid #00FF00;
                padding: 20px;
                border-radius: 8px;
                margin: 25px 0;
                text-align: center;
            }}
            .attachments h3 {{
                color: #000000;
                margin-top: 0;
            }}
            .attachment-list {{
                list-style: none;
                padding: 0;
                margin: 15px 0;
            }}
            .attachment-list li {{
                background: #F8F9FA;
                border: 1px solid #E5E5E5;
                padding: 12px;
                margin: 8px 0;
                border-radius: 6px;
                border-left: 4px solid #00FF00;
            }}
            .primary-file {{
                background: #000000;
                color: white;
                font-weight: bold;
            }}
            .footer {{
                text-align: center;
                color: #666666;
                font-size: 14px;
                margin-top: 32px;
                padding-top: 20px;
                border-top: 1px solid #E5E5E5;
            }}
            .logo {{
                color: #00FF00;
                font-weight: bold;
            }}
            a {{
                color: #000000;
                text-decoration: none;
                border-bottom: 2px solid #00FF00;
            }}
            a:hover {{
                background-color: #00FF00;
                color: #000000;
            }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>Validation Complete</h1>
            <p>Hyperplexity Table Validation Results</p>
        </div>
        
        <div class="content">
            <div class="summary">
                <h2>Your Results Are Ready</h2>
                {preview_notice}
                <p><b>Configuration ID:</b> {config_id or 'N/A'}</p>
                <p><b>Total rows processed:</b> {total_rows:,}</p>
                {pin_info}
                <p><b>Fields validated:</b> {len(fields_validated)}</p>
                <p><small>({fields_html})</small></p>
                {time_info}
                
                <div class="confidence">
                    <p><b>Confidence Distribution:</b></p>
                    <ul>
                        {confidence_html}
                    </ul>
                </div>
            </div>
            
            <div class="attachments">
                <h3>📎 Attached Files</h3>
                <ul class="attachment-list">
                    <li class="primary-file">
                        📊 <b>{enhanced_excel_filename or 'Validated_Results.xlsx'}</b> (Updated Page)<br>
                        <small>Color-coded validation results - updates values when we found better information</small>
                    </li>
                    <li>
                        📄 <b>{input_filename or 'Original_Input.xlsx'}</b> (Original Page)<br>
                        <small>Fact-check version of your table without updates - color-coded by confidence</small>
                    </li>
                </ul>
                <p><strong>Configuration Code:</strong> {config_id or 'N/A'}</p>
                <p><small>Save this code to keep the same settings for future validations. For full validations, use the Updated page with this configuration to update your table.</small></p>
            </div>
            
            <h3>Understanding Your Results</h3>
            <p>Both files are color-coded by confidence level:</p>
            <p><b>🟢 Green = HIGH confidence | 🟡 Yellow = MEDIUM confidence | 🔴 Red = LOW confidence</b></p>
            
            <p><b>Visit <a href="https://eliyahu.ai/hyperplexity">eliyahu.ai/hyperplexity</a></b> to process more tables or refine your configuration.</p>
            
            <p><b>Questions or need help?</b> Simply reply to this email and our team will assist you.</p>
        </div>
        
        <div class="footer">
            <p>Best regards,<br>
            The <a href="https://eliyahu.ai/hyperplexity">Eliyahu.AI</a> Team</p>
            
            <p><small>This email was sent because you requested validation results. 
            Your data is processed securely and is not stored beyond the validation session.</small></p>
        </div>
    </body>
    </html>
    """
    
    return body_html


def send_validation_code_email(email_address: str, validation_code: str):
    """
    Send email validation code to user.
    
    Args:
        email_address: Recipient email
        validation_code: 6-digit numerical code
        
    Returns:
        dict: Response with status and message ID
    """
    try:
        # Create message
        message = MIMEMultipart()
        message["From"] = SENDER
        message["To"] = email_address
        message["Subject"] = "Perplexity Validator - Email Verification Code"
        
        # Create email body with validation code
        body_html = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <meta charset="UTF-8">
            <title>Email Verification - Perplexity Validator</title>
            <style>
                body {{
                    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                    line-height: 1.6;
                    color: #000000;
                    max-width: 600px;
                    margin: 0 auto;
                    padding: 20px;
                    background-color: #ffffff;
                }}
                .header {{
                    background: #000000;
                    color: white;
                    padding: 30px;
                    text-align: center;
                    border-radius: 8px 8px 0 0;
                }}
                .content {{
                    background: #ffffff;
                    padding: 30px;
                    border: 1px solid #E5E5E5;
                    border-radius: 0 0 8px 8px;
                }}
                .verification-code {{
                    background: #F8F9FA;
                    border: 2px solid #00FF00;
                    color: #000000;
                    font-size: 32px;
                    font-weight: bold;
                    padding: 20px;
                    text-align: center;
                    border-radius: 8px;
                    letter-spacing: 8px;
                    margin: 20px 0;
                    font-family: 'Courier New', monospace;
                    position: relative;
                    transition: all 0.3s ease;
                }}
                .verification-code.hidden {{
                    background: #E5E5E5;
                    border-color: #E5E5E5;
                    color: #E5E5E5;
                    user-select: none;
                }}
                .verification-code.hidden::after {{
                    content: '●●●●●●';
                    position: absolute;
                    top: 50%;
                    left: 50%;
                    transform: translate(-50%, -50%);
                    color: #666666;
                    font-size: 24px;
                    letter-spacing: 12px;
                }}
                .code-notice {{
                    background: #FFFFFF;
                    border: 1px solid #00FF00;
                    color: #000000;
                    padding: 12px 20px;
                    border-radius: 8px;
                    margin: 15px 0;
                    text-align: center;
                    border-left: 4px solid #00FF00;
                    font-size: 14px;
                }}
                .code-notice.hidden {{
                    display: none;
                }}
                .privacy-notice {{
                    background: #FFFFFF;
                    border: 1px solid #00FF00;
                    color: #000000;
                    padding: 25px;
                    border-radius: 8px;
                    margin: 25px 0;
                    border-left: 4px solid #00FF00;
                    text-align: center;
                }}
                .privacy-link {{
                    color: #000000;
                    text-decoration: none;
                    border-bottom: 2px solid #00FF00;
                    font-weight: bold;
                }}
                .privacy-link:hover {{
                    background-color: #00FF00;
                    color: #000000;
                }}
                .acceptance-warning {{
                    background: #FFFFFF;
                    border: 2px solid #00FF00;
                    color: #000000;
                    padding: 15px;
                    border-radius: 8px;
                    margin: 15px 0;
                    text-align: center;
                    font-size: 14px;
                    border-left: 6px solid #00FF00;
                }}
                .privacy-link-container {{
                    text-align: center;
                    margin: 20px 0;
                }}
                .privacy-button {{
                    display: inline-block;
                    background: #000000;
                    color: white;
                    text-decoration: none;
                    padding: 15px 30px;
                    border-radius: 8px;
                    font-size: 16px;
                    font-weight: bold;
                    border: 2px solid #00FF00;
                    transition: all 0.3s ease;
                }}
                .privacy-button:hover {{
                    background: #00FF00;
                    color: #000000;
                    text-decoration: none;
                }}

                .warning {{
                    background: #FFFFFF;
                    border: 1px solid #E5E5E5;
                    color: #000000;
                    padding: 15px;
                    border-radius: 8px;
                    margin: 20px 0;
                    border-left: 4px solid #00FF00;
                }}
                .footer {{
                    text-align: center;
                    color: #666666;
                    font-size: 14px;
                    margin-top: 32px;
                    padding-top: 20px;
                    border-top: 1px solid #E5E5E5;
                }}
                .logo {{
                    color: #00FF00;
                    font-weight: bold;
                }}
            </style>

        </head>
        <body>
            <div class="header">
                <h1>🔐 Email Verification</h1>
                <p>Perplexity Validator Access Request</p>
            </div>
            
            <div class="content">
                <h2>Verify Your Email Address</h2>
                <p>You have requested access to the Perplexity Validator service. Use the verification code below to complete your registration:</p>
                
                <div class="verification-code">
                    {validation_code}
                </div>
                
                <div class="privacy-notice">
                    <p><strong>📋 Privacy Notice Acceptance Required</strong></p>
                    <p><strong>⚠️ IMPORTANT: Entering and submitting this verification code in the Perplexity Validator interface constitutes your explicit acceptance of our <a href="https://eliyahu.ai/privacy-notice" target="_blank" class="privacy-link">Privacy Notice</a> and consent to data processing.</strong></p>
                    
                    <div class="privacy-link-container">
                        <a href="https://eliyahu.ai/privacy-notice" target="_blank" class="privacy-button">
                            📖 Read Our Privacy Notice
                        </a>
                    </div>
                    
                    <p class="acceptance-warning"><strong>🔒 By proceeding with email verification, you acknowledge that you have read and agree to our Privacy Notice.</strong></p>
                </div>
                
                <div class="warning">
                    <strong>⏰ Important:</strong> This verification code will expire in <strong>10 minutes</strong>.
                    You have up to 3 attempts to enter the correct code.
                </div>
                
                <h3>How to Use Your Code:</h3>
                <ol>
                    <li>Copy the 6-digit verification code above</li>
                    <li>Return to the Perplexity Validator interface</li>
                    <li>Enter the code and click "Verify Email"</li>
                </ol>
                
                <p><strong>If you didn't request this verification,</strong> you can safely ignore this email. The code will expire automatically.</p>
                
                <p><strong>Need help?</strong> Reply to this email and our team will assist you.</p>
            </div>
            
            <div class="footer">
                <p>Best regards,<br>
                The <span class="logo">Eliyahu.AI</span> Team</p>
                
                <p><small>This is an automated security email for Perplexity Validator access verification.</small></p>
            </div>
        </body>
        </html>
        """
        
        # Attach HTML body
        part = MIMEText(body_html, 'html', CHARSET)
        message.attach(part)
        
        # Send email via SES
        ses_client = boto3.client('ses')
        
        response = ses_client.send_raw_email(
            Source=SENDER,
            Destinations=[email_address],
            RawMessage={
                'Data': message.as_string()
            }
        )
        
        message_id = response['MessageId']
        logger.info(f"Validation email sent successfully! Message ID: {message_id}")
        
        return {
            'success': True,
            'message_id': message_id,
            'message': f"Verification code sent to {email_address}"
        }
        
    except ClientError as e:
        error_message = e.response['Error']['Message']
        logger.error(f"SES error sending validation email: {error_message}")
        
        return {
            'success': False,
            'error': error_message,
            'message': f"Failed to send verification email: {error_message}"
        }
        
    except Exception as e:
        logger.error(f"Unexpected error sending validation email: {str(e)}")
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