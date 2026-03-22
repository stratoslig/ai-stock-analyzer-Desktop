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
        '--onefile',                          # Συμπίεση σε ένα και μόνο αρχείο
        '--noconsole',                        # Απόκρυψη του μαύρου τερματικού (για Windows)
        '--icon=icon.ico',                    # Εικονίδιο εφαρμογής
        '--add-data=icon.ico;.',              # Ενσωμάτωση εικονιδίου για το Taskbar
        '--collect-all=customtkinter',        # Ενσωμάτωση όλων των θεμάτων του GUI
        '--clean'                             # Καθαρισμός παλιών προσωρινών αρχείων πριν το build
    ])

    print("\n✅ Η διαδικασία ολοκληρώθηκε επιτυχώς!")
    print("📂 Μπορείτε να βρείτε το έτοιμο πρόγραμμα μέσα στον φάκελο 'dist'.")
    
    print("\n📦 Δημιουργία του αρχείου .zip για διανομή...")
    exe_path = os.path.join('dist', 'AI Stock Analyzer Desktop.exe')
    readme_path = 'readme.txt'
    zip_name = os.path.join('dist', 'AI_Stock_Analyzer_Pro_v1.2.zip')
    
    with zipfile.ZipFile(zip_name, 'w', zipfile.ZIP_DEFLATED) as zipf:
        if os.path.exists(exe_path):
            zipf.write(exe_path, 'AI Stock Analyzer Desktop.exe')
        if os.path.exists(readme_path):
            zipf.write(readme_path, 'readme.txt')
    print(f"🎉 Το τελικό αρχείο '{zip_name}' είναι έτοιμο για ανέβασμα στο GitHub!")

if __name__ == "__main__":
    build_exe()