import os
import shutil
from pathlib import Path

def move_file(source_path, dest_dir, force_overwrite=True):
    """Moves a file to a destination directory.
    If force_overwrite is True, it will overwrite the destination if it exists.
    Source file will be deleted after successful copy.
    """
    source = Path(source_path)
    dest_directory = Path(dest_dir)
    
    if not source.exists():
        print(f"Source file not found: {source}")
        return

    if not dest_directory.is_dir():
        print(f"Destination is not a directory: {dest_directory}. Attempting to create it.")
        try:
            dest_directory.mkdir(parents=True, exist_ok=True)
            print(f"Created directory: {dest_directory}")
        except Exception as e:
            print(f"Error creating directory {dest_directory}: {e}")
            return

    dest_file = dest_directory / source.name

    try:
        if dest_file.exists() and force_overwrite:
            print(f"Destination file {dest_file} exists. Removing it first.")
            if dest_file.is_dir(): # Should not happen if source is a file
                shutil.rmtree(dest_file)
            else:
                os.remove(dest_file)
        
        # Use shutil.move for atomicity if possible, but copy then delete for clarity
        # shutil.move(str(source), str(dest_directory))
        shutil.copy2(str(source), str(dest_file)) # copy2 preserves metadata
        print(f"Copied: {source} -> {dest_file}")
        os.remove(source)
        print(f"Deleted source file: {source}")

    except Exception as e:
        print(f"Error moving file {source} to {dest_file}: {e}")

def delete_item(item_path_str):
    """Deletes a file or directory."""
    item_path = Path(item_path_str)
    try:
        if item_path.exists():
            if item_path.is_file():
                os.remove(item_path)
                print(f"Deleted file: {item_path}")
            elif item_path.is_dir():
                shutil.rmtree(item_path)
                print(f"Deleted directory: {item_path}")
        else:
            print(f"Item not found, cannot delete: {item_path}")
    except Exception as e:
        print(f"Error deleting {item_path}: {e}")

def main():
    project_root = Path.cwd() # Assumes script is run from project root
    print(f"Operating in project root: {project_root}")

    src_dir = project_root / "src"
    example_io_dir = project_root / "example_lambda_io"

    # Ensure target directories exist
    if not src_dir.exists():
        print(f"Warning: src directory {src_dir} does not exist. Some moves might fail.")
    
    example_io_dir.mkdir(parents=True, exist_ok=True)
    print(f"Ensured example_lambda_io directory exists: {example_io_dir}")

    # 1. Files to move from root to src/
    files_to_move_to_src = [
        "excel_batch_processor.py",
        "lambda_test_json_clean.py",
        "excel_test.py",
        "batch_validate.py",
        "prompts.yml" # This will overwrite prompts.yml in src if it exists
    ]
    print("\n--- Moving files to src/ ---")
    for f_name in files_to_move_to_src:
        move_file(project_root / f_name, src_dir)

    # 2. Files to move from root to example_lambda_io/
    files_to_move_to_example_io = [
        "perplexity_response_content.txt",
        "perplexity_response_full.json",
        "perplexity_response_raw.json"
    ]
    print("\n--- Moving files to example_lambda_io/ ---")
    for f_name in files_to_move_to_example_io:
        move_file(project_root / f_name, example_io_dir)
    
    # 3. Files to delete from root
    files_to_delete_from_root = [
        "Congresses Master List.xlsx", # The one at the root
        "column_config.yml",
        "column_config_template.yml",
        "enhanced_processor.py",
        "error_log.txt",
        "lambda_test_harness.py",
        "pytest.ini",
        "run_lambda_test.py",
        "simple_test.py",
        "test_lambda.py",
        "test_parallel_multiplex.py",
        "test_perplexity_response.py"
    ]
    print("\n--- Deleting files from root ---")
    for f_name in files_to_delete_from_root:
        delete_item(project_root / f_name)

    # 4. Directories to delete from root
    dirs_to_delete_from_root = [
        "tab_sanity",
        "test_events", # Note: If you need any specific test events from here for create_package.py, ensure they are backed up or moved elsewhere. We moved one specific to deployment/.
        "tests"
    ]
    print("\n--- Deleting directories from root ---")
    for dir_name in dirs_to_delete_from_root:
        delete_item(project_root / dir_name)
        
    print("\nCleanup script finished.")
    print("Please verify your project structure.")

if __name__ == "__main__":
    main() 