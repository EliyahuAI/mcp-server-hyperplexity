
import difflib
import os

def compare_files(file1_path, file2_path):
    with open(file1_path, 'r') as f1, open(file2_path, 'r') as f2:
        file1_lines = f1.readlines()
        file2_lines = f2.readlines()

    diff = difflib.unified_diff(
        file1_lines,
        file2_lines,
        fromfile=os.path.basename(file1_path),
        tofile=os.path.basename(file2_path),
    )

    for line in diff:
        print(line, end='')

if __name__ == "__main__":
    file1 = "/mnt/c/Users/ellio/OneDrive - Eliyahu.AI/Desktop/src/perplexityValidator/temp_unnecessary_files/test_prompts/prompt1.txt"
    file2 = "/mnt/c/Users/ellio/OneDrive - Eliyahu.AI/Desktop/src/perplexityValidator/temp_unnecessary_files/test_prompts/prompt2.txt"
    compare_files(file1, file2)
