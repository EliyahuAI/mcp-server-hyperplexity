#!/usr/bin/env python3
"""
Demo Session Manager

Manages session lifecycle and S3 interactions for demo testing.
Provides utilities for creating test sessions, checking status, and downloading results.

Usage:
    from demo_session_manager import DemoSessionManager

    manager = DemoSessionManager()
    session_id = manager.create_test_session("product_validation", "test@example.com")
    status = manager.check_session_status("test@example.com", session_id)
    manager.download_results("test@example.com", session_id, "./output")
"""

import boto3
import json
import time
import sys
from datetime import datetime
from typing import Dict, Optional, Tuple, List
from pathlib import Path


class DemoSessionManager:
    """Manages demo session lifecycle and S3 interactions"""

    def __init__(self, bucket_name: str = "hyperplexity-storage-dev", region: str = "us-east-1"):
        """
        Initialize the demo session manager

        Args:
            bucket_name: S3 bucket name (default: hyperplexity-storage-dev)
            region: AWS region (default: us-east-1)
        """
        self.bucket_name = bucket_name
        self.region = region
        self.s3_client = boto3.client('s3', region_name=region)

    def _get_session_path(self, email: str, session_id: str) -> str:
        """
        Generate session storage path following the standard structure
        Format: users/{email}/sessions/{session_id}/

        Args:
            email: User email address
            session_id: Session identifier

        Returns:
            S3 path prefix for the session
        """
        # Extract domain and create safe email prefix
        domain = email.split('@')[-1] if '@' in email else 'unknown'
        email_prefix = email.split('@')[0].replace('.', '_').replace('+', '_plus_')[:20]

        # Use session_id directly as folder name
        return f"results/{domain}/{email_prefix}/{session_id}/"

    def create_test_session(self, demo_name: str, email: str) -> str:
        """
        Generate unique test session ID for demo testing

        Args:
            demo_name: Name/identifier for the demo (e.g., "product_validation")
            email: Test user email address

        Returns:
            Generated session ID (format: session_demo_YYYYMMDD_HHMMSS_XXXXXXXX)

        Example:
            >>> manager = DemoSessionManager()
            >>> session_id = manager.create_test_session("product_validation", "test@example.com")
            >>> print(session_id)
            session_demo_20251010_143022_abc12345
        """
        # Generate timestamp-based session ID with demo prefix
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # Generate unique suffix (8 characters)
        import hashlib
        unique_str = f"{demo_name}_{email}_{timestamp}_{time.time()}"
        unique_hash = hashlib.md5(unique_str.encode()).hexdigest()[:8]

        session_id = f"session_demo_{timestamp}_{unique_hash}"

        print(f"[SUCCESS] Generated test session ID: {session_id}")
        print(f"[INFO] Demo name: {demo_name}")
        print(f"[INFO] Test email: {email}")

        return session_id

    def check_session_status(self, email: str, session_id: str) -> Dict:
        """
        Check session state from S3 by reading session_info.json

        Args:
            email: User email address
            session_id: Session identifier

        Returns:
            Dictionary containing session status information including:
            - exists: Whether the session exists
            - session_info: Full session info data (if exists)
            - current_version: Latest config version
            - has_preview: Whether preview results exist
            - has_validation: Whether validation results exist
            - error: Error message (if any)

        Example:
            >>> status = manager.check_session_status("test@example.com", session_id)
            >>> if status['exists']:
            ...     print(f"Session has {status['current_version']} config versions")
            ...     print(f"Preview complete: {status['has_preview']}")
            ...     print(f"Validation complete: {status['has_validation']}")
        """
        try:
            session_path = self._get_session_path(email, session_id)
            session_info_key = f"{session_path}session_info.json"

            print(f"[INFO] Checking session status...")
            print(f"[INFO] Session path: {session_path}")

            try:
                # Try to retrieve session_info.json
                response = self.s3_client.get_object(
                    Bucket=self.bucket_name,
                    Key=session_info_key
                )

                session_info = json.loads(response['Body'].read().decode('utf-8'))

                # Extract key information
                current_version = session_info.get('current_version', 0)
                versions = session_info.get('versions', {})

                # Check for preview and validation results in latest version
                has_preview = False
                has_validation = False
                preview_status = None
                validation_status = None

                if current_version > 0 and str(current_version) in versions:
                    version_data = versions[str(current_version)]

                    if 'preview' in version_data:
                        has_preview = True
                        preview_status = version_data['preview'].get('status')

                    if 'validation' in version_data:
                        has_validation = True
                        validation_status = version_data['validation'].get('status')

                print(f"[SUCCESS] Session found")
                print(f"[INFO] Current version: {current_version}")
                print(f"[INFO] Preview results: {has_preview} (status: {preview_status})")
                print(f"[INFO] Validation results: {has_validation} (status: {validation_status})")

                return {
                    'exists': True,
                    'session_info': session_info,
                    'session_path': session_path,
                    'current_version': current_version,
                    'has_preview': has_preview,
                    'has_validation': has_validation,
                    'preview_status': preview_status,
                    'validation_status': validation_status,
                    'versions': versions
                }

            except self.s3_client.exceptions.NoSuchKey:
                print(f"[INFO] Session not found in S3")
                return {
                    'exists': False,
                    'error': 'Session not found in S3',
                    'session_path': session_path
                }

        except Exception as e:
            print(f"[ERROR] Failed to check session status: {e}")
            return {
                'exists': False,
                'error': str(e)
            }

    def verify_results_exist(self, email: str, session_id: str, version: Optional[int] = None) -> Dict:
        """
        Check if results file exists in S3 for the specified session

        Args:
            email: User email address
            session_id: Session identifier
            version: Config version to check (None = latest version)

        Returns:
            Dictionary containing:
            - exists: Whether results exist
            - validation_results: Path to validation results (if exists)
            - enhanced_excel: Path to enhanced Excel file (if exists)
            - preview_results: Path to preview results (if exists)
            - version: Version number checked

        Example:
            >>> result = manager.verify_results_exist("test@example.com", session_id)
            >>> if result['exists']:
            ...     print(f"Results found for version {result['version']}")
            ...     if result['enhanced_excel']:
            ...         print(f"Excel output: {result['enhanced_excel']}")
        """
        try:
            session_path = self._get_session_path(email, session_id)

            # Get session info to determine version
            if version is None:
                status = self.check_session_status(email, session_id)
                if not status['exists']:
                    return {'exists': False, 'error': 'Session not found'}
                version = status['current_version']

            if version == 0:
                return {'exists': False, 'error': 'No config version found'}

            results_folder = f"{session_path}v{version}_results/"

            print(f"[INFO] Checking for results in version {version}")
            print(f"[INFO] Results folder: {results_folder}")

            # List all files in the results folder
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=results_folder
            )

            if 'Contents' not in response or len(response['Contents']) == 0:
                print(f"[INFO] No results found in {results_folder}")
                return {'exists': False, 'version': version, 'error': 'Results folder empty'}

            # Look for specific result files
            validation_results = None
            enhanced_excel = None
            preview_results = None

            for obj in response['Contents']:
                key = obj['Key']
                filename = key.split('/')[-1]

                if filename == 'validation_results.json':
                    validation_results = key
                elif filename == 'preview_results.json':
                    preview_results = key
                elif filename.endswith('_output.xlsx') or filename.endswith('_Output.xlsx') or filename == 'enhanced_validation.xlsx':
                    enhanced_excel = key

            exists = validation_results is not None or preview_results is not None

            if exists:
                print(f"[SUCCESS] Results found for version {version}")
                if validation_results:
                    print(f"[INFO] Validation results: {validation_results}")
                if preview_results:
                    print(f"[INFO] Preview results: {preview_results}")
                if enhanced_excel:
                    print(f"[INFO] Enhanced Excel: {enhanced_excel}")
            else:
                print(f"[WARNING] Results folder exists but no result files found")

            return {
                'exists': exists,
                'version': version,
                'validation_results': validation_results,
                'enhanced_excel': enhanced_excel,
                'preview_results': preview_results,
                'results_folder': results_folder
            }

        except Exception as e:
            print(f"[ERROR] Failed to verify results: {e}")
            return {
                'exists': False,
                'error': str(e)
            }

    def download_results(self, email: str, session_id: str, output_path: str,
                        version: Optional[int] = None) -> bool:
        """
        Download result Excel file from S3 to local path

        Args:
            email: User email address
            session_id: Session identifier
            output_path: Local directory or file path to save results
            version: Config version to download (None = latest version)

        Returns:
            True if download successful, False otherwise

        Example:
            >>> success = manager.download_results(
            ...     "test@example.com",
            ...     session_id,
            ...     "./test_results/output.xlsx"
            ... )
            >>> if success:
            ...     print("Results downloaded successfully")
        """
        try:
            # Verify results exist
            verification = self.verify_results_exist(email, session_id, version)

            if not verification['exists']:
                print(f"[ERROR] No results found for session")
                return False

            # Determine what to download
            download_key = verification.get('enhanced_excel') or verification.get('validation_results')

            if not download_key:
                print(f"[ERROR] No downloadable results found")
                return False

            # Prepare output path
            output_path = Path(output_path)

            # If output_path is a directory, generate filename
            if output_path.is_dir() or not output_path.suffix:
                filename = download_key.split('/')[-1]
                output_path = output_path / filename

            # Create parent directory if needed
            output_path.parent.mkdir(parents=True, exist_ok=True)

            print(f"[INFO] Downloading from S3...")
            print(f"[INFO] S3 key: {download_key}")
            print(f"[INFO] Output path: {output_path}")

            # Get object metadata for progress tracking
            head_response = self.s3_client.head_object(
                Bucket=self.bucket_name,
                Key=download_key
            )
            file_size = head_response['ContentLength']

            print(f"[INFO] File size: {file_size:,} bytes ({file_size / 1024 / 1024:.2f} MB)")

            # Download with progress tracking
            def progress_callback(bytes_transferred):
                percent = (bytes_transferred / file_size) * 100
                mb_transferred = bytes_transferred / 1024 / 1024
                mb_total = file_size / 1024 / 1024
                print(f"\r[INFO] Progress: {percent:.1f}% ({mb_transferred:.2f}/{mb_total:.2f} MB)", end='', flush=True)

            self.s3_client.download_file(
                self.bucket_name,
                download_key,
                str(output_path),
                Callback=progress_callback
            )

            print()  # New line after progress
            print(f"[SUCCESS] Results downloaded successfully to: {output_path}")

            # Also download session_info.json for reference
            session_path = self._get_session_path(email, session_id)
            session_info_key = f"{session_path}session_info.json"
            session_info_path = output_path.parent / f"{session_id}_session_info.json"

            try:
                self.s3_client.download_file(
                    self.bucket_name,
                    session_info_key,
                    str(session_info_path)
                )
                print(f"[INFO] Session info downloaded to: {session_info_path}")
            except Exception as e:
                print(f"[WARNING] Could not download session info: {e}")

            return True

        except Exception as e:
            print(f"[ERROR] Failed to download results: {e}")
            import traceback
            traceback.print_exc()
            return False

    def cleanup_session(self, email: str, session_id: str, dry_run: bool = True) -> Dict:
        """
        Clean up test data from S3 (optional - use with caution!)

        Args:
            email: User email address
            session_id: Session identifier
            dry_run: If True, only list files without deleting (default: True)

        Returns:
            Dictionary containing cleanup summary:
            - files_found: Number of files found
            - files_deleted: Number of files deleted (0 if dry_run)
            - deleted_keys: List of deleted S3 keys (empty if dry_run)

        Example:
            >>> # First, do a dry run to see what would be deleted
            >>> result = manager.cleanup_session("test@example.com", session_id, dry_run=True)
            >>> print(f"Would delete {result['files_found']} files")
            >>>
            >>> # If you're sure, actually delete
            >>> result = manager.cleanup_session("test@example.com", session_id, dry_run=False)
            >>> print(f"Deleted {result['files_deleted']} files")
        """
        try:
            session_path = self._get_session_path(email, session_id)

            print(f"[INFO] {'DRY RUN - ' if dry_run else ''}Cleaning up session: {session_id}")
            print(f"[INFO] Session path: {session_path}")

            # List all objects in the session
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=session_path
            )

            if 'Contents' not in response or len(response['Contents']) == 0:
                print(f"[INFO] No files found to clean up")
                return {
                    'files_found': 0,
                    'files_deleted': 0,
                    'deleted_keys': []
                }

            files = response['Contents']
            print(f"[INFO] Found {len(files)} files to clean up:")

            for obj in files:
                size_kb = obj['Size'] / 1024
                print(f"  - {obj['Key']} ({size_kb:.2f} KB)")

            if dry_run:
                print(f"[INFO] DRY RUN - No files deleted")
                return {
                    'files_found': len(files),
                    'files_deleted': 0,
                    'deleted_keys': [],
                    'dry_run': True
                }

            # Actually delete files
            deleted_keys = []
            for obj in files:
                key = obj['Key']
                self.s3_client.delete_object(
                    Bucket=self.bucket_name,
                    Key=key
                )
                deleted_keys.append(key)
                print(f"[INFO] Deleted: {key}")

            print(f"[SUCCESS] Cleanup complete - deleted {len(deleted_keys)} files")

            return {
                'files_found': len(files),
                'files_deleted': len(deleted_keys),
                'deleted_keys': deleted_keys,
                'dry_run': False
            }

        except Exception as e:
            print(f"[ERROR] Failed to cleanup session: {e}")
            return {
                'files_found': 0,
                'files_deleted': 0,
                'deleted_keys': [],
                'error': str(e)
            }

    def list_all_demo_sessions(self, email: str) -> List[Dict]:
        """
        List all demo sessions for a given email

        Args:
            email: User email address

        Returns:
            List of dictionaries, each containing:
            - session_id: Session identifier
            - session_path: S3 path to session
            - last_modified: Last modification timestamp
            - file_count: Number of files in session

        Example:
            >>> sessions = manager.list_all_demo_sessions("test@example.com")
            >>> for session in sessions:
            ...     print(f"Session: {session['session_id']}")
            ...     print(f"  Files: {session['file_count']}")
            ...     print(f"  Last modified: {session['last_modified']}")
        """
        try:
            domain = email.split('@')[-1] if '@' in email else 'unknown'
            email_prefix = email.split('@')[0].replace('.', '_').replace('+', '_plus_')[:20]
            base_path = f"results/{domain}/{email_prefix}/"

            print(f"[INFO] Listing demo sessions for: {email}")
            print(f"[INFO] Base path: {base_path}")

            # List all session folders
            response = self.s3_client.list_objects_v2(
                Bucket=self.bucket_name,
                Prefix=base_path,
                Delimiter='/'
            )

            sessions = []

            if 'CommonPrefixes' in response:
                for prefix in response['CommonPrefixes']:
                    session_path = prefix['Prefix']
                    session_id = session_path.rstrip('/').split('/')[-1]

                    # Only include demo sessions
                    if session_id.startswith('session_demo_'):
                        # Count files in session
                        file_response = self.s3_client.list_objects_v2(
                            Bucket=self.bucket_name,
                            Prefix=session_path
                        )

                        file_count = len(file_response.get('Contents', []))
                        last_modified = None

                        if file_count > 0:
                            # Get most recent file modification
                            last_modified = max(
                                obj['LastModified']
                                for obj in file_response['Contents']
                            )

                        sessions.append({
                            'session_id': session_id,
                            'session_path': session_path,
                            'last_modified': last_modified.isoformat() if last_modified else None,
                            'file_count': file_count
                        })

            print(f"[SUCCESS] Found {len(sessions)} demo sessions")
            for session in sessions:
                print(f"  - {session['session_id']} ({session['file_count']} files)")

            return sessions

        except Exception as e:
            print(f"[ERROR] Failed to list demo sessions: {e}")
            return []


# CLI Interface
def main():
    """Command-line interface for demo session manager"""
    import argparse

    parser = argparse.ArgumentParser(
        description='Demo Session Manager - Manage test sessions and S3 interactions',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Create a new test session
  python demo_session_manager.py create --demo-name product_validation --email test@example.com

  # Check session status
  python demo_session_manager.py status --email test@example.com --session-id session_demo_20251010_143022_abc12345

  # Verify results exist
  python demo_session_manager.py verify --email test@example.com --session-id session_demo_20251010_143022_abc12345

  # Download results
  python demo_session_manager.py download --email test@example.com --session-id session_demo_20251010_143022_abc12345 --output ./results/

  # List all demo sessions
  python demo_session_manager.py list --email test@example.com

  # Clean up session (dry run first)
  python demo_session_manager.py cleanup --email test@example.com --session-id session_demo_20251010_143022_abc12345 --dry-run
  python demo_session_manager.py cleanup --email test@example.com --session-id session_demo_20251010_143022_abc12345
        """
    )

    parser.add_argument(
        '--bucket',
        default='hyperplexity-storage-dev',
        help='S3 bucket name (default: hyperplexity-storage-dev)'
    )

    subparsers = parser.add_subparsers(dest='command', help='Command to execute')

    # Create command
    create_parser = subparsers.add_parser('create', help='Create a new test session')
    create_parser.add_argument('--demo-name', required=True, help='Demo name/identifier')
    create_parser.add_argument('--email', required=True, help='Test user email')

    # Status command
    status_parser = subparsers.add_parser('status', help='Check session status')
    status_parser.add_argument('--email', required=True, help='User email')
    status_parser.add_argument('--session-id', required=True, help='Session ID')

    # Verify command
    verify_parser = subparsers.add_parser('verify', help='Verify results exist')
    verify_parser.add_argument('--email', required=True, help='User email')
    verify_parser.add_argument('--session-id', required=True, help='Session ID')
    verify_parser.add_argument('--version', type=int, help='Config version (default: latest)')

    # Download command
    download_parser = subparsers.add_parser('download', help='Download results')
    download_parser.add_argument('--email', required=True, help='User email')
    download_parser.add_argument('--session-id', required=True, help='Session ID')
    download_parser.add_argument('--output', required=True, help='Output path')
    download_parser.add_argument('--version', type=int, help='Config version (default: latest)')

    # List command
    list_parser = subparsers.add_parser('list', help='List all demo sessions')
    list_parser.add_argument('--email', required=True, help='User email')

    # Cleanup command
    cleanup_parser = subparsers.add_parser('cleanup', help='Clean up test data')
    cleanup_parser.add_argument('--email', required=True, help='User email')
    cleanup_parser.add_argument('--session-id', required=True, help='Session ID')
    cleanup_parser.add_argument('--dry-run', action='store_true', help='List files without deleting')

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    # Initialize manager
    manager = DemoSessionManager(bucket_name=args.bucket)

    # Execute command
    if args.command == 'create':
        session_id = manager.create_test_session(args.demo_name, args.email)
        print(f"\n[INFO] Use this session ID for subsequent operations:")
        print(f"  {session_id}")
        return 0

    elif args.command == 'status':
        status = manager.check_session_status(args.email, args.session_id)
        if not status['exists']:
            print(f"\n[ERROR] Session does not exist or could not be accessed")
            return 1
        return 0

    elif args.command == 'verify':
        result = manager.verify_results_exist(args.email, args.session_id, args.version)
        if not result['exists']:
            print(f"\n[ERROR] Results not found")
            return 1
        return 0

    elif args.command == 'download':
        success = manager.download_results(
            args.email,
            args.session_id,
            args.output,
            args.version
        )
        return 0 if success else 1

    elif args.command == 'list':
        sessions = manager.list_all_demo_sessions(args.email)
        return 0

    elif args.command == 'cleanup':
        result = manager.cleanup_session(
            args.email,
            args.session_id,
            dry_run=args.dry_run
        )
        return 0

    return 1


if __name__ == '__main__':
    sys.exit(main())
