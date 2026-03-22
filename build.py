import PyInstaller.__main__
import os
import shutil
import zipfile

def build_exe():
    print("🚀 Ξεκινάει η δημιουργία του εκτελέσιμου αρχείου (.exe)...")
    print("⏳ Παρακαλώ περιμένετε, αυτό μπορεί να διαρκέσει 1-3 λεπτά.\n")

    # Παράμετροι για το PyInstaller
    PyInstaller.__main__.run([
        'desktop_app.py',                     # Το κεντρικό αρχείο της εφαρμογής
        '--name=AI Stock Analyzer Desktop',   # Το όνομα του τελικού αρχείου
        '--noconsole',                        # Απόκρυψη του μαύρου τερματικού (για Windows)
        '--icon=icon.ico',                    # Εικονίδιο εφαρμογής
        '--add-data=icon.ico;.',              # Ενσωμάτωση εικονιδίου για το Taskbar
        '--collect-all=customtkinter',        # Ενσωμάτωση όλων των θεμάτων του GUI
        '--clean'                             # Καθαρισμός παλιών προσωρινών αρχείων πριν το build
    ])

    print("\n✅ Η διαδικασία ολοκληρώθηκε επιτυχώς!")
    
    print("\n📦 Δημιουργία του αρχείου .zip για διανομή...")
    app_dir = os.path.join('dist', 'AI Stock Analyzer Desktop')
    readme_path = 'readme.txt'
    zip_name = os.path.join('dist', 'AI_Stock_Analyzer_Pro_v1.2.zip')
    
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Προσθήκη ολόκληρου του φακέλου της εφαρμογής στο zip
        if os.path.exists(app_dir):
            for root, dirs, files in os.walk(app_dir):
                for file in files:
                    file_path = os.path.join(root, file)
                    arcname = os.path.relpath(file_path, 'dist') # Διατήρηση δομής φακέλων
                    zipf.write(file_path, arcname)
        if os.path.exists(readme_path):
            zipf.write(readme_path, 'readme.txt')
    print(f"🎉 Το τελικό αρχείο '{zip_name}' είναι έτοιμο για ανέβασμα στο GitHub!")

if __name__ == "__main__":
    build_exe()