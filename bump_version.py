import re
import os
import subprocess
import sys

VERSION_FILE = os.path.join(os.path.dirname(__file__), 'version.py')

def bump():
    if not os.path.exists(VERSION_FILE):
        return

    with open(VERSION_FILE, 'r', encoding='utf-8') as f:
        content = f.read()

    # Ψάχνει το μοτίβο π.χ. "1.4.00"
    match = re.search(r'__version__\s*=\s*["\'](\d+\.\d+)\.(\d+)["\']', content)
    if match:
        base_version = match.group(1)
        patch_version = int(match.group(2))
        new_version = f"{base_version}.{patch_version + 1:02d}"
        
        # Αντικατάσταση στο κείμενο
        new_content = re.sub(r'__version__\s*=\s*["\'].*?["\']', f'__version__ = "{new_version}"', content)

        with open(VERSION_FILE, 'w', encoding='utf-8') as f:
            f.write(new_content)

        # Προσθήκη της αλλαγής στο τρέχον Git Commit
        subprocess.run(['git', 'add', VERSION_FILE])

def tag():
    if not os.path.exists(VERSION_FILE):
        return
        
    with open(VERSION_FILE, 'r', encoding='utf-8') as f:
        content = f.read()
        
    match = re.search(r'__version__\s*=\s*["\'](.*?)["\']', content)
    if match:
        version = match.group(1)
        tag_name = f"v{version}"
        # Δημιουργία του Git Tag (Annotated)
        subprocess.run(['git', 'tag', '-a', tag_name, '-m', f'Έκδοση {tag_name}'])

if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'tag':
        tag()
    else:
        bump()