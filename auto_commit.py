#!/usr/bin/env python3
"""
Auto-commit script that analyzes git diffs and generates appropriate commit messages
"""

import subprocess
import sys
import re
from collections import defaultdict

def run_git_command(cmd):
    """Run a git command and return the output"""
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, check=True)
        return result.stdout.strip()
    except subprocess.CalledProcessError as e:
        print(f"[ERROR] Git command failed: {cmd}")
        print(f"Error: {e.stderr}")
        return None

def analyze_file_changes():
    """Analyze the changes in the repository"""
    # Get status
    status_output = run_git_command("git status --porcelain")
    if not status_output:
        print("[INFO] No changes to commit")
        return None
    
    # Get diff stats
    diff_stats = run_git_command("git diff --stat")
    
    # Get diff summary
    diff_summary = run_git_command("git diff --name-status")
    
    # Parse changes
    changes = defaultdict(list)
    if diff_summary:
        for line in diff_summary.split('\n'):
            if line.strip():
                parts = line.split('\t')
                if len(parts) >= 2:
                    status = parts[0]
                    filename = parts[1]
                    changes[status].append(filename)
    
    # Also check staged changes
    staged_diff = run_git_command("git diff --cached --name-status")
    if staged_diff:
        for line in staged_diff.split('\n'):
            if line.strip():
                parts = line.split('\t')
                if len(parts) >= 2:
                    status = parts[0]
                    filename = parts[1]
                    changes[status].append(filename)
    
    return changes, diff_stats, status_output

def categorize_changes(changes):
    """Categorize changes by type"""
    categories = {
        'config': [],
        'docs': [],
        'lambdas': [],
        'frontend': [],
        'tests': [],
        'deployment': [],
        'core': [],
        'other': []
    }
    
    for status, files in changes.items():
        for file in files:
            file_lower = file.lower()
            
            if any(x in file_lower for x in ['config', '.json', '.yml', '.yaml']):
                categories['config'].append((status, file))
            elif any(x in file_lower for x in ['.md', 'readme', 'doc']):
                categories['docs'].append((status, file))
            elif 'lambda' in file_lower or '/lambdas/' in file:
                categories['lambdas'].append((status, file))
            elif any(x in file_lower for x in ['frontend', '.html', '.php', '.css', '.js']):
                categories['frontend'].append((status, file))
            elif 'test' in file_lower:
                categories['tests'].append((status, file))
            elif any(x in file_lower for x in ['deploy', 'requirement']):
                categories['deployment'].append((status, file))
            elif any(x in file_lower for x in ['src/', 'core/', '.py']) and 'test' not in file_lower:
                categories['core'].append((status, file))
            else:
                categories['other'].append((status, file))
    
    return categories

def generate_commit_message(categories, diff_stats):
    """Generate a meaningful commit message based on changes"""
    
    # Count total changes
    total_files = sum(len(files) for files in categories.values())
    
    # Determine primary change type
    primary_changes = []
    
    if categories['lambdas']:
        primary_changes.append('lambda functions')
    if categories['frontend']:
        primary_changes.append('frontend')
    if categories['config']:
        primary_changes.append('configuration')
    if categories['core']:
        primary_changes.append('core functionality')
    if categories['deployment']:
        primary_changes.append('deployment')
    if categories['tests']:
        primary_changes.append('tests')
    if categories['docs']:
        primary_changes.append('documentation')
    
    # Generate title
    if len(primary_changes) == 1:
        title = f"feat: Update {primary_changes[0]}"
    elif len(primary_changes) <= 3:
        title = f"feat: Update {', '.join(primary_changes[:-1])} and {primary_changes[-1]}"
    else:
        title = f"feat: Major updates across {len(primary_changes)} components"
    
    # Generate body
    body_parts = []
    
    if categories['lambdas']:
        lambda_count = len(categories['lambdas'])
        body_parts.append(f"- Updated {lambda_count} lambda function files")
    
    if categories['frontend']:
        frontend_count = len(categories['frontend'])
        body_parts.append(f"- Modified {frontend_count} frontend files")
    
    if categories['config']:
        config_count = len(categories['config'])
        body_parts.append(f"- Updated {config_count} configuration files")
    
    if categories['core']:
        core_count = len(categories['core'])
        body_parts.append(f"- Enhanced {core_count} core system files")
    
    if categories['deployment']:
        deploy_count = len(categories['deployment'])
        body_parts.append(f"- Updated {deploy_count} deployment files")
    
    if categories['tests']:
        test_count = len(categories['tests'])
        body_parts.append(f"- Modified {test_count} test files")
    
    if categories['docs']:
        doc_count = len(categories['docs'])
        body_parts.append(f"- Updated {doc_count} documentation files")
    
    body_parts.append(f"- Total files changed: {total_files}")
    
    # Add diff stats summary
    if diff_stats:
        lines = diff_stats.split('\n')
        if len(lines) > 1:
            summary_line = lines[-1]
            body_parts.append(f"- {summary_line}")
    
    body = '\n'.join(body_parts)
    
    commit_message = f"""{title}

{body}

[AUTOMATED] Generated with [Claude Code](https://claude.ai/code)

Co-Authored-By: Claude <noreply@anthropic.com>"""
    
    return commit_message

def main():
    """Main function"""
    print("[INFO] Analyzing repository changes...")
    
    # Analyze changes
    result = analyze_file_changes()
    if not result:
        return
    
    changes, diff_stats, status_output = result
    
    # Categorize changes
    categories = categorize_changes(changes)
    
    # Generate commit message
    commit_message = generate_commit_message(categories, diff_stats)
    
    print("\n[INFO] Generated commit message:")
    print("=" * 50)
    print(commit_message)
    print("=" * 50)
    
    # Ask for confirmation
    response = input("\n[PROMPT] Proceed with commit and push? (y/n): ").lower().strip()
    
    if response == 'y' or response == 'yes':
        # Add all changes
        print("[INFO] Adding all changes...")
        add_result = run_git_command("git add .")
        
        # Commit with message
        print("[INFO] Creating commit...")
        commit_cmd = f'git commit -m "{commit_message.replace('"', '\\"')}"'
        commit_result = run_git_command(commit_cmd)
        
        if commit_result is not None:
            print("[SUCCESS] Commit created successfully")
            
            # Push to remote
            print("[INFO] Pushing to remote...")
            push_result = run_git_command("git push")
            
            if push_result is not None:
                print("[SUCCESS] Changes pushed successfully")
            else:
                print("[ERROR] Failed to push changes")
        else:
            print("[ERROR] Failed to create commit")
    else:
        print("[INFO] Operation cancelled")

if __name__ == "__main__":
    main()