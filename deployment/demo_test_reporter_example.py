"""
Example usage of demo_test_reporter module.

This script demonstrates how to use the demo testing report generator
to track and report on demo validation test results.
"""

from demo_test_reporter import (
    create_report,
    add_demo_result,
    generate_summary,
    save_report,
    print_report
)


def main():
    """
    Example workflow for generating a demo test report.
    """
    print("Creating demo test report...\n")

    # Step 1: Initialize report
    report = create_report(
        email="eliyahu@eliyahu.ai",
        environment="dev",
        test_description="End-to-end validation of all demo configurations"
    )

    # Step 2: Add test results as they complete
    # Example 1: Successful demo test
    add_demo_result(report, "Investment Research", {
        "status": "passed",
        "demo_path": "demos/investment_research/",
        "session_id": "session_demo_20251010_100001_abc123",
        "preview_time": 42.5,
        "preview_results": {
            "rows_processed": 5,
            "validations_passed": 5,
            "validations_failed": 0
        },
        "preview_cost": 0.14,
        "full_validation_time": 175.2,
        "full_validation_results": {
            "rows_processed": 48,
            "validations_passed": 48,
            "validations_failed": 0
        },
        "full_cost": 0.78,
        "download_success": True,
        "download_path": "/tmp/investment_research_results.xlsx"
    })

    # Example 2: Another successful test
    add_demo_result(report, "Competitive Intelligence", {
        "status": "passed",
        "demo_path": "demos/competitive_intelligence/",
        "session_id": "session_demo_20251010_100145_def456",
        "preview_time": 38.1,
        "preview_cost": 0.11,
        "full_validation_time": 162.8,
        "full_cost": 0.72,
        "download_success": True
    })

    # Example 3: Failed test
    add_demo_result(report, "Program Applications", {
        "status": "failed",
        "demo_path": "demos/program_applications/",
        "session_id": "session_demo_20251010_100330_ghi789",
        "preview_time": 55.3,
        "preview_cost": 0.19,
        "full_validation_time": 0.0,
        "full_cost": 0.0,
        "download_success": False,
        "error": "Lambda timeout during full validation",
        "error_details": "Function exceeded 300 second timeout during batch 3 of 5"
    })

    # Example 4: Skipped test
    add_demo_result(report, "Customer Segmentation", {
        "status": "skipped",
        "demo_path": "demos/customer_segmentation/",
        "error": "Missing configuration file"
    })

    # Example 5: Another successful test
    add_demo_result(report, "Market Analysis", {
        "status": "passed",
        "demo_path": "demos/market_analysis/",
        "session_id": "session_demo_20251010_100515_jkl012",
        "preview_time": 31.7,
        "preview_cost": 0.09,
        "full_validation_time": 145.6,
        "full_cost": 0.65,
        "download_success": True
    })

    # Step 3: Print report to console
    print_report(report)

    # Step 4: Generate summary statistics
    summary = generate_summary(report)
    print("\n\nDetailed Summary Statistics:")
    print(f"Success Rate: {summary['success_rate']:.1f}%")
    print(f"Average Time per Demo: {summary['avg_time_per_demo']:.1f} seconds")
    print(f"Average Cost per Demo: ${summary['avg_cost_per_demo']:.3f}")
    print(f"Total Test Duration: {summary['test_duration_seconds']:.2f} seconds")

    # Step 5: Save reports in all formats
    print("\n\nSaving reports to disk...")

    # Save text format
    text_path = save_report(report, output_dir="./test_results", format="text")
    print(f"[SUCCESS] Text report: {text_path}")

    # Save JSON format (for programmatic processing)
    json_path = save_report(report, output_dir="./test_results", format="json")
    print(f"[SUCCESS] JSON report: {json_path}")

    # Save HTML format (for viewing in browser)
    html_path = save_report(report, output_dir="./test_results", format="html")
    print(f"[SUCCESS] HTML report: {html_path}")

    print("\n\nReport generation complete!")


def example_integration_with_test_loop():
    """
    Example showing how to integrate the reporter into an automated test loop.
    """
    import time

    # Initialize report
    report = create_report(
        email="automation@example.com",
        environment="ci",
        test_description="Automated CI/CD demo validation"
    )

    # List of demos to test
    demos = [
        "investment_research",
        "competitive_intelligence",
        "program_applications",
        "market_analysis"
    ]

    print("Running automated demo tests...\n")

    # Simulate testing loop
    for demo_name in demos:
        print(f"Testing {demo_name}...")

        start_time = time.time()

        try:
            # Simulated test execution
            # In real implementation, this would call your actual test functions
            preview_time = 40.0
            validation_time = 160.0
            success = True

            # Simulate occasional failures
            if demo_name == "program_applications":
                success = False
                validation_time = 0.0

            if success:
                add_demo_result(report, demo_name.replace("_", " ").title(), {
                    "status": "passed",
                    "demo_path": f"demos/{demo_name}/",
                    "preview_time": preview_time,
                    "preview_cost": 0.12,
                    "full_validation_time": validation_time,
                    "full_cost": 0.68,
                    "download_success": True
                })
                print(f"  [PASS] {demo_name}")
            else:
                add_demo_result(report, demo_name.replace("_", " ").title(), {
                    "status": "failed",
                    "demo_path": f"demos/{demo_name}/",
                    "preview_time": preview_time,
                    "preview_cost": 0.12,
                    "full_validation_time": 0.0,
                    "full_cost": 0.0,
                    "download_success": False,
                    "error": "Validation timeout"
                })
                print(f"  [FAIL] {demo_name}")

        except Exception as e:
            add_demo_result(report, demo_name.replace("_", " ").title(), {
                "status": "failed",
                "error": str(e),
                "error_details": "Unexpected exception during test execution"
            })
            print(f"  [ERROR] {demo_name}: {e}")

    # Generate final report
    print("\n" + "="*70)
    print_report(report)

    # Save reports
    save_report(report, "./test_results", format="json")
    save_report(report, "./test_results", format="html")


if __name__ == "__main__":
    # Run the basic example
    main()

    # Uncomment to see integration example
    # print("\n\n" + "="*70)
    # print("INTEGRATION EXAMPLE")
    # print("="*70 + "\n")
    # example_integration_with_test_loop()
