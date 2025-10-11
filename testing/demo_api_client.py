#!/usr/bin/env python3
"""
Demo API Client for Hyperplexity Validator Dev Environment

This module provides a Python HTTP client for interacting with the dev environment
interface lambda API for demo workflows.

Usage Example:
    from deployment.demo_api_client import DemoAPIClient

    # Initialize client
    client = DemoAPIClient(email="eliyahu@eliyahu.ai")

    # Load a demo
    session_id, demo_info = client.call_demo_api("demo_name")

    # Trigger preview
    preview_result = client.trigger_preview(session_id)

    # Trigger full validation
    validation_result = client.trigger_full_validation(session_id)

    # Poll status
    status = client.check_status(session_id)

    # Get results
    results = client.get_results_info(session_id)
"""

import requests
import time
import json
from typing import Dict, Optional, Tuple, Any
from datetime import datetime
import websocket
import threading


class DemoAPIClient:
    """HTTP client for interacting with the Hyperplexity Validator dev API."""

    # API Configuration
    DEV_API_BASE = "https://wqamcddvub.execute-api.us-east-1.amazonaws.com/dev"
    WEBSOCKET_URL = "wss://xt6790qk9f.execute-api.us-east-1.amazonaws.com/prod"
    DEFAULT_EMAIL = "eliyahu@eliyahu.ai"

    # Timeout configurations (in seconds)
    PREVIEW_TIMEOUT = 5 * 60  # 5 minutes
    VALIDATION_TIMEOUT = 30 * 60  # 30 minutes

    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAY = 2  # seconds

    # Polling configuration
    POLL_INTERVAL = 5  # seconds

    # WebSocket configuration
    USE_WEBSOCKET = True  # Use WebSocket for status updates

    def __init__(self, email: Optional[str] = None, api_base: Optional[str] = None):
        """
        Initialize the Demo API Client.

        Args:
            email: User email address (defaults to DEFAULT_EMAIL)
            api_base: API base URL (defaults to DEV_API_BASE)
        """
        self.email = email or self.DEFAULT_EMAIL
        self.api_base = api_base or self.DEV_API_BASE
        self.session = requests.Session()

        # Set default headers
        self.session.headers.update({
            'User-Agent': 'HyperplexityValidator-DemoClient/1.0'
        })

        # WebSocket state
        self.ws_messages = {}  # session_id -> list of messages
        self.ws_lock = threading.Lock()

    def _make_request(
        self,
        method: str,
        endpoint: str,
        data: Optional[Dict] = None,
        files: Optional[Dict] = None,
        params: Optional[Dict] = None,
        timeout: int = 30,
        retries: int = None
    ) -> Dict[str, Any]:
        """
        Make an HTTP request with error handling and retries.

        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint path
            data: Request body data (for JSON requests)
            files: Files to upload (for multipart requests)
            params: Query parameters
            timeout: Request timeout in seconds
            retries: Number of retries (defaults to MAX_RETRIES)

        Returns:
            Response data as dictionary

        Raises:
            Exception: If request fails after all retries
        """
        if retries is None:
            retries = self.MAX_RETRIES

        url = f"{self.api_base}{endpoint}"
        last_error = None

        for attempt in range(retries):
            try:
                if files:
                    # Multipart request
                    response = self.session.request(
                        method=method,
                        url=url,
                        data=data,
                        files=files,
                        params=params,
                        timeout=timeout
                    )
                else:
                    # JSON request
                    response = self.session.request(
                        method=method,
                        url=url,
                        json=data,
                        params=params,
                        timeout=timeout
                    )

                response.raise_for_status()

                # Parse JSON response
                return response.json()

            except requests.exceptions.Timeout as e:
                last_error = f"Request timeout after {timeout}s"
                print(f"[WARNING] Attempt {attempt + 1}/{retries}: {last_error}")

            except requests.exceptions.ConnectionError as e:
                last_error = f"Connection error: {str(e)}"
                print(f"[WARNING] Attempt {attempt + 1}/{retries}: {last_error}")

            except requests.exceptions.HTTPError as e:
                status_code = e.response.status_code
                try:
                    error_data = e.response.json()
                    error_msg = error_data.get('error', str(e))
                except:
                    error_msg = str(e)

                last_error = f"HTTP {status_code}: {error_msg}"
                print(f"[ERROR] Attempt {attempt + 1}/{retries}: {last_error}")

                # Don't retry on 4xx errors (client errors)
                if 400 <= status_code < 500:
                    raise Exception(last_error)

            except Exception as e:
                last_error = f"Unexpected error: {str(e)}"
                print(f"[ERROR] Attempt {attempt + 1}/{retries}: {last_error}")

            # Wait before retrying (except on last attempt)
            if attempt < retries - 1:
                time.sleep(self.RETRY_DELAY)

        # All retries failed
        raise Exception(f"Request failed after {retries} attempts: {last_error}")

    def call_demo_api(self, demo_name: str, email: Optional[str] = None) -> Tuple[str, Dict]:
        """
        Call demo management API to select and load a demo.

        This creates a new session with demo files copied to user storage.

        Args:
            demo_name: Name of the demo to load
            email: User email (defaults to client email)

        Returns:
            Tuple of (session_id, demo_info)

        Raises:
            Exception: If demo selection fails
        """
        email = email or self.email

        print(f"[INFO] Loading demo '{demo_name}' for {email}...")

        request_data = {
            'action': 'selectDemo',
            'demo_name': demo_name,
            'email': email
        }

        response = self._make_request(
            method='POST',
            endpoint='/validate',
            data=request_data,
            timeout=30
        )

        if not response.get('success'):
            error = response.get('error', 'Unknown error')
            raise Exception(f"Demo selection failed: {error}")

        session_id = response.get('session_id')
        demo_info = response.get('demo', {})

        print(f"[SUCCESS] Demo loaded successfully")
        print(f"  - Session ID: {session_id}")
        print(f"  - Demo: {demo_info.get('display_name', demo_name)}")

        return session_id, demo_info

    def trigger_preview(
        self,
        session_id: str,
        email: Optional[str] = None,
        preview_max_rows: int = 3,
        wait_for_completion: bool = True
    ) -> Dict[str, Any]:
        """
        Trigger preview validation on the first few rows.

        Args:
            session_id: Session ID from demo loading
            email: User email (defaults to client email)
            preview_max_rows: Number of rows to preview (default: 3)
            wait_for_completion: Whether to poll until complete (default: True)

        Returns:
            Preview results dictionary

        Raises:
            Exception: If preview fails
        """
        email = email or self.email

        print(f"[INFO] Triggering preview validation (max {preview_max_rows} rows)...")

        # Create dummy file to satisfy backend requirement
        dummy_file = json.dumps({'use_stored_files': True}).encode('utf-8')

        files = {
            'dummy_file': ('stored_files_marker.json', dummy_file, 'application/json')
        }

        data = {
            'email': email,
            'session_id': session_id
        }

        params = {
            'async': 'true',
            'preview_first_row': 'true',
            'preview_max_rows': str(preview_max_rows)
        }

        response = self._make_request(
            method='POST',
            endpoint='/validate',
            data=data,
            files=files,
            params=params,
            timeout=60
        )

        if response.get('status') != 'processing':
            error = response.get('error', 'Unknown error')
            raise Exception(f"Preview trigger failed: {error}")

        # Get the actual preview session ID
        preview_session_id = response.get('session_id', session_id)

        print(f"[SUCCESS] Preview triggered")
        print(f"  - Preview Session ID: {preview_session_id}")

        if wait_for_completion:
            return self._poll_for_completion(
                session_id=preview_session_id,
                is_preview=True,
                timeout=self.PREVIEW_TIMEOUT
            )

        return {
            'status': 'processing',
            'session_id': preview_session_id
        }

    def trigger_full_validation(
        self,
        session_id: str,
        email: Optional[str] = None,
        max_rows: Optional[int] = None,
        batch_size: Optional[int] = None,
        wait_for_completion: bool = True
    ) -> Dict[str, Any]:
        """
        Trigger full validation on the entire table.

        Args:
            session_id: Session ID from demo loading
            email: User email (defaults to client email)
            max_rows: Maximum rows to process (None = all rows)
            batch_size: Batch size for processing (None = auto)
            wait_for_completion: Whether to poll until complete (default: True)

        Returns:
            Validation results dictionary

        Raises:
            Exception: If validation fails
        """
        email = email or self.email

        print(f"[INFO] Triggering full validation...")
        if max_rows:
            print(f"  - Max rows: {max_rows}")
        if batch_size:
            print(f"  - Batch size: {batch_size}")

        # Create dummy file to satisfy backend requirement
        dummy_file = json.dumps({'use_stored_files': True}).encode('utf-8')

        files = {
            'config_file': ('stored_files_marker.json', dummy_file, 'application/json')
        }

        data = {
            'email': email,
            'session_id': session_id
        }

        params = {
            'async': 'true'
        }

        if max_rows:
            params['max_rows'] = str(max_rows)
        if batch_size:
            params['batch_size'] = str(batch_size)

        response = self._make_request(
            method='POST',
            endpoint='/validate',
            data=data,
            files=files,
            params=params,
            timeout=60
        )

        if response.get('status') != 'processing':
            error = response.get('error', 'Unknown error')
            raise Exception(f"Validation trigger failed: {error}")

        validation_session_id = response.get('session_id', session_id)

        print(f"[SUCCESS] Validation triggered")
        print(f"  - Session ID: {validation_session_id}")

        if wait_for_completion:
            return self._poll_for_completion(
                session_id=validation_session_id,
                is_preview=False,
                timeout=self.VALIDATION_TIMEOUT
            )

        return {
            'status': 'processing',
            'session_id': validation_session_id
        }

    def check_status(
        self,
        session_id: str,
        is_preview: bool = False
    ) -> Dict[str, Any]:
        """
        Poll validation status for a session.

        Args:
            session_id: Session ID to check
            is_preview: Whether this is a preview session

        Returns:
            Status information dictionary

        Raises:
            Exception: If status check fails
        """
        # Use the same endpoint as the frontend: POST /validate with action: checkStatus
        request_data = {
            'action': 'checkStatus',
            'session_id': session_id
        }

        response = self._make_request(
            method='POST',
            endpoint='/validate',
            data=request_data,
            timeout=10
        )

        return response

    def get_results_info(self, session_id: str) -> Dict[str, Any]:
        """
        Get results metadata for a completed validation.

        Args:
            session_id: Session ID to get results for

        Returns:
            Results metadata including download URL

        Raises:
            Exception: If session is not completed or results not found
        """
        status = self.check_status(session_id, is_preview=False)

        if status.get('status') != 'COMPLETED':
            current_status = status.get('status', 'UNKNOWN')
            raise Exception(f"Session not completed. Current status: {current_status}")

        if 'download_url' not in status:
            raise Exception("Results download URL not found in status response")

        return {
            'session_id': session_id,
            'download_url': status['download_url'],
            'total_rows': status.get('total_rows'),
            'processed_rows': status.get('processed_rows'),
            'total_cost': status.get('total_cost'),
            'status_data': status
        }

    def _connect_websocket(self, session_id: str):
        """Connect to WebSocket and listen for messages for a specific session."""
        def on_message(ws, message):
            try:
                data = json.loads(message)
                print(f"[WEBSOCKET] {json.dumps(data, indent=2)}")

                # Store message for this session
                with self.ws_lock:
                    if session_id not in self.ws_messages:
                        self.ws_messages[session_id] = []
                    self.ws_messages[session_id].append(data)
            except Exception as e:
                print(f"[WEBSOCKET ERROR] Failed to parse message: {e}")

        def on_error(ws, error):
            print(f"[WEBSOCKET ERROR] {error}")

        def on_close(ws, close_status_code, close_msg):
            print(f"[WEBSOCKET] Connection closed")

        def on_open(ws):
            print(f"[WEBSOCKET] Connected for session {session_id}")
            # Subscribe to session updates
            ws.send(json.dumps({
                'action': 'subscribe',
                'session_id': session_id
            }))

        ws = websocket.WebSocketApp(
            self.WEBSOCKET_URL,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open
        )

        # Run WebSocket in background thread
        ws_thread = threading.Thread(target=ws.run_forever, daemon=True)
        ws_thread.start()

        return ws

    def _poll_for_completion(
        self,
        session_id: str,
        is_preview: bool,
        timeout: int
    ) -> Dict[str, Any]:
        """
        Poll for validation completion using WebSocket or HTTP polling.

        Args:
            session_id: Session ID to poll
            is_preview: Whether this is a preview session
            timeout: Maximum time to wait (seconds)

        Returns:
            Completion data

        Raises:
            Exception: If polling times out or validation fails
        """
        start_time = time.time()
        last_status = None
        last_percent = 0

        # Connect WebSocket if enabled
        ws = None
        if self.USE_WEBSOCKET:
            print(f"[INFO] Connecting WebSocket for real-time updates...")
            ws = self._connect_websocket(session_id)
            time.sleep(1)  # Give WebSocket time to connect

        print(f"[INFO] Waiting for completion (timeout: {timeout}s)...")

        while True:
            elapsed = time.time() - start_time

            if elapsed > timeout:
                raise Exception(f"Polling timeout after {timeout}s. Last status: {last_status}")

            try:
                # Check WebSocket messages first
                if self.USE_WEBSOCKET:
                    with self.ws_lock:
                        if session_id in self.ws_messages and self.ws_messages[session_id]:
                            # Get the latest message
                            latest_msg = self.ws_messages[session_id][-1]

                            # Check if it's a completion message
                            msg_status = latest_msg.get('status', '').upper()
                            if msg_status == 'COMPLETED' or 'preview_data' in latest_msg or 'download_url' in latest_msg:
                                print(f"[SUCCESS] Validation completed! (via WebSocket)")

                                if ws:
                                    ws.close()

                                if is_preview:
                                    return {
                                        'success': True,
                                        'session_id': session_id,
                                        'preview_data': latest_msg.get('preview_data', {}),
                                        'full_status': latest_msg
                                    }
                                else:
                                    return {
                                        'success': True,
                                        'session_id': session_id,
                                        'download_url': latest_msg.get('download_url'),
                                        'total_rows': latest_msg.get('total_rows'),
                                        'processed_rows': latest_msg.get('processed_rows'),
                                        'total_cost': latest_msg.get('total_cost'),
                                        'full_status': latest_msg
                                    }

                            # Check for failure
                            if msg_status in ['FAILED', 'ERROR']:
                                if ws:
                                    ws.close()
                                error_msg = latest_msg.get('error_message', 'Unknown error')
                                raise Exception(f"Validation failed: {error_msg}")

                # Also check via HTTP status as fallback
                status = self.check_status(session_id, is_preview=is_preview)
                current_status = status.get('status', 'UNKNOWN')

                # Show progress updates
                if current_status != last_status:
                    print(f"[STATUS] {current_status}")
                    last_status = current_status

                # Show percentage if available
                percent = status.get('percent_complete', 0)
                if percent != last_percent and percent > 0:
                    print(f"[PROGRESS] {percent}%")
                    last_percent = percent

                # Check for completion (case-insensitive)
                status_upper = current_status.upper() if current_status else ''
                is_completed = (status_upper == 'COMPLETED' or
                               'preview_data' in status or
                               'download_url' in status)

                if is_completed:
                    print(f"[SUCCESS] Validation completed! (via HTTP)")

                    if ws:
                        ws.close()

                    if is_preview:
                        preview_data = status.get('preview_data', {})
                        return {
                            'success': True,
                            'session_id': session_id,
                            'preview_data': preview_data,
                            'full_status': status
                        }
                    else:
                        download_url = status.get('download_url')
                        return {
                            'success': True,
                            'session_id': session_id,
                            'download_url': download_url,
                            'total_rows': status.get('total_rows'),
                            'processed_rows': status.get('processed_rows'),
                            'total_cost': status.get('total_cost'),
                            'full_status': status
                        }

                # Check for failure
                if status_upper in ['FAILED', 'ERROR']:
                    if ws:
                        ws.close()
                    error_msg = status.get('error_message', 'Unknown error')
                    raise Exception(f"Validation failed: {error_msg}")

            except Exception as e:
                # Only raise if it's not a temporary network error
                if "Request failed" not in str(e) and "Validation failed" in str(e):
                    raise
                if "Request failed" not in str(e):
                    print(f"[WARNING] Error during polling: {e}")

            # Wait before next poll
            time.sleep(self.POLL_INTERVAL)

    def list_demos(self) -> Dict[str, Any]:
        """
        List all available demos.

        Returns:
            Dictionary with list of available demos

        Raises:
            Exception: If listing fails
        """
        print("[INFO] Fetching available demos...")

        request_data = {
            'action': 'listDemos'
        }

        response = self._make_request(
            method='POST',
            endpoint='/validate',
            data=request_data,
            timeout=30
        )

        if not response.get('success'):
            error = response.get('error', 'Unknown error')
            raise Exception(f"Failed to list demos: {error}")

        demos = response.get('demos', [])
        print(f"[SUCCESS] Found {len(demos)} demos")

        return {
            'success': True,
            'demos': demos
        }


# Convenience functions for quick usage
def quick_demo_test(demo_name: str, email: Optional[str] = None, preview_only: bool = False):
    """
    Quick test function to run a complete demo workflow.

    Args:
        demo_name: Name of the demo to run
        email: User email (defaults to DEFAULT_EMAIL)
        preview_only: If True, only run preview (default: False)

    Returns:
        Dictionary with test results
    """
    client = DemoAPIClient(email=email)

    print("=" * 60)
    print(f"DEMO WORKFLOW TEST: {demo_name}")
    print("=" * 60)

    try:
        # Step 1: Load demo
        session_id, demo_info = client.call_demo_api(demo_name)

        # Step 2: Run preview
        preview_result = client.trigger_preview(session_id, wait_for_completion=True)

        print("\n[PREVIEW RESULTS]")
        if 'preview_data' in preview_result:
            pd = preview_result['preview_data']
            print(f"  - Estimated total cost: ${pd.get('estimated_total_cost', 0):.2f}")
            print(f"  - Estimated time: {pd.get('estimated_total_time_seconds', 0):.0f}s")
            print(f"  - Total rows: {pd.get('total_rows', 0)}")

        results = {
            'success': True,
            'session_id': session_id,
            'demo_info': demo_info,
            'preview_result': preview_result
        }

        if not preview_only:
            # Step 3: Run full validation
            print("\n" + "=" * 60)
            validation_result = client.trigger_full_validation(
                session_id,
                wait_for_completion=True
            )

            print("\n[VALIDATION RESULTS]")
            print(f"  - Download URL: {validation_result.get('download_url')}")
            print(f"  - Processed rows: {validation_result.get('processed_rows')}")
            print(f"  - Total cost: ${validation_result.get('total_cost', 0):.2f}")

            results['validation_result'] = validation_result

        print("\n" + "=" * 60)
        print("[SUCCESS] Demo workflow completed!")
        print("=" * 60)

        return results

    except Exception as e:
        print("\n" + "=" * 60)
        print(f"[ERROR] Demo workflow failed: {e}")
        print("=" * 60)
        raise


if __name__ == '__main__':
    # Example usage
    import sys

    if len(sys.argv) > 1:
        demo_name = sys.argv[1]
        preview_only = '--preview-only' in sys.argv

        result = quick_demo_test(demo_name, preview_only=preview_only)
        print("\n[FINAL RESULT]")
        print(json.dumps(result, indent=2, default=str))
    else:
        print("Usage: python.exe demo_api_client.py <demo_name> [--preview-only]")
        print("\nExample:")
        print("  python.exe demo_api_client.py competitive_intelligence --preview-only")
        print("\nTo list available demos:")
        print("  python.exe -c 'from deployment.demo_api_client import DemoAPIClient; client = DemoAPIClient(); print(client.list_demos())'")
