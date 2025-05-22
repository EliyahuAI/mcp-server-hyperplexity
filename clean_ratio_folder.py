import os
from pathlib import Path

def clean_ratio_folder():
    print("Cleaning tables/RatioCompetitiveIntelligence/ folder - keeping only files with 'multiplex' or 'config' in the name, and the original RatioCompetitiveIntelligence.xlsx file")
    ratio_dir = Path('tables/RatioCompetitiveIntelligence')
    
    if not ratio_dir.exists():
        print(f"Directory does not exist: {ratio_dir}")
        return
    
    # List all files in the directory
    files = [f for f in ratio_dir.iterdir() if f.is_file()]
    
    for file in files:
        # Check if the file should be kept
        if ('multiplex' in file.name.lower() or 
            'config' in file.name.lower() or 
            file.name == 'RatioCompetitiveIntelligence.xlsx'):
            print(f"Keeping: {file}")
        else:
            try:
                os.remove(file)
                print(f"Deleted: {file}")
            except Exception as e:
                print(f"Error deleting {file}: {e}")

if __name__ == "__main__":
    clean_ratio_folder() 