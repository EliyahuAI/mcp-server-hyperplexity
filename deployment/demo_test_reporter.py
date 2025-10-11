"""
Demo Testing Report Generator

Generates comprehensive test execution reports for demo validation testing.
Supports multiple output formats: text, JSON, and HTML.

Usage:
    from demo_test_reporter import create_report, add_demo_result, save_report

    # Initialize report
    report = create_report(email="test@example.com", environment="dev")

    # Add test results
    add_demo_result(report, "Investment Research", {
        "status": "passed",
        "preview_time": 45.2,
        "full_validation_time": 180.5,
        "download_success": True,
        "preview_cost": 0.15,
        "full_cost": 0.82
    })

    # Save report
    save_report(report, output_dir="./test_results", format="text")
    print_report(report)
"""

import json
import os
from datetime import datetime
from typing import Dict, List, Optional, Any
from pathlib import Path


def create_report(
    email: str = "test@example.com",
    environment: str = "dev",
    test_description: Optional[str] = None
) -> Dict[str, Any]:
    """
    Initialize a new test report.

    Args:
        email: Test email address used for validation
        environment: Environment name (dev, staging, prod)
        test_description: Optional description of the test run

    Returns:
        Report dictionary with initialized structure
    """
    return {
        "metadata": {
            "generated_at": datetime.now().isoformat(),
            "test_email": email,
            "environment": environment,
            "description": test_description or "Automated demo validation testing",
            "start_time": datetime.now().isoformat()
        },
        "demos": [],
        "summary": {
            "total": 0,
            "passed": 0,
            "failed": 0,
            "skipped": 0,
            "total_time": 0.0,
            "total_preview_time": 0.0,
            "total_validation_time": 0.0,
            "total_cost": 0.0,
            "total_preview_cost": 0.0,
            "total_validation_cost": 0.0
        },
        "errors": []
    }


def add_demo_result(
    report: Dict[str, Any],
    demo_name: str,
    result_data: Dict[str, Any]
) -> None:
    """
    Add a test result for a demo to the report.

    Args:
        report: Report dictionary created by create_report()
        demo_name: Name/title of the demo
        result_data: Dictionary containing test results with keys:
            - status: "passed", "failed", or "skipped"
            - demo_path: S3 path or identifier (optional)
            - preview_time: Time in seconds for preview (optional)
            - preview_results: Preview validation results (optional)
            - preview_cost: Estimated cost for preview (optional)
            - full_validation_time: Time in seconds for full validation (optional)
            - full_validation_results: Full validation results (optional)
            - full_cost: Actual cost for full validation (optional)
            - download_success: Boolean indicating if download succeeded (optional)
            - error: Error message if failed (optional)
            - error_details: Detailed error information (optional)
            - session_id: Session ID for the test (optional)
            - config_version: Configuration version used (optional)
    """
    demo_entry = {
        "demo_name": demo_name,
        "status": result_data.get("status", "unknown"),
        "timestamp": datetime.now().isoformat(),
        "demo_path": result_data.get("demo_path", ""),
        "session_id": result_data.get("session_id", ""),
        "config_version": result_data.get("config_version", 1),
        "preview": {
            "time_seconds": result_data.get("preview_time", 0.0),
            "results": result_data.get("preview_results"),
            "cost": result_data.get("preview_cost", 0.0)
        },
        "full_validation": {
            "time_seconds": result_data.get("full_validation_time", 0.0),
            "results": result_data.get("full_validation_results"),
            "cost": result_data.get("full_cost", 0.0)
        },
        "download": {
            "success": result_data.get("download_success", False),
            "file_path": result_data.get("download_path", "")
        },
        "error": result_data.get("error"),
        "error_details": result_data.get("error_details")
    }

    # Add to demos list
    report["demos"].append(demo_entry)

    # Update summary
    summary = report["summary"]
    summary["total"] += 1

    status = result_data.get("status", "unknown")
    if status == "passed":
        summary["passed"] += 1
    elif status == "failed":
        summary["failed"] += 1
    elif status == "skipped":
        summary["skipped"] += 1

    # Update timing
    preview_time = result_data.get("preview_time", 0.0)
    validation_time = result_data.get("full_validation_time", 0.0)
    summary["total_preview_time"] += preview_time
    summary["total_validation_time"] += validation_time
    summary["total_time"] += preview_time + validation_time

    # Update costs
    preview_cost = result_data.get("preview_cost", 0.0)
    validation_cost = result_data.get("full_cost", 0.0)
    summary["total_preview_cost"] += preview_cost
    summary["total_validation_cost"] += validation_cost
    summary["total_cost"] += preview_cost + validation_cost

    # Add to errors list if failed
    if status == "failed" and result_data.get("error"):
        report["errors"].append({
            "demo_name": demo_name,
            "error": result_data.get("error"),
            "error_details": result_data.get("error_details"),
            "timestamp": datetime.now().isoformat()
        })


def generate_summary(report: Dict[str, Any]) -> Dict[str, Any]:
    """
    Generate summary statistics from the report.

    Args:
        report: Report dictionary

    Returns:
        Dictionary containing summary statistics
    """
    summary = report["summary"].copy()

    # Calculate averages
    if summary["total"] > 0:
        summary["avg_time_per_demo"] = summary["total_time"] / summary["total"]
        summary["avg_preview_time"] = summary["total_preview_time"] / summary["total"]
        summary["avg_validation_time"] = summary["total_validation_time"] / summary["total"]
        summary["avg_cost_per_demo"] = summary["total_cost"] / summary["total"]
    else:
        summary["avg_time_per_demo"] = 0.0
        summary["avg_preview_time"] = 0.0
        summary["avg_validation_time"] = 0.0
        summary["avg_cost_per_demo"] = 0.0

    # Calculate success rate
    if summary["total"] > 0:
        summary["success_rate"] = (summary["passed"] / summary["total"]) * 100
    else:
        summary["success_rate"] = 0.0

    # Add end time
    summary["end_time"] = datetime.now().isoformat()

    # Calculate test duration
    start_time = datetime.fromisoformat(report["metadata"]["start_time"])
    end_time = datetime.now()
    summary["test_duration_seconds"] = (end_time - start_time).total_seconds()

    return summary


def _format_time(seconds: float) -> str:
    """Format seconds into human-readable time."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}min"
    else:
        hours = seconds / 3600
        return f"{hours:.2f}hr"


def _format_cost(cost: float) -> str:
    """Format cost as currency."""
    return f"${cost:.3f}"


def _generate_text_report(report: Dict[str, Any]) -> str:
    """Generate text format report."""
    summary = generate_summary(report)
    metadata = report["metadata"]

    lines = []
    lines.append("=" * 70)
    lines.append("DEMO TESTING REPORT".center(70))
    lines.append("=" * 70)
    lines.append("")
    lines.append(f"Generated:    {metadata['generated_at']}")
    lines.append(f"Environment:  {metadata['environment']}")
    lines.append(f"Test Email:   {metadata['test_email']}")
    lines.append(f"Description:  {metadata['description']}")
    lines.append("")

    # Summary section
    lines.append("-" * 70)
    lines.append("SUMMARY")
    lines.append("-" * 70)
    lines.append(f"Total Demos:     {summary['total']}")
    lines.append(f"Passed:          {summary['passed']} ({summary['success_rate']:.1f}%)")
    lines.append(f"Failed:          {summary['failed']}")
    lines.append(f"Skipped:         {summary['skipped']}")
    lines.append("")
    lines.append(f"Total Time:      {_format_time(summary['total_time'])}")
    lines.append(f"  Preview Time:  {_format_time(summary['total_preview_time'])}")
    lines.append(f"  Validation:    {_format_time(summary['total_validation_time'])}")
    lines.append(f"Average Time:    {_format_time(summary['avg_time_per_demo'])}")
    lines.append("")
    lines.append(f"Total Cost:      {_format_cost(summary['total_cost'])}")
    lines.append(f"  Preview Cost:  {_format_cost(summary['total_preview_cost'])}")
    lines.append(f"  Validation:    {_format_cost(summary['total_validation_cost'])}")
    lines.append(f"Average Cost:    {_format_cost(summary['avg_cost_per_demo'])}")
    lines.append("")

    # Demo details section
    if report["demos"]:
        lines.append("-" * 70)
        lines.append("DEMO DETAILS")
        lines.append("-" * 70)

        for idx, demo in enumerate(report["demos"], 1):
            status_symbol = "[PASS]" if demo["status"] == "passed" else "[FAIL]" if demo["status"] == "failed" else "[SKIP]"
            total_time = demo["preview"]["time_seconds"] + demo["full_validation"]["time_seconds"]
            total_cost = demo["preview"]["cost"] + demo["full_validation"]["cost"]

            lines.append(f"[{idx}/{summary['total']}] {demo['demo_name']} - {status_symbol}")
            lines.append(f"  Time:     {_format_time(total_time)} (Preview: {_format_time(demo['preview']['time_seconds'])}, Validation: {_format_time(demo['full_validation']['time_seconds'])})")
            lines.append(f"  Cost:     {_format_cost(total_cost)} (Preview: {_format_cost(demo['preview']['cost'])}, Validation: {_format_cost(demo['full_validation']['cost'])})")
            lines.append(f"  Download: {'Success' if demo['download']['success'] else 'Failed'}")

            if demo["session_id"]:
                lines.append(f"  Session:  {demo['session_id']}")

            if demo["error"]:
                lines.append(f"  Error:    {demo['error']}")

            lines.append("")

    # Errors section
    if report["errors"]:
        lines.append("-" * 70)
        lines.append("ERRORS")
        lines.append("-" * 70)

        for error in report["errors"]:
            lines.append(f"Demo: {error['demo_name']}")
            lines.append(f"Error: {error['error']}")
            if error.get("error_details"):
                lines.append(f"Details: {error['error_details']}")
            lines.append(f"Time: {error['timestamp']}")
            lines.append("")

    lines.append("=" * 70)
    lines.append("END OF REPORT")
    lines.append("=" * 70)

    return "\n".join(lines)


def _generate_json_report(report: Dict[str, Any]) -> str:
    """Generate JSON format report."""
    summary = generate_summary(report)
    report_copy = report.copy()
    report_copy["summary"] = summary
    return json.dumps(report_copy, indent=2)


def _generate_html_report(report: Dict[str, Any]) -> str:
    """Generate HTML format report."""
    summary = generate_summary(report)
    metadata = report["metadata"]

    html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Demo Testing Report - {metadata['generated_at']}</title>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #4CAF50;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #555;
            margin-top: 30px;
            border-bottom: 2px solid #ddd;
            padding-bottom: 5px;
        }}
        .metadata {{
            background-color: #f9f9f9;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 20px;
        }}
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .summary-card {{
            background-color: #f9f9f9;
            padding: 20px;
            border-radius: 5px;
            border-left: 4px solid #4CAF50;
        }}
        .summary-card.failed {{
            border-left-color: #f44336;
        }}
        .summary-card h3 {{
            margin: 0 0 10px 0;
            color: #666;
            font-size: 14px;
            text-transform: uppercase;
        }}
        .summary-card .value {{
            font-size: 28px;
            font-weight: bold;
            color: #333;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th {{
            background-color: #4CAF50;
            color: white;
            padding: 12px;
            text-align: left;
        }}
        td {{
            padding: 10px;
            border-bottom: 1px solid #ddd;
        }}
        tr:hover {{
            background-color: #f5f5f5;
        }}
        .status-badge {{
            padding: 4px 8px;
            border-radius: 3px;
            font-size: 12px;
            font-weight: bold;
            text-transform: uppercase;
        }}
        .status-passed {{
            background-color: #4CAF50;
            color: white;
        }}
        .status-failed {{
            background-color: #f44336;
            color: white;
        }}
        .status-skipped {{
            background-color: #ff9800;
            color: white;
        }}
        .error-box {{
            background-color: #ffebee;
            border-left: 4px solid #f44336;
            padding: 15px;
            margin: 10px 0;
            border-radius: 3px;
        }}
        .error-box h4 {{
            margin: 0 0 10px 0;
            color: #c62828;
        }}
        .error-details {{
            font-family: monospace;
            font-size: 12px;
            color: #666;
            white-space: pre-wrap;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Demo Testing Report</h1>

        <div class="metadata">
            <strong>Generated:</strong> {metadata['generated_at']}<br>
            <strong>Environment:</strong> {metadata['environment']}<br>
            <strong>Test Email:</strong> {metadata['test_email']}<br>
            <strong>Description:</strong> {metadata['description']}
        </div>

        <h2>Summary</h2>
        <div class="summary-grid">
            <div class="summary-card">
                <h3>Total Demos</h3>
                <div class="value">{summary['total']}</div>
            </div>
            <div class="summary-card">
                <h3>Passed</h3>
                <div class="value" style="color: #4CAF50;">{summary['passed']}</div>
                <div>{summary['success_rate']:.1f}% success rate</div>
            </div>
            <div class="summary-card failed">
                <h3>Failed</h3>
                <div class="value" style="color: #f44336;">{summary['failed']}</div>
            </div>
            <div class="summary-card">
                <h3>Skipped</h3>
                <div class="value">{summary['skipped']}</div>
            </div>
            <div class="summary-card">
                <h3>Total Time</h3>
                <div class="value">{_format_time(summary['total_time'])}</div>
                <div>Avg: {_format_time(summary['avg_time_per_demo'])}</div>
            </div>
            <div class="summary-card">
                <h3>Total Cost</h3>
                <div class="value">{_format_cost(summary['total_cost'])}</div>
                <div>Avg: {_format_cost(summary['avg_cost_per_demo'])}</div>
            </div>
        </div>

        <h2>Demo Details</h2>
        <table>
            <thead>
                <tr>
                    <th>#</th>
                    <th>Demo Name</th>
                    <th>Status</th>
                    <th>Preview Time</th>
                    <th>Validation Time</th>
                    <th>Total Cost</th>
                    <th>Download</th>
                </tr>
            </thead>
            <tbody>
"""

    for idx, demo in enumerate(report["demos"], 1):
        status_class = f"status-{demo['status']}"
        download_status = "Success" if demo["download"]["success"] else "Failed"
        total_cost = demo["preview"]["cost"] + demo["full_validation"]["cost"]

        html += f"""
                <tr>
                    <td>{idx}</td>
                    <td>{demo['demo_name']}</td>
                    <td><span class="status-badge {status_class}">{demo['status']}</span></td>
                    <td>{_format_time(demo['preview']['time_seconds'])}</td>
                    <td>{_format_time(demo['full_validation']['time_seconds'])}</td>
                    <td>{_format_cost(total_cost)}</td>
                    <td>{download_status}</td>
                </tr>
"""

    html += """
            </tbody>
        </table>
"""

    # Add errors section if any
    if report["errors"]:
        html += """
        <h2>Errors</h2>
"""
        for error in report["errors"]:
            error_details = error.get("error_details", "")
            html += f"""
        <div class="error-box">
            <h4>{error['demo_name']}</h4>
            <strong>Error:</strong> {error['error']}<br>
            <strong>Time:</strong> {error['timestamp']}
"""
            if error_details:
                html += f"""
            <div class="error-details">{error_details}</div>
"""
            html += """
        </div>
"""

    html += """
    </div>
</body>
</html>
"""

    return html


def save_report(
    report: Dict[str, Any],
    output_dir: str,
    format: str = "text",
    filename: Optional[str] = None
) -> str:
    """
    Save report to file.

    Args:
        report: Report dictionary
        output_dir: Directory to save report to
        format: Output format - "text", "json", or "html"
        filename: Custom filename (optional, will auto-generate if not provided)

    Returns:
        Path to saved report file

    Raises:
        ValueError: If format is not supported
    """
    # Create output directory if it doesn't exist
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    # Generate filename if not provided
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        env = report["metadata"]["environment"]
        filename = f"demo_test_report_{env}_{timestamp}"

    # Generate report content based on format
    if format == "text":
        content = _generate_text_report(report)
        file_ext = ".txt"
    elif format == "json":
        content = _generate_json_report(report)
        file_ext = ".json"
    elif format == "html":
        content = _generate_html_report(report)
        file_ext = ".html"
    else:
        raise ValueError(f"Unsupported format: {format}. Use 'text', 'json', or 'html'")

    # Ensure filename has correct extension
    if not filename.endswith(file_ext):
        filename = f"{filename}{file_ext}"

    # Write to file
    file_path = output_path / filename
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content)

    return str(file_path)


def print_report(report: Dict[str, Any]) -> None:
    """
    Print report to console in text format.

    Args:
        report: Report dictionary
    """
    print(_generate_text_report(report))


# Example usage
if __name__ == "__main__":
    # Create a sample report for testing
    report = create_report(
        email="test@example.com",
        environment="dev",
        test_description="Automated validation of all demo configurations"
    )

    # Add some sample results
    add_demo_result(report, "Investment Research", {
        "status": "passed",
        "demo_path": "demos/investment_research/",
        "preview_time": 45.2,
        "preview_results": {"rows_processed": 5, "validations_passed": 5},
        "preview_cost": 0.15,
        "full_validation_time": 180.5,
        "full_validation_results": {"rows_processed": 50, "validations_passed": 50},
        "full_cost": 0.82,
        "download_success": True,
        "session_id": "session_demo_20251010_123456_abc123"
    })

    add_demo_result(report, "Competitive Intelligence", {
        "status": "passed",
        "demo_path": "demos/competitive_intelligence/",
        "preview_time": 38.7,
        "preview_results": {"rows_processed": 5, "validations_passed": 5},
        "preview_cost": 0.12,
        "full_validation_time": 165.3,
        "full_validation_results": {"rows_processed": 45, "validations_passed": 45},
        "full_cost": 0.75,
        "download_success": True,
        "session_id": "session_demo_20251010_123512_def456"
    })

    add_demo_result(report, "Program Applications", {
        "status": "failed",
        "demo_path": "demos/program_applications/",
        "preview_time": 52.1,
        "preview_results": {"rows_processed": 5, "validations_passed": 5},
        "preview_cost": 0.18,
        "full_validation_time": 0.0,
        "full_validation_results": None,
        "full_cost": 0.0,
        "download_success": False,
        "error": "Timeout during full validation",
        "error_details": "Lambda function timed out after 300 seconds during batch processing",
        "session_id": "session_demo_20251010_123598_ghi789"
    })

    # Print to console
    print_report(report)

    # Save in all formats
    print("\n\nSaving reports...")
    text_path = save_report(report, "./test_results", format="text")
    print(f"Text report saved to: {text_path}")

    json_path = save_report(report, "./test_results", format="json")
    print(f"JSON report saved to: {json_path}")

    html_path = save_report(report, "./test_results", format="html")
    print(f"HTML report saved to: {html_path}")
