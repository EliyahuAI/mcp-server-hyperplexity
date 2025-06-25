import os
import shutil
from pathlib import Path

# Files to move to temp_unnecessary_files
TEST_FILES = [
    # CloudWatch log checkers
    "check_cloudwatch_logs.py",
    "check_all_lambdas_logs.py",
    
    # Lambda testing files
    "check_lambda_config.py",
    "test_lambda_directly.py",
    
    # API testing files
    "test_api_directly.py",
    
    # Email testing files
    "test_email_functionality.py",
    "test_ses_directly.py",
    "test_10_rows_email.py",
    "send_existing_results.py",
    
    # S3 checking files
    "check_s3_results.py",
    "check_test_session.py",
    "download_test_results.py",
    
    # IAM fix script
    "fix_lambda_ses_permissions.py",
    
    # Downloaded test results
    "test_results_37322e06.zip",
    
    # Progress tracking
    "progress_log.txt"
]

def cleanup_files():
    """Move test files to temp_unnecessary_files directory"""
    
    # Create temp directory if it doesn't exist
    temp_dir = Path("temp_unnecessary_files")
    temp_dir.mkdir(exist_ok=True)
    
    print("Moving test files to temp_unnecessary_files/")
    print("="*60)
    
    moved_count = 0
    for file_name in TEST_FILES:
        if os.path.exists(file_name):
            try:
                dest_path = temp_dir / file_name
                shutil.move(file_name, dest_path)
                print(f"✓ Moved: {file_name}")
                moved_count += 1
            except Exception as e:
                print(f"✗ Error moving {file_name}: {e}")
        else:
            print(f"- Skipped: {file_name} (not found)")
    
    print(f"\nMoved {moved_count} files to temp_unnecessary_files/")
    
    # Check for any other test files that might have been created
    print("\nChecking for other test files...")
    test_patterns = ["test_*.py", "check_*.py", "debug_*.py", "fix_*.py"]
    
    other_files = []
    for pattern in test_patterns:
        for file_path in Path(".").glob(pattern):
            if file_path.name not in TEST_FILES and file_path.is_file():
                other_files.append(file_path.name)
    
    if other_files:
        print(f"\nFound {len(other_files)} other test files:")
        for file_name in other_files:
            print(f"  - {file_name}")
        print("\nConsider moving these manually if they're temporary.")
    
    return moved_count

if __name__ == "__main__":
    print("Perplexity Validator Cleanup")
    print("Moving test and temporary files\n")
    
    cleanup_files()
    
    print("\n✅ Cleanup complete!")
    print("\nNext steps:")
    print("1. Review any remaining test files")
    print("2. Commit the email functionality fixes")
    print("3. Run final test with all rows") 