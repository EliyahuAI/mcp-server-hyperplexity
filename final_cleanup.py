import os
import shutil
from pathlib import Path
import glob

def clean_deployment_folder():
    print("\n--- Cleaning deployment/ folder ---")
    deployment_dir = Path('deployment')
    
    # List all files in deployment directory
    files = [f for f in deployment_dir.iterdir() if f.is_file()]
    
    # Files to keep
    keep_files = ['create_package.py', 'ratio_competitive_intelligence_test.json']
    
    # Delete all files except those in keep_files
    for file in files:
        if file.name not in keep_files:
            try:
                os.remove(file)
                print(f"Deleted: {file}")
            except Exception as e:
                print(f"Error deleting {file}: {e}")

def clean_src_folder():
    print("\n--- Cleaning src/ folder ---")
    src_dir = Path('src')
    
    # Remove tables folder in src if it exists
    tables_dir = src_dir / 'tables'
    if tables_dir.exists():
        try:
            shutil.rmtree(tables_dir)
            print(f"Deleted directory: {tables_dir}")
        except Exception as e:
            print(f"Error deleting {tables_dir}: {e}")
    
    # Remove batch*.json files
    batch_files = list(src_dir.glob('batch*.json'))
    for file in batch_files:
        try:
            os.remove(file)
            print(f"Deleted: {file}")
        except Exception as e:
            print(f"Error deleting {file}: {e}")

def clean_tables_folder():
    print("\n--- Cleaning tables/RatioCompetitiveIntelligence/ folder ---")
    ratio_dir = Path('tables/RatioCompetitiveIntelligence')
    
    if not ratio_dir.exists():
        print(f"Directory does not exist: {ratio_dir}")
        return
    
    # List all files in the directory
    files = [f for f in ratio_dir.iterdir() if f.is_file()]
    
    # Keep only files that have 'multiplex' or 'config' in the name,
    # or are the original RatioCompetitiveIntelligence.xlsx files
    for file in files:
        # Check if the file should be kept
        if ('multiplex' in file.name.lower() or 
            'config' in file.name.lower() or 
            file.name.startswith('RatioCompetitiveIntelligence') and file.suffix.lower() == '.xlsx'):
            print(f"Keeping: {file}")
        else:
            try:
                os.remove(file)
                print(f"Deleted: {file}")
            except Exception as e:
                print(f"Error deleting {file}: {e}")

def main():
    print("Starting final cleanup process...")
    
    # Run all cleanup functions
    clean_deployment_folder()
    clean_src_folder()
    clean_tables_folder()
    
    print("\nFinal cleanup complete!")

if __name__ == "__main__":
    main() 