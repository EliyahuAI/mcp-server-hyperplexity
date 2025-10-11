#!/usr/bin/env python3
"""
Demo Session Manager Usage Examples

This script demonstrates how to use the DemoSessionManager for testing.
"""

from demo_session_manager import DemoSessionManager


def example_create_and_monitor_session():
    """Example: Create a test session and monitor its progress"""

    # Initialize manager (uses dev bucket by default)
    manager = DemoSessionManager()

    # Create a new test session
    print("=" * 60)
    print("EXAMPLE 1: Creating Test Session")
    print("=" * 60)
    session_id = manager.create_test_session(
        demo_name="product_validation_demo",
        email="test@example.com"
    )
    print(f"\nGenerated Session ID: {session_id}\n")

    # Check session status
    print("=" * 60)
    print("EXAMPLE 2: Checking Session Status")
    print("=" * 60)
    status = manager.check_session_status("test@example.com", session_id)

    if status['exists']:
        print(f"\nSession Status Summary:")
        print(f"  Current Version: {status['current_version']}")
        print(f"  Has Preview: {status['has_preview']}")
        print(f"  Has Validation: {status['has_validation']}")

        if status['has_preview']:
            print(f"  Preview Status: {status['preview_status']}")
        if status['has_validation']:
            print(f"  Validation Status: {status['validation_status']}")
    else:
        print(f"\nSession not yet created in S3")
        print(f"This is expected for a newly generated session ID")

    return session_id


def example_verify_and_download_results(session_id: str):
    """Example: Verify results exist and download them"""

    manager = DemoSessionManager()

    # Verify results exist
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Verifying Results Exist")
    print("=" * 60)
    result = manager.verify_results_exist(
        email="test@example.com",
        session_id=session_id
    )

    if result['exists']:
        print(f"\nResults found for version {result['version']}")

        # Download results
        print("\n" + "=" * 60)
        print("EXAMPLE 4: Downloading Results")
        print("=" * 60)
        success = manager.download_results(
            email="test@example.com",
            session_id=session_id,
            output_path="./demo_results/"
        )

        if success:
            print("\nResults successfully downloaded to ./demo_results/")
        else:
            print("\nFailed to download results")
    else:
        print(f"\nNo results found yet. Error: {result.get('error', 'Unknown')}")


def example_list_sessions():
    """Example: List all demo sessions for a user"""

    manager = DemoSessionManager()

    print("\n" + "=" * 60)
    print("EXAMPLE 5: Listing All Demo Sessions")
    print("=" * 60)
    sessions = manager.list_all_demo_sessions("test@example.com")

    if sessions:
        print(f"\nFound {len(sessions)} demo sessions:")
        for i, session in enumerate(sessions, 1):
            print(f"\n{i}. {session['session_id']}")
            print(f"   Files: {session['file_count']}")
            print(f"   Last Modified: {session['last_modified']}")
    else:
        print("\nNo demo sessions found")


def example_cleanup_session(session_id: str):
    """Example: Clean up test session data"""

    manager = DemoSessionManager()

    # First do a dry run
    print("\n" + "=" * 60)
    print("EXAMPLE 6: Cleanup Session (Dry Run)")
    print("=" * 60)
    result = manager.cleanup_session(
        email="test@example.com",
        session_id=session_id,
        dry_run=True
    )

    print(f"\nDry run complete:")
    print(f"  Files found: {result['files_found']}")
    print(f"  Would delete: {result['files_found']} files")

    # Uncomment to actually delete:
    # print("\n" + "=" * 60)
    # print("EXAMPLE 7: Cleanup Session (Actual Delete)")
    # print("=" * 60)
    # result = manager.cleanup_session(
    #     email="test@example.com",
    #     session_id=session_id,
    #     dry_run=False
    # )
    # print(f"\nCleanup complete - deleted {result['files_deleted']} files")


def example_working_with_existing_session():
    """Example: Work with an existing session from the system"""

    manager = DemoSessionManager()

    # Replace with an actual session ID from your system
    existing_session_id = "session_20251010_120000_abc12345"

    print("\n" + "=" * 60)
    print("EXAMPLE 8: Working with Existing Session")
    print("=" * 60)
    print(f"Session ID: {existing_session_id}")

    # Check status
    status = manager.check_session_status("test@example.com", existing_session_id)

    if status['exists']:
        print(f"\n[SUCCESS] Session found!")
        print(f"Current version: {status['current_version']}")

        # Verify results
        if status['has_validation']:
            result = manager.verify_results_exist(
                "test@example.com",
                existing_session_id
            )

            if result['exists']:
                print(f"\n[SUCCESS] Results verified!")
                print(f"Enhanced Excel: {result.get('enhanced_excel', 'N/A')}")

                # Download
                print(f"\nDownloading results...")
                manager.download_results(
                    "test@example.com",
                    existing_session_id,
                    f"./results/{existing_session_id}/"
                )
    else:
        print(f"\n[INFO] Session not found")


def main():
    """Run all examples"""

    print("\n" + "=" * 60)
    print("DEMO SESSION MANAGER - USAGE EXAMPLES")
    print("=" * 60)
    print("\nThis script demonstrates various operations:")
    print("  1. Creating test sessions")
    print("  2. Checking session status")
    print("  3. Verifying results exist")
    print("  4. Downloading results")
    print("  5. Listing all sessions")
    print("  6. Cleaning up test data")
    print("\n" + "=" * 60)

    # Example 1-2: Create session and check status
    session_id = example_create_and_monitor_session()

    # Example 3-4: Verify and download (will fail for new session, but shows the flow)
    example_verify_and_download_results(session_id)

    # Example 5: List all sessions
    example_list_sessions()

    # Example 6: Cleanup (dry run only)
    example_cleanup_session(session_id)

    # Example 8: Working with existing session (commented out by default)
    # example_working_with_existing_session()

    print("\n" + "=" * 60)
    print("EXAMPLES COMPLETE")
    print("=" * 60)
    print("\nTo use with actual sessions:")
    print("  1. Replace session IDs with real ones from your system")
    print("  2. Use the CLI interface for interactive testing:")
    print("     python demo_session_manager.py --help")
    print("=" * 60 + "\n")


if __name__ == '__main__':
    main()
