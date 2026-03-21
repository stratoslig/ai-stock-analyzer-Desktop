import PyInstaller.__main__
import os
import shutil

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

if __name__ == "__main__":
    build_exe()