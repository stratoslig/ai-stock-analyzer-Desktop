import PyInstaller.__main__
import os
import zipfile
import tarfile
import sys
import subprocess

# Κοινές "κρυφές" εξαρτήσεις για το PyInstaller, απαραίτητες λόγω του lazy-loading
hidden_imports = [
    '--hidden-import=yfinance',
    '--hidden-import=pandas',
    '--hidden-import=PyPDF2',
    '--hidden-import=matplotlib.backends.backend_tkagg',
    '--hidden-import=matplotlib.widgets',
    '--hidden-import=sklearn',
    '--hidden-import=sklearn.utils._cython_blas',
    '--hidden-import=sklearn.neighbors._typedefs',
    '--hidden-import=sklearn.neighbors._quad_tree',
    '--hidden-import=openpyxl',
    '--hidden-import=dateutil.parser',
    '--hidden-import=pkg_resources.py2_warn',
    '--hidden-import=lxml',
    '--hidden-import=google.generativeai',
    '--hidden-import=google.ai.generativelanguage',
    '--hidden-import=docx',
]

# Λίστα για τη συλλογή ολόκληρων των δεδομένων των βιβλιοθηκών που το απαιτούν
collect_data = [
    '--collect-data=pandas_ta',
    '--collect-data=trafilatura',
    '--collect-data=cloudscraper',
    '--collect-data=ddgs',
    '--collect-data=feedparser',
]

def build_windows():
    print("🚀 Building for Windows (.exe)...")
    print("⏳ Please wait, this may take 1-3 minutes.\n")
    
    pyinstaller_args = [
        'desktop_app.py',
        '--name=AI Stock Analyzer Desktop',
        '--noconsole',
        '--icon=icon.ico',
        '--add-data=icon.ico;.',
        '--collect-all=customtkinter',
        '--clean'
    ]
    pyinstaller_args.extend(hidden_imports)
    pyinstaller_args.extend(collect_data)

    PyInstaller.__main__.run(pyinstaller_args)

    print("\n✅ PyInstaller build completed successfully!")
    
    print("\n📦 Creating .zip file for distribution...")
    app_dir = os.path.join('dist', 'AI Stock Analyzer Desktop')
    readme_path = 'readme.txt'
    
    release_tag = os.environ.get('RELEASE_TAG', 'v1.3')
    zip_name = os.path.join('dist', f'AI_Stock_Analyzer_Pro_{release_tag}.zip')
    
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        if os.path.exists(app_dir):
            for root, dirs, files in os.walk(app_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, 'dist')
                    zipf.write(file_path, arcname)
        if os.path.exists(readme_path):
            zipf.write(readme_path, 'readme.txt')
    print(f"🎉 Final file '{zip_name}' is ready for GitHub upload!")

def build_macos():
    print("🚀 Building for macOS (.dmg)...")
    print("⏳ Please wait, this may take 1-3 minutes.\n")
    
    icon_path = 'icon.icns'
    pyinstaller_args = [
        'desktop_app.py',
        '--name=AI Stock Analyzer Desktop',
        '--windowed',
        '--collect-all=customtkinter',
        '--clean'
    ]
    if os.path.exists(icon_path):
        print(f"🍏 Found '{icon_path}', adding it to the build.")
        pyinstaller_args.extend(['--icon=' + icon_path, '--add-data=' + icon_path + ':.'])
    else:
        print(f"⚠️ '{icon_path}' not found. Building without a custom icon.")

    pyinstaller_args.extend(hidden_imports)
    pyinstaller_args.extend(collect_data)
    PyInstaller.__main__.run(pyinstaller_args)
    
    print("\n✅ PyInstaller build completed successfully!")
    print("\n📦 Creating .dmg file...")
    
    app_path = os.path.join('dist', 'AI Stock Analyzer Desktop.app')
    release_tag = os.environ.get('RELEASE_TAG', 'v1.3')
    dmg_name = f'AI_Stock_Analyzer_Pro_{release_tag}.dmg'
    dmg_path = os.path.join('dist', dmg_name)
    
    if os.path.exists(app_path):
        try:
            subprocess.run(['create-dmg', '--volname', f'AI Stock Analyzer {release_tag}', dmg_path, app_path], check=True)
            print(f"🎉 Final file '{dmg_path}' is ready for GitHub upload!")
        except FileNotFoundError:
            print("\n❌ 'create-dmg' command not found. Please install it via Homebrew: 'brew install create-dmg'")
            sys.exit(1)
        except subprocess.CalledProcessError as e:
            print(f"\n❌ An error occurred while creating the .dmg file: {e}")
            sys.exit(1)
    else:
        print(f"\n❌ App bundle not found at '{app_path}'. Build failed.")
        sys.exit(1)

def build_linux():
    print("🚀 Building for Linux...")
    print("⏳ Please wait, this may take 1-3 minutes.\n")
    
    pyinstaller_args = [
        'desktop_app.py',
        '--name=AI Stock Analyzer Desktop',
        '--windowed',
        '--collect-all=customtkinter',
        '--clean'
    ]
    pyinstaller_args.extend(hidden_imports)
    pyinstaller_args.extend(collect_data)
    
    PyInstaller.__main__.run(pyinstaller_args)
    
    print("\n✅ PyInstaller build completed successfully!")
    print("\n📦 Creating .tar.gz file for distribution...")
    
    app_dir = os.path.join('dist', 'AI Stock Analyzer Desktop')
    readme_path = 'readme.txt'
    
    release_tag = os.environ.get('RELEASE_TAG', 'v1.3')
    tar_name = os.path.join('dist', f'AI_Stock_Analyzer_Pro_{release_tag}_Linux.tar.gz')
    
    with tarfile.open(tar_name, "w:gz") as tar:
        if os.path.exists(app_dir):
            tar.add(app_dir, arcname='AI Stock Analyzer Desktop')
        if os.path.exists(readme_path):
            tar.add(readme_path, arcname='readme.txt')
            
    print(f"🎉 Final file '{tar_name}' is ready for GitHub upload!")

if __name__ == "__main__":
    if sys.platform == "win32":
        build_windows()
    elif sys.platform == "darwin":
        build_macos()
    elif sys.platform.startswith("linux"):
        build_linux()
    else:
        print(f"Unsupported OS for build: {sys.platform}")