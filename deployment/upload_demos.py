#!/usr/bin/env python3
"""
Demo Upload and Validation Script

This script validates and uploads two types of demos to S3:

1. Onboarding Demos (--demos-folder):
   - For new users to try the full validation flow
   - Each folder needs: data file (.xlsx/.csv), config.json, description.md
   - Uploaded to: s3://{bucket}/demos/{demo_name}/

2. Interactive Table Demos (--interactive-tables):
   - Pre-built tables for the public viewer
   - Each folder needs: table_metadata.json, optionally info.json
   - Uploaded to: s3://{bucket}/demos/interactive_tables/{table_name}/

Usage:
    # Onboarding demos
    python upload_demos.py --demos-folder ./demos --bucket hyperplexity-storage --dry-run
    python upload_demos.py --demos-folder ./demos --bucket hyperplexity-storage --upload

    # Interactive table demos
    python upload_demos.py --interactive-tables ./demos/interactive_tables --bucket hyperplexity-storage --dry-run
    python upload_demos.py --interactive-tables ./demos/interactive_tables --bucket hyperplexity-storage --upload

    # Both at once
    python upload_demos.py --demos-folder ./demos --interactive-tables ./demos/interactive_tables --bucket hyperplexity-storage --upload
"""

import os
import sys
import json
import argparse
import boto3
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re
import pandas as pd

class DemoValidator:
    def __init__(self, bucket_name: str, dry_run: bool = True):
        self.bucket_name = bucket_name
        self.dry_run = dry_run
        self.s3_client = boto3.client('s3') if not dry_run else None
        self.errors = []
        self.warnings = []
        self.validated_demos = []

    def log_error(self, message: str):
        self.errors.append(message)
        print(f"[ERROR] {message}")

    def log_warning(self, message: str):
        self.warnings.append(message)
        print(f"[WARNING] {message}")

    def log_info(self, message: str):
        print(f"[INFO] {message}")

    def validate_demo_folder(self, demo_path: Path) -> Optional[Dict]:
        """Validate a single demo folder and return demo metadata if valid."""
        demo_name = demo_path.name
        self.log_info(f"Validating demo: {demo_name}")

        # Check if folder exists
        if not demo_path.is_dir():
            self.log_error(f"Demo path is not a directory: {demo_path}")
            return None

        # Find required files
        files = list(demo_path.glob("*"))

        # Find data file (Excel or CSV)
        data_files = [f for f in files if f.suffix.lower() in ['.xlsx', '.xls', '.csv']]
        if len(data_files) == 0:
            self.log_error(f"No data file found in {demo_name} (expected .xlsx, .xls, or .csv)")
            return None
        elif len(data_files) > 1:
            self.log_warning(f"Multiple data files found in {demo_name}, using: {data_files[0].name}")
        data_file = data_files[0]

        # Find config file
        config_files = [f for f in files if f.suffix.lower() == '.json']
        if len(config_files) == 0:
            self.log_error(f"No config file found in {demo_name} (expected .json)")
            return None
        elif len(config_files) > 1:
            self.log_warning(f"Multiple config files found in {demo_name}, using: {config_files[0].name}")
        config_file = config_files[0]

        # Find description file
        desc_files = [f for f in files if f.suffix.lower() == '.md']
        if len(desc_files) == 0:
            self.log_error(f"No description file found in {demo_name} (expected .md)")
            return None
        elif len(desc_files) > 1:
            self.log_warning(f"Multiple description files found in {demo_name}, using: {desc_files[0].name}")
        desc_file = desc_files[0]

        # Validate data file
        if not self.validate_data_file(data_file):
            return None

        # Validate config file
        config_data = self.validate_config_file(config_file)
        if config_data is None:
            return None

        # Validate description file
        desc_data = self.validate_description_file(desc_file)
        if desc_data is None:
            return None

        # Create demo metadata
        demo_metadata = {
            'name': demo_name,
            'display_name': desc_data.get('display_name', demo_name.replace('_', ' ').title()),
            'description': desc_data.get('description', 'No description provided'),
            'data_file': data_file.name,
            'config_file': config_file.name,
            'description_file': desc_file.name,
            'data_file_path': str(data_file),
            'config_file_path': str(config_file),
            'description_file_path': str(desc_file),
            'config_data': config_data
        }

        self.log_info(f"Demo {demo_name} validation passed")
        return demo_metadata

    def validate_data_file(self, data_file: Path) -> bool:
        """Validate that the data file can be read and has content."""
        try:
            if data_file.suffix.lower() == '.csv':
                df = pd.read_csv(data_file)
            else:
                df = pd.read_excel(data_file)

            if df.empty:
                self.log_error(f"Data file {data_file.name} is empty")
                return False

            if len(df.columns) < 2:
                self.log_error(f"Data file {data_file.name} has fewer than 2 columns")
                return False

            self.log_info(f"Data file {data_file.name}: {len(df)} rows, {len(df.columns)} columns")
            return True

        except Exception as e:
            self.log_error(f"Failed to read data file {data_file.name}: {e}")
            return False

    def validate_config_file(self, config_file: Path) -> Optional[Dict]:
        """Validate that the config file is valid JSON with required structure."""
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)

            # Basic validation of config structure
            required_fields = ['validation_targets']
            for field in required_fields:
                if field not in config_data:
                    self.log_error(f"Config file {config_file.name} missing required field: {field}")
                    return None

            # Validate validation targets
            if not isinstance(config_data['validation_targets'], list):
                self.log_error(f"Config file {config_file.name}: validation_targets must be a list")
                return None

            if len(config_data['validation_targets']) == 0:
                self.log_error(f"Config file {config_file.name}: validation_targets cannot be empty")
                return None

            self.log_info(f"Config file {config_file.name}: {len(config_data['validation_targets'])} validation targets")
            return config_data

        except json.JSONDecodeError as e:
            self.log_error(f"Config file {config_file.name} is not valid JSON: {e}")
            return None
        except Exception as e:
            self.log_error(f"Failed to read config file {config_file.name}: {e}")
            return None

    def validate_description_file(self, desc_file: Path) -> Optional[Dict]:
        """Validate and parse the description markdown file."""
        try:
            with open(desc_file, 'r', encoding='utf-8') as f:
                content = f.read().strip()

            if not content:
                self.log_error(f"Description file {desc_file.name} is empty")
                return None

            # Parse metadata from markdown (simple format)
            desc_data = {'description': content}

            # Look for title/display name in first heading or bold text
            lines = content.split('\n')
            for line in lines:
                if line.startswith('# '):
                    desc_data['display_name'] = line[2:].strip()
                    break
                elif line.strip().startswith('**') and line.strip().endswith('**'):
                    # Handle **Title** format
                    desc_data['display_name'] = line.strip()[2:-2].strip()
                    break

            # Extract description (only first paragraph after heading/title)
            desc_lines = []
            skip_first_heading = False
            in_first_paragraph = False

            for line in lines:
                # Skip heading line (either # or **)
                if (line.startswith('# ') or (line.strip().startswith('**') and line.strip().endswith('**'))) and not skip_first_heading:
                    skip_first_heading = True
                    continue

                if skip_first_heading:
                    # Start collecting the first paragraph
                    if line.strip():  # Non-empty line
                        if not in_first_paragraph:
                            in_first_paragraph = True
                        desc_lines.append(line)
                    elif in_first_paragraph:
                        # Empty line after paragraph content - stop here
                        break

            if desc_lines:
                desc_data['description'] = '\n'.join(desc_lines).strip()

            if len(desc_data['description']) < 10:
                self.log_warning(f"Description in {desc_file.name} is very short")

            self.log_info(f"Description file {desc_file.name} parsed successfully")
            return desc_data

        except Exception as e:
            self.log_error(f"Failed to read description file {desc_file.name}: {e}")
            return None

    def validate_demos_folder(self, demos_folder: Path) -> List[Dict]:
        """Validate all demo folders in the demos directory."""
        self.log_info(f"Validating demos folder: {demos_folder}")

        if not demos_folder.exists():
            self.log_error(f"Demos folder does not exist: {demos_folder}")
            return []

        if not demos_folder.is_dir():
            self.log_error(f"Demos path is not a directory: {demos_folder}")
            return []

        # Find all subdirectories (demo folders)
        demo_folders = [d for d in demos_folder.iterdir() if d.is_dir()]

        if not demo_folders:
            self.log_error(f"No demo folders found in: {demos_folder}")
            return []

        self.log_info(f"Found {len(demo_folders)} demo folders")

        validated_demos = []
        for demo_folder in demo_folders:
            demo_metadata = self.validate_demo_folder(demo_folder)
            if demo_metadata:
                validated_demos.append(demo_metadata)

        return validated_demos

    def upload_demo_to_s3(self, demo: Dict) -> bool:
        """Upload a single demo to S3."""
        if self.dry_run:
            self.log_info(f"[DRY RUN] Would upload demo: {demo['name']}")
            return True

        try:
            # S3 key prefix for this demo
            s3_prefix = f"demos/{demo['name']}/"

            # Upload data file
            self.log_info(f"Uploading {demo['data_file']} to s3://{self.bucket_name}/{s3_prefix}{demo['data_file']}")
            self.s3_client.upload_file(
                demo['data_file_path'],
                self.bucket_name,
                f"{s3_prefix}{demo['data_file']}"
            )

            # Upload config file
            self.log_info(f"Uploading {demo['config_file']} to s3://{self.bucket_name}/{s3_prefix}{demo['config_file']}")
            self.s3_client.upload_file(
                demo['config_file_path'],
                self.bucket_name,
                f"{s3_prefix}{demo['config_file']}"
            )

            # Upload description file
            self.log_info(f"Uploading {demo['description_file']} to s3://{self.bucket_name}/{s3_prefix}{demo['description_file']}")
            self.s3_client.upload_file(
                demo['description_file_path'],
                self.bucket_name,
                f"{s3_prefix}{demo['description_file']}"
            )

            self.log_info(f"Successfully uploaded demo: {demo['name']}")
            return True

        except Exception as e:
            self.log_error(f"Failed to upload demo {demo['name']}: {e}")
            return False

    def upload_demos(self, demos: List[Dict]) -> int:
        """Upload all validated demos to S3."""
        if not demos:
            self.log_error("No demos to upload")
            return 0

        if self.dry_run:
            self.log_info(f"[DRY RUN] Would upload {len(demos)} demos to s3://{self.bucket_name}/demos/")
            for demo in demos:
                self.log_info(f"  - {demo['name']}: {demo['display_name']}")
            return len(demos)

        uploaded_count = 0
        for demo in demos:
            if self.upload_demo_to_s3(demo):
                uploaded_count += 1

        return uploaded_count

    def generate_summary(self, demos: List[Dict]):
        """Generate and print a summary of the validation/upload process."""
        print("\n" + "="*60)
        print("DEMO VALIDATION SUMMARY")
        print("="*60)

        if demos:
            print(f"✅ Validated demos: {len(demos)}")
            for demo in demos:
                print(f"   - {demo['name']}: {demo['display_name']}")
                print(f"     Description: {demo['description'][:100]}...")
                print(f"     Files: {demo['data_file']}, {demo['config_file']}, {demo['description_file']}")
                print()
        else:
            print("❌ No valid demos found")

        if self.warnings:
            print(f"⚠️  Warnings: {len(self.warnings)}")
            for warning in self.warnings:
                print(f"   - {warning}")
            print()

        if self.errors:
            print(f"❌ Errors: {len(self.errors)}")
            for error in self.errors:
                print(f"   - {error}")
            print()
        else:
            print("✅ No errors found")

        if self.dry_run:
            print("\n[DRY RUN] Use --upload to actually upload to S3")
        else:
            print(f"\n✅ Upload complete! Demos available at s3://{self.bucket_name}/demos/")


class InteractiveTableValidator:
    """Validator for interactive table demos (pre-built tables for the viewer)."""

    def __init__(self, bucket_name: str, dry_run: bool = True):
        self.bucket_name = bucket_name
        self.dry_run = dry_run
        self.s3_client = boto3.client('s3') if not dry_run else None
        self.errors = []
        self.warnings = []

    def log_error(self, message: str):
        self.errors.append(message)
        print(f"[ERROR] {message}")

    def log_warning(self, message: str):
        self.warnings.append(message)
        print(f"[WARNING] {message}")

    def log_info(self, message: str):
        print(f"[INFO] {message}")

    def validate_table_folder(self, table_path: Path) -> Optional[Dict]:
        """Validate a single interactive table folder and return metadata if valid."""
        table_name = table_path.name
        self.log_info(f"Validating interactive table: {table_name}")

        # Check if folder exists
        if not table_path.is_dir():
            self.log_error(f"Table path is not a directory: {table_path}")
            return None

        # Find required files
        metadata_file = table_path / "table_metadata.json"
        info_file = table_path / "info.json"

        if not metadata_file.exists():
            self.log_error(f"No table_metadata.json found in {table_name}")
            return None

        # Validate table_metadata.json
        metadata = self.validate_metadata_file(metadata_file)
        if metadata is None:
            return None

        # Check for optional info.json
        info_data = None
        if info_file.exists():
            info_data = self.validate_info_file(info_file)
            if info_data:
                self.log_info(f"Found info.json with display_name: {info_data.get('display_name', 'N/A')}")

        # Generate display name
        display_name = table_name.replace('-', ' ').replace('_', ' ').title()
        if info_data and info_data.get('display_name'):
            display_name = info_data['display_name']

        # Create table metadata
        table_data = {
            'name': table_name,
            'display_name': display_name,
            'metadata_file_path': str(metadata_file),
            'info_file_path': str(info_file) if info_file.exists() else None,
            'has_info': info_file.exists(),
            'row_count': len(metadata.get('rows', [])),
            'column_count': len(metadata.get('columns', []))
        }

        self.log_info(f"Interactive table {table_name} validation passed ({table_data['row_count']} rows, {table_data['column_count']} columns)")
        return table_data

    def validate_metadata_file(self, metadata_file: Path) -> Optional[Dict]:
        """Validate that table_metadata.json is valid and has required structure."""
        try:
            with open(metadata_file, 'r', encoding='utf-8') as f:
                metadata = json.load(f)

            # Check for required fields
            if 'rows' not in metadata:
                self.log_error(f"table_metadata.json missing 'rows' field")
                return None

            if 'columns' not in metadata:
                self.log_error(f"table_metadata.json missing 'columns' field")
                return None

            if not isinstance(metadata['rows'], list):
                self.log_error(f"table_metadata.json 'rows' must be a list")
                return None

            if not isinstance(metadata['columns'], list):
                self.log_error(f"table_metadata.json 'columns' must be a list")
                return None

            if len(metadata['rows']) == 0:
                self.log_warning(f"table_metadata.json has no rows")

            if len(metadata['columns']) == 0:
                self.log_error(f"table_metadata.json has no columns")
                return None

            return metadata

        except json.JSONDecodeError as e:
            self.log_error(f"table_metadata.json is not valid JSON: {e}")
            return None
        except Exception as e:
            self.log_error(f"Failed to read table_metadata.json: {e}")
            return None

    def validate_info_file(self, info_file: Path) -> Optional[Dict]:
        """Validate optional info.json file."""
        try:
            with open(info_file, 'r', encoding='utf-8') as f:
                info = json.load(f)
            return info
        except json.JSONDecodeError as e:
            self.log_warning(f"info.json is not valid JSON: {e}")
            return None
        except Exception as e:
            self.log_warning(f"Failed to read info.json: {e}")
            return None

    def validate_tables_folder(self, tables_folder: Path) -> List[Dict]:
        """Validate all interactive table folders."""
        self.log_info(f"Validating interactive tables folder: {tables_folder}")

        if not tables_folder.exists():
            self.log_error(f"Interactive tables folder does not exist: {tables_folder}")
            return []

        if not tables_folder.is_dir():
            self.log_error(f"Interactive tables path is not a directory: {tables_folder}")
            return []

        # Find all subdirectories (table folders)
        table_folders = [d for d in tables_folder.iterdir() if d.is_dir()]

        if not table_folders:
            self.log_error(f"No table folders found in: {tables_folder}")
            return []

        self.log_info(f"Found {len(table_folders)} table folders")

        validated_tables = []
        for table_folder in sorted(table_folders):
            table_data = self.validate_table_folder(table_folder)
            if table_data:
                validated_tables.append(table_data)

        return validated_tables

    def upload_table_to_s3(self, table: Dict) -> bool:
        """Upload a single interactive table to S3."""
        if self.dry_run:
            self.log_info(f"[DRY RUN] Would upload interactive table: {table['name']}")
            return True

        try:
            # S3 key prefix for interactive tables
            s3_prefix = f"demos/interactive_tables/{table['name']}/"

            # Upload table_metadata.json
            self.log_info(f"Uploading table_metadata.json to s3://{self.bucket_name}/{s3_prefix}table_metadata.json")
            self.s3_client.upload_file(
                table['metadata_file_path'],
                self.bucket_name,
                f"{s3_prefix}table_metadata.json"
            )

            # Upload info.json if it exists
            if table['has_info'] and table['info_file_path']:
                self.log_info(f"Uploading info.json to s3://{self.bucket_name}/{s3_prefix}info.json")
                self.s3_client.upload_file(
                    table['info_file_path'],
                    self.bucket_name,
                    f"{s3_prefix}info.json"
                )

            self.log_info(f"Successfully uploaded interactive table: {table['name']}")
            return True

        except Exception as e:
            self.log_error(f"Failed to upload interactive table {table['name']}: {e}")
            return False

    def upload_tables(self, tables: List[Dict]) -> int:
        """Upload all validated interactive tables to S3."""
        if not tables:
            self.log_error("No interactive tables to upload")
            return 0

        if self.dry_run:
            self.log_info(f"[DRY RUN] Would upload {len(tables)} interactive tables to s3://{self.bucket_name}/demos/interactive_tables/")
            for table in tables:
                self.log_info(f"  - {table['name']}: {table['display_name']} ({table['row_count']} rows)")
            return len(tables)

        uploaded_count = 0
        for table in tables:
            if self.upload_table_to_s3(table):
                uploaded_count += 1

        return uploaded_count

    def generate_summary(self, tables: List[Dict]):
        """Generate and print a summary of the validation/upload process."""
        print("\n" + "="*60)
        print("INTERACTIVE TABLE VALIDATION SUMMARY")
        print("="*60)

        if tables:
            print(f"✅ Validated interactive tables: {len(tables)}")
            for table in tables:
                print(f"   - {table['name']}: {table['display_name']}")
                print(f"     Size: {table['row_count']} rows, {table['column_count']} columns")
                print(f"     Has info.json: {'Yes' if table['has_info'] else 'No'}")
                print()
        else:
            print("❌ No valid interactive tables found")

        if self.warnings:
            print(f"⚠️  Warnings: {len(self.warnings)}")
            for warning in self.warnings:
                print(f"   - {warning}")
            print()

        if self.errors:
            print(f"❌ Errors: {len(self.errors)}")
            for error in self.errors:
                print(f"   - {error}")
            print()
        else:
            print("✅ No errors found")

        if self.dry_run:
            print("\n[DRY RUN] Use --upload to actually upload to S3")
        else:
            print(f"\n✅ Upload complete! Interactive tables available at s3://{self.bucket_name}/demos/interactive_tables/")


def main():
    parser = argparse.ArgumentParser(
        description="Validate and upload demo folders to S3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate onboarding demos (dry run)
  python upload_demos.py --demos-folder ./demos --bucket hyperplexity-storage --dry-run

  # Upload onboarding demos to S3
  python upload_demos.py --demos-folder ./demos --bucket hyperplexity-storage --upload

  # Validate interactive table demos (dry run)
  python upload_demos.py --interactive-tables ./demos/interactive_tables --bucket hyperplexity-storage --dry-run

  # Upload interactive table demos to S3
  python upload_demos.py --interactive-tables ./demos/interactive_tables --bucket hyperplexity-storage --upload

  # Upload both types at once
  python upload_demos.py --demos-folder ./demos --interactive-tables ./demos/interactive_tables --bucket hyperplexity-storage --upload

Expected folder structures:

  Onboarding demos (--demos-folder):
  demos/
  ├── financial_portfolio/
  │   ├── portfolio_data.xlsx
  │   ├── portfolio_config.json
  │   └── description.md
  └── sales_leads/
      ├── leads_data.csv
      ├── leads_config.json
      └── description.md

  Interactive tables (--interactive-tables):
  demos/interactive_tables/
  ├── ai_research_tools/
  │   ├── table_metadata.json
  │   └── info.json (optional)
  └── competitive_analysis/
      └── table_metadata.json
        """
    )

    parser.add_argument(
        '--demos-folder',
        type=str,
        help='Path to local demos folder containing onboarding demo subfolders'
    )

    parser.add_argument(
        '--interactive-tables',
        type=str,
        help='Path to local folder containing interactive table demos (table_metadata.json)'
    )

    parser.add_argument(
        '--bucket',
        type=str,
        default='hyperplexity-storage',
        help='S3 bucket name (default: hyperplexity-storage)'
    )

    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate demos without uploading to S3'
    )
    group.add_argument(
        '--upload',
        action='store_true',
        help='Validate and upload demos to S3'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )

    args = parser.parse_args()

    # Require at least one demo type
    if not args.demos_folder and not args.interactive_tables:
        parser.error("At least one of --demos-folder or --interactive-tables is required")

    has_errors = False

    print(f"Demo Upload Script")
    print(f"S3 bucket: {args.bucket}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'UPLOAD'}")
    print("="*60)

    # Handle onboarding demos
    if args.demos_folder:
        demos_folder = Path(args.demos_folder).resolve()
        print(f"\n[ONBOARDING DEMOS] Folder: {demos_folder}")
        print("-" * 60)

        validator = DemoValidator(
            bucket_name=args.bucket,
            dry_run=args.dry_run
        )

        validated_demos = validator.validate_demos_folder(demos_folder)

        if validated_demos and args.upload:
            uploaded_count = validator.upload_demos(validated_demos)
            print(f"\n✅ Successfully uploaded {uploaded_count}/{len(validated_demos)} onboarding demos")

        validator.generate_summary(validated_demos)

        if validator.errors:
            has_errors = True

    # Handle interactive table demos
    if args.interactive_tables:
        tables_folder = Path(args.interactive_tables).resolve()
        print(f"\n[INTERACTIVE TABLES] Folder: {tables_folder}")
        print("-" * 60)

        table_validator = InteractiveTableValidator(
            bucket_name=args.bucket,
            dry_run=args.dry_run
        )

        validated_tables = table_validator.validate_tables_folder(tables_folder)

        if validated_tables and args.upload:
            uploaded_count = table_validator.upload_tables(validated_tables)
            print(f"\n✅ Successfully uploaded {uploaded_count}/{len(validated_tables)} interactive tables")

        table_validator.generate_summary(validated_tables)

        if table_validator.errors:
            has_errors = True

    # Exit with error code if there were errors
    if has_errors:
        sys.exit(1)


if __name__ == '__main__':
    main()