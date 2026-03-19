#!/usr/bin/env python3
"""
Upload MCP example scripts and the API guide to S3.

Targets:
  mcp/examples/*.py        → s3://{bucket}/website_downloads/examples/*.py
  mcp/README.md            → s3://{bucket}/website_downloads/API_GUIDE.md
  frontend/API_GUIDE.html  → s3://{bucket}/website_downloads/API_GUIDE.html

The HTML file is served at eliyahu.ai/api-guide (via CloudFront).
Generate it first with:  python3 frontend/md_to_html.py

Usage:
    # Dry run (list what would be uploaded)
    python upload_api_docs.py --dry-run

    # Upload
    python upload_api_docs.py --upload

    # Override defaults
    python upload_api_docs.py --upload --bucket my-bucket \
        --examples ../mcp/examples --api-guide ../mcp/README.md \
        --api-guide-html ../frontend/API_GUIDE.html
"""

import argparse
import sys
from pathlib import Path
from typing import List, Tuple

import boto3

BUCKET = "hyperplexity-storage"
REPO_ROOT = Path(__file__).parent.parent

DEFAULTS = {
    "examples_dir":   REPO_ROOT / "mcp" / "examples",
    "api_guide":      REPO_ROOT / "mcp" / "README.md",
    "api_guide_html": REPO_ROOT / "frontend" / "API_GUIDE.html",
}

_CONTENT_TYPES = {
    ".py":   "text/x-python",
    ".md":   "text/markdown",
    ".html": "text/html",
}


def build_manifest(examples_dir: Path, api_guide: Path, api_guide_html: Path) -> List[Tuple[Path, str]]:
    """Return [(local_path, s3_key), ...] for everything to upload."""
    manifest: List[Tuple[Path, str]] = []

    for f in sorted(examples_dir.glob("*.py")):
        manifest.append((f, f"website_downloads/examples/{f.name}"))

    manifest.append((api_guide,      "website_downloads/API_GUIDE.md"))
    manifest.append((api_guide_html, "website_downloads/API_GUIDE.html"))

    return manifest


def run(manifest: List[Tuple[Path, str]], bucket: str, dry_run: bool) -> bool:
    s3 = None if dry_run else boto3.client("s3")
    ok = True

    for local, key in manifest:
        if not local.exists():
            print(f"[ERROR] missing: {local}")
            ok = False
            continue

        url = f"s3://{bucket}/{key}"
        if dry_run:
            print(f"  {local.name:40s} → {url}")
        else:
            ct = _CONTENT_TYPES.get(local.suffix, "application/octet-stream")
            try:
                s3.upload_file(
                    str(local), bucket, key,
                    ExtraArgs={
                        "ContentType": ct,
                        "ContentDisposition": f"attachment; filename={local.name}",
                    },
                )
                print(f"  OK  {local.name:40s} → {url}")
            except Exception as exc:
                print(f"  ERR {local.name}: {exc}")
                ok = False

    return ok


def main() -> None:
    parser = argparse.ArgumentParser(description="Upload MCP examples + API guide to S3")

    parser.add_argument(
        "--examples",
        default=str(DEFAULTS["examples_dir"]),
        metavar="DIR",
        help=f"Path to examples folder (default: {DEFAULTS['examples_dir']})",
    )
    parser.add_argument(
        "--api-guide",
        default=str(DEFAULTS["api_guide"]),
        metavar="FILE",
        help=f"Path to README.md / API guide markdown (default: {DEFAULTS['api_guide']})",
    )
    parser.add_argument(
        "--api-guide-html",
        default=str(DEFAULTS["api_guide_html"]),
        metavar="FILE",
        help=f"Path to API_GUIDE.html (default: {DEFAULTS['api_guide_html']})",
    )
    parser.add_argument(
        "--bucket",
        default=BUCKET,
        help=f"S3 bucket (default: {BUCKET})",
    )

    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="List files without uploading")
    mode.add_argument("--upload",  action="store_true", help="Upload files to S3")

    args = parser.parse_args()

    examples_dir   = Path(args.examples).resolve()
    api_guide      = Path(args.api_guide).resolve()
    api_guide_html = Path(args.api_guide_html).resolve()

    manifest = build_manifest(examples_dir, api_guide, api_guide_html)

    print(f"{'DRY RUN' if args.dry_run else 'UPLOAD'} — {len(manifest)} file(s) → s3://{args.bucket}/website_downloads/\n")
    ok = run(manifest, args.bucket, dry_run=args.dry_run)

    if args.dry_run:
        print("\nRun with --upload to push to S3.")

    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
