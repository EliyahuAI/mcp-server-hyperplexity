#!/usr/bin/env python3
"""
Compare the corrupted Excel file with Excel's repaired version to identify fixes.
"""

import zipfile
import xml.etree.ElementTree as ET
import difflib
import os
import sys

def extract_and_compare(original_file, repaired_file):
    """Compare internal XML files between original and repaired Excel files."""
    # Check if files exist
    if not os.path.exists(original_file):
        print(f"Error: Original file not found: {original_file}")
        return
    if not os.path.exists(repaired_file):
        print(f"Error: Repaired file not found: {repaired_file}")
        return
    
    print(f"\nComparing Excel files:")
    print(f"Original (corrupted): {original_file}")
    print(f"Repaired by Excel: {repaired_file}")
    print("="*60)
    
    try:
        with zipfile.ZipFile(original_file, 'r') as orig_zip, \
             zipfile.ZipFile(repaired_file, 'r') as repair_zip:
            
            # Get file lists
            orig_files = set(orig_zip.namelist())
            repair_files = set(repair_zip.namelist())
            
            # Check for differences in file lists
            only_in_orig = orig_files - repair_files
            only_in_repair = repair_files - orig_files
            
            if only_in_orig:
                print("\nFiles removed during repair:")
                for f in sorted(only_in_orig):
                    print(f"  - {f}")
            
            if only_in_repair:
                print("\nFiles added during repair:")
                for f in sorted(only_in_repair):
                    print(f"  + {f}")
            
            # Compare common files
            common_files = orig_files & repair_files
            
            print("\n\nDifferences in common files:")
            print("-"*60)
            
            differences_found = False
            
            for file_path in sorted(common_files):
                if file_path.endswith('.xml') or file_path.endswith('.rels'):
                    try:
                        orig_content = orig_zip.read(file_path).decode('utf-8')
                        repair_content = repair_zip.read(file_path).decode('utf-8')
                        
                        if orig_content != repair_content:
                            differences_found = True
                            print(f"\n### {file_path} ###")
                            
                            # For smaller files, show full diff
                            if len(orig_content) < 5000 and len(repair_content) < 5000:
                                diff = list(difflib.unified_diff(
                                    orig_content.splitlines(keepends=True),
                                    repair_content.splitlines(keepends=True),
                                    fromfile='original',
                                    tofile='repaired',
                                    n=3
                                ))
                                
                                if diff:
                                    print(''.join(diff[:50]))  # Show first 50 lines of diff
                                    if len(diff) > 50:
                                        print(f"... ({len(diff) - 50} more lines)")
                            else:
                                # For larger files, just show size difference
                                print(f"Size changed: {len(orig_content)} -> {len(repair_content)} bytes")
                                
                                # Try to identify specific issues
                                if 'sharedStrings.xml' in file_path:
                                    # Check for problematic characters
                                    check_shared_strings(orig_content, repair_content)
                                elif 'sheet' in file_path:
                                    # Check worksheet issues
                                    check_worksheet(orig_content, repair_content)
                                    
                                # Special analysis for sharedStrings.xml
                                if file_path == 'xl/sharedStrings.xml':
                                    print("\nAnalyzing sharedStrings.xml changes:")
                                    print(f"  String items: {orig_content.count('<t>') + orig_content.count('<t ')} -> {repair_content.count('<t>') + repair_content.count('<t ')}")
                                    
                                    # Check for double-escaped entities
                                    double_escaped_patterns = [
                                        ('&amp;amp;', '&amp;'),
                                        ('&amp;lt;', '&lt;'),
                                        ('&amp;gt;', '&gt;'),
                                        ('&amp;quot;', '&quot;'),
                                        ('&amp;apos;', '&apos;')
                                    ]
                                    
                                    for pattern, fixed in double_escaped_patterns:
                                        orig_count = orig_content.count(pattern)
                                        repair_count = repair_content.count(pattern)
                                        if orig_count > 0:
                                            print(f"  FOUND DOUBLE ESCAPING: {pattern} appears {orig_count} times in original!")
                                            print(f"  After repair: {pattern} appears {repair_count} times")
                                    
                                    # Also check actual content for other anomalies
                                    if orig_content.count('&amp;') != repair_content.count('&amp;'):
                                        print(f"  Ampersand count changed: {orig_content.count('&amp;')} -> {repair_content.count('&amp;')}")
                                
                                # Special analysis for comments1.xml
                                if file_path == 'xl/comments1.xml':
                                    print("\nAnalyzing comments1.xml changes:")
                                    
                                    # Check for double-escaped entities in comments
                                    for pattern, fixed in double_escaped_patterns:
                                        orig_count = orig_content.count(pattern)
                                        repair_count = repair_content.count(pattern)
                                        if orig_count > 0:
                                            print(f"  FOUND DOUBLE ESCAPING: {pattern} appears {orig_count} times in original!")
                                            print(f"  After repair: {pattern} appears {repair_count} times")
                    except Exception as e:
                        print(f"Error comparing {file_path}: {e}")
            
            if not differences_found:
                print("\nNo differences found in XML files!")
                
    except Exception as e:
        print(f"Error opening files: {e}")

def check_shared_strings(orig, repair):
    """Check for specific issues in sharedStrings.xml."""
    print("\nAnalyzing sharedStrings.xml changes:")
    
    # Count string items
    orig_count = orig.count('<si>')
    repair_count = repair.count('<si>')
    print(f"  String items: {orig_count} -> {repair_count}")
    
    # Check for escaped characters
    escapes = [('&amp;', '&'), ('&lt;', '<'), ('&gt;', '>'), ('&quot;', '"'), ('&apos;', "'")]
    for escaped, char in escapes:
        orig_escaped = orig.count(escaped)
        repair_escaped = repair.count(escaped)
        if orig_escaped != repair_escaped:
            print(f"  {escaped} count changed: {orig_escaped} -> {repair_escaped}")
    
    # Check for double escaping
    double_escapes = ['&amp;amp;', '&amp;lt;', '&amp;gt;', '&amp;quot;', '&amp;apos;']
    for de in double_escapes:
        if de in orig:
            count = orig.count(de)
            print(f"  FOUND DOUBLE ESCAPING: {de} appears {count} times in original!")
    
    # Look for specific problematic patterns
    if '&amp;amp;' in orig and '&amp;' in repair:
        print("  CONFIRMED: Excel fixed double-escaped ampersands!")

def check_worksheet(orig, repair):
    """Check for specific issues in worksheet files."""
    print("\nAnalyzing worksheet changes:")
    
    # Check comment count
    orig_comments = orig.count('</comment>')
    repair_comments = repair.count('</comment>')
    if orig_comments != repair_comments:
        print(f"  Comments: {orig_comments} -> {repair_comments}")
    
    # Check for formula issues
    orig_formulas = orig.count('<f>')
    repair_formulas = repair.count('<f>')
    if orig_formulas != repair_formulas:
        print(f"  Formulas: {orig_formulas} -> {repair_formulas}")

if __name__ == "__main__":
    # Use command line args if provided, otherwise use default filenames
    if len(sys.argv) == 3:
        orig_file = sys.argv[1]
        repair_file = sys.argv[2]
    else:
        # Check current directory first
        orig_file = "validation_results_enhanced.xlsx"
        repair_file = "validation_results_enhanced2.xlsx"
    
    extract_and_compare(orig_file, repair_file) 