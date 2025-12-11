"""
Extract claims from Chex analysis Excel files to JSON format.

This script reads the Chex validation output Excel files and creates a consolidated
JSON file with all claims, their validation status, sources, and citations from cell comments.

Usage:
    python extract_claims_to_json.py [input_xlsx] [output_json]

    If no arguments provided, uses the most recent Chex analysis file in data_room/
"""

import pandas as pd
import openpyxl
import json
import sys
import os
from pathlib import Path
from datetime import datetime


def extract_cell_comments(xlsx_path: str) -> dict:
    """
    Extract all cell comments from the Excel file.

    Returns a dict mapping (row, col) -> comment_text
    """
    wb = openpyxl.load_workbook(xlsx_path)
    ws = wb.active

    comments = {}
    for row in ws.iter_rows():
        for cell in row:
            if cell.comment:
                comments[(cell.row, cell.column)] = cell.comment.text

    return comments


def parse_comment_citations(comment_text: str) -> dict:
    """
    Parse a cell comment to extract key citation and sources.

    Returns dict with:
        - key_citation: The primary citation text and URL
        - sources: List of all sources mentioned
    """
    result = {
        "key_citation": None,
        "sources": []
    }

    if not comment_text:
        return result

    lines = comment_text.split('\n')

    # Look for Key Citation
    in_sources = False
    current_source = []

    for line in lines:
        line = line.strip()

        if line.startswith("Key Citation:"):
            result["key_citation"] = line.replace("Key Citation:", "").strip()
        elif line.startswith("Sources:"):
            in_sources = True
        elif in_sources and line.startswith("["):
            # New source entry
            if current_source:
                result["sources"].append(" ".join(current_source))
            current_source = [line]
        elif in_sources and current_source:
            current_source.append(line)

    # Don't forget the last source
    if current_source:
        result["sources"].append(" ".join(current_source))

    return result


def extract_claims(xlsx_path: str) -> list:
    """
    Extract all claims from a Chex analysis Excel file.

    Returns a list of claim dictionaries.
    """
    # Read the main data
    df = pd.read_excel(xlsx_path, sheet_name=0)

    # Extract cell comments
    comments = extract_cell_comments(xlsx_path)

    # Get column indices for comment extraction
    # Typically: I=Reference Description, J=What Reference Says, K=Qualified Fact, L=Support Level, M=Validation Notes
    col_map = {col: idx + 1 for idx, col in enumerate(df.columns)}

    claims = []

    for idx, row in df.iterrows():
        excel_row = idx + 2  # Excel rows are 1-indexed and have header

        claim = {
            "claim_id": str(row.get("Claim ID", f"claim_{idx+1:03d}")),
            "order": int(row.get("Claim Order", idx + 1)) if pd.notna(row.get("Claim Order")) else idx + 1,
            "statement": str(row.get("Statement", "")) if pd.notna(row.get("Statement")) else "",
            "context": str(row.get("Context", "")) if pd.notna(row.get("Context")) else "",
            "text_location": str(row.get("Text Location", "")) if pd.notna(row.get("Text Location")) else "",
            "reference": str(row.get("Reference", "")) if pd.notna(row.get("Reference")) else "",
            "supporting_data": str(row.get("Supporting Data", "")) if pd.notna(row.get("Supporting Data")) else None,
            "criticality": str(row.get("Claim Criticality", "")) if pd.notna(row.get("Claim Criticality")) else "",
            "reference_description": str(row.get("Reference Description", "")) if pd.notna(row.get("Reference Description")) else "",
            "what_reference_says": str(row.get("What Reference Says", "")) if pd.notna(row.get("What Reference Says")) else "",
            "qualified_fact": str(row.get("Qualified Fact", "")) if pd.notna(row.get("Qualified Fact")) else "",
            "support_level": str(row.get("Support Level", "")) if pd.notna(row.get("Support Level")) else "",
            "validation_notes": str(row.get("Validation Notes", "")) if pd.notna(row.get("Validation Notes")) else "",
            "citations": {}
        }

        # Extract citations from cell comments
        # Look for comments in the key columns (I, J, K, L, M = columns 9, 10, 11, 12, 13)
        for col_name, col_letter, col_num in [
            ("reference_description", "I", 9),
            ("what_reference_says", "J", 10),
            ("qualified_fact", "K", 11),
            ("support_level", "L", 12),
            ("validation_notes", "M", 13)
        ]:
            comment_key = (excel_row, col_num)
            if comment_key in comments:
                parsed = parse_comment_citations(comments[comment_key])
                if parsed["key_citation"] or parsed["sources"]:
                    claim["citations"][col_name] = parsed

        # Clean up None values
        claim = {k: v for k, v in claim.items() if v is not None and v != ""}

        claims.append(claim)

    return claims


def create_claims_json(xlsx_path: str, output_path: str = None) -> str:
    """
    Create a JSON file from the Chex analysis Excel file.

    Args:
        xlsx_path: Path to the input Excel file
        output_path: Path for output JSON (optional, auto-generated if not provided)

    Returns:
        Path to the created JSON file
    """
    claims = extract_claims(xlsx_path)

    # Create output structure
    output = {
        "_metadata": {
            "source_file": os.path.basename(xlsx_path),
            "extracted_at": datetime.now().isoformat(),
            "total_claims": len(claims),
            "support_level_summary": {}
        },
        "claims": claims
    }

    # Calculate support level summary
    for claim in claims:
        level = claim.get("support_level", "Unknown")
        # Extract just the level number/name
        if "5" in level:
            key = "Level 5 (Confirmed)"
        elif "4" in level:
            key = "Level 4 (Supported)"
        elif "3" in level:
            key = "Level 3 (Partial)"
        elif "2" in level:
            key = "Level 2 (Unclear)"
        elif "1" in level:
            key = "Level 1 (Unsupported)"
        else:
            key = "Unknown"

        output["_metadata"]["support_level_summary"][key] = \
            output["_metadata"]["support_level_summary"].get(key, 0) + 1

    # Generate output path if not provided
    if output_path is None:
        base_name = Path(xlsx_path).stem
        output_path = str(Path(xlsx_path).parent / f"{base_name}_claims.json")

    # Write JSON with nice formatting
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    return output_path


def find_latest_chex_file(data_room_path: str = "data_room") -> str:
    """Find the most recent Chex analysis file in the data_room directory."""
    pattern = "Supporting-4.Market_Analysis_Claims_Analysis_Chex_*.xlsx"
    files = list(Path(data_room_path).glob(pattern))

    if not files:
        raise FileNotFoundError(f"No Chex analysis files found matching {pattern} in {data_room_path}")

    # Sort by modification time, newest first
    files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
    return str(files[0])


def main():
    """Main entry point."""
    # Determine input file
    if len(sys.argv) > 1:
        xlsx_path = sys.argv[1]
    else:
        try:
            xlsx_path = find_latest_chex_file()
            print(f"Using most recent file: {xlsx_path}")
        except FileNotFoundError as e:
            print(f"Error: {e}")
            print("Usage: python extract_claims_to_json.py [input_xlsx] [output_json]")
            sys.exit(1)

    # Determine output file
    output_path = sys.argv[2] if len(sys.argv) > 2 else None

    # Extract and save
    try:
        result_path = create_claims_json(xlsx_path, output_path)
        print(f"Claims extracted to: {result_path}")

        # Print summary
        with open(result_path, 'r', encoding='utf-8') as f:
            data = json.load(f)

        print(f"\nSummary:")
        print(f"  Total claims: {data['_metadata']['total_claims']}")
        print(f"  Support levels:")
        for level, count in sorted(data['_metadata']['support_level_summary'].items()):
            print(f"    {level}: {count}")

    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
