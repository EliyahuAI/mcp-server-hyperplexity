import sys
import json
import zipfile

# Add src to path
sys.path.insert(0, 'src')

from email_sender import send_validation_results_email

def send_existing_results_email(zip_file_path, recipient_email):
    """Send existing results ZIP file via email"""
    
    print(f"Sending existing results to {recipient_email}")
    print("="*60)
    
    # Read the ZIP file
    with open(zip_file_path, 'rb') as f:
        zip_content = f.read()
    
    print(f"ZIP file size: {len(zip_content):,} bytes")
    
    # Extract summary data from ZIP
    summary_data = {
        'total_rows': 0,
        'fields_validated': [],
        'confidence_distribution': {}
    }
    
    try:
        with zipfile.ZipFile(zip_file_path, 'r') as zip_file:
            if 'validation_results.json' in zip_file.namelist():
                results_json = json.loads(zip_file.read('validation_results.json'))
                summary = results_json.get('summary', {})
                summary_data['total_rows'] = summary.get('total_rows', 0)
                summary_data['fields_validated'] = summary.get('fields_validated', [])
                summary_data['confidence_distribution'] = summary.get('confidence_distribution', {})
                session_id = results_json.get('session_id', 'unknown')
                
                print(f"\nExtracted summary:")
                print(f"  Session ID: {session_id}")
                print(f"  Total rows: {summary_data['total_rows']}")
                print(f"  Fields: {len(summary_data['fields_validated'])}")
                print(f"  Confidence: {summary_data['confidence_distribution']}")
    except Exception as e:
        print(f"Warning: Couldn't extract summary: {e}")
        session_id = "manual-send"
    
    # Send email
    print(f"\nSending email...")
    
    try:
        result = send_validation_results_email(
            email_address=recipient_email,
            zip_content=zip_content,
            session_id=session_id,
            summary_data=summary_data,
            processing_time=None  # Unknown for existing results
        )
        
        print(f"\nResult:")
        print(f"  Success: {result['success']}")
        print(f"  Message: {result['message']}")
        
        if result['success']:
            print(f"\n✅ Email sent successfully!")
            if 'message_id' in result:
                print(f"  Message ID: {result['message_id']}")
        else:
            print(f"\n❌ Failed to send email")
            
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    # Configuration
    ZIP_FILE = "test_results_37322e06.zip"
    RECIPIENT = "eliyahu@eliyahu.ai"
    
    print("Manual Email Sender for Existing Results")
    print(f"ZIP file: {ZIP_FILE}")
    print(f"Recipient: {RECIPIENT}")
    
    send_existing_results_email(ZIP_FILE, RECIPIENT) 