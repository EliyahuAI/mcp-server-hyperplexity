#!/usr/bin/env python3
"""
Demo Upload and Validation Script

This script validates a local demos folder structure and uploads it to S3.
Each demo folder should contain:
- A data file (Excel or CSV)
- A JSON configuration file
- A markdown file with description

Usage:
    python upload_demos.py --demos-folder ./demos --bucket hyperplexity-storage --dry-run
    python upload_demos.py --demos-folder ./demos --bucket hyperplexity-storage --upload
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


def main():
    parser = argparse.ArgumentParser(
        description="Validate and upload demo folders to S3",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate demos folder (dry run)
  python upload_demos.py --demos-folder ./demos --bucket hyperplexity-storage --dry-run

  # Upload demos to S3
  python upload_demos.py --demos-folder ./demos --bucket hyperplexity-storage --upload

  # Upload to specific environment bucket
  python upload_demos.py --demos-folder ./demos --bucket hyperplexity-storage-dev --upload

Expected folder structure:
  demos/
  ├── financial_portfolio/
  │   ├── portfolio_data.xlsx
  │   ├── portfolio_config.json
  │   └── description.md
  └── sales_leads/
      ├── leads_data.csv
      ├── leads_config.json
      └── description.md
        """
    )

    parser.add_argument(
        '--demos-folder',
        type=str,
        required=True,
        help='Path to local demos folder containing demo subfolders'
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

    # Initialize validator
    validator = DemoValidator(
        bucket_name=args.bucket,
        dry_run=args.dry_run
    )

    # Convert path
    demos_folder = Path(args.demos_folder).resolve()

    print(f"Demo Upload Script")
    print(f"Demos folder: {demos_folder}")
    print(f"S3 bucket: {args.bucket}")
    print(f"Mode: {'DRY RUN' if args.dry_run else 'UPLOAD'}")
    print("-" * 60)

    # Validate demos
    validated_demos = validator.validate_demos_folder(demos_folder)

    # Upload if requested and demos are valid
    if validated_demos and args.upload:
        uploaded_count = validator.upload_demos(validated_demos)
        print(f"\n✅ Successfully uploaded {uploaded_count}/{len(validated_demos)} demos")

    # Generate summary
    validator.generate_summary(validated_demos)

    # Exit with error code if there were errors
    if validator.errors:
        sys.exit(1)


if __name__ == '__main__':
    main()