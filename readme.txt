=========================================================
    AI Stock Analyzer Desktop - Αναλυτικές Οδηγίες
=========================================================

Καλώς ήρθατε στο AI Stock Analyzer! Αυτό το έγγραφο περιέχει
όλες τις πληροφορίες που χρειάζεστε για να εγκαταστήσετε,
να ρυθμίσετε και να χρησιμοποιήσετε την εφαρμογή.

--- [ 1. ΕΓΚΑΤΑΣΤΑΣΗ ] ------------------------------------
Η εφαρμογή είναι "portable", δηλαδή δεν απαιτεί εγκατάσταση.

1. Αποσυμπιέστε το αρχείο .zip που κατεβάσατε σε έναν φάκελο
   της επιλογής σας (π.χ. στην Επιφάνεια Εργασίας).
2. Ανοίξτε τον φάκελο και κάντε διπλό κλικ στο αρχείο:
   > AI Stock Analyzer Desktop.exe

ΣΗΜΕΙΩΣΗ ΑΣΦΑΛΕΙΑΣ: Την πρώτη φορά που θα τρέξετε την εφαρμογή,
τα Windows μπορεί να εμφανίσουν μια μπλε οθόνη "Windows protected
your PC". Αυτό είναι φυσιολογικό. Πατήστε "More info" (Περισσότερες
πληροφορίες) και μετά "Run anyway" (Εκτέλεση οπωσδήποτε).

--- [ 2. ΡΥΘΜΙΣΗ API KEYS & AI ] -------------------------
Για να λειτουργήσει η εφαρμογή, χρειάζεται "κλειδιά" (API Keys)
για να συνδέεται στις διάφορες υπηρεσίες.

ΒΗΜΑ 1: ΑΠΟΚΤΗΣΗ ΤΩΝ ΚΛΕΙΔΙΩΝ (ΔΩΡΕΑΝ)
  - Gemini API Key (Για την AI ανάλυση):
    1. Πηγαίνετε στο https://aistudio.google.com/app/apikey
    2. Συνδεθείτε με τον λογαριασμό σας Google.
    3. Πατήστε "Create API key" και αντιγράψτε το κλειδί.
  - Alpha Vantage Key (Για θεμελιώδη δεδομένα):
    1. Πηγαίνετε στο https://www.alphavantage.co/support/#api-key
    2. Συμπληρώστε τη φόρμα για να πάρετε το δωρεάν κλειδί σας.
  - Finnhub Key (Για ζωντανές τιμές):
    1. Πηγαίνετε στο https://finnhub.io/register
    2. Εγγραφείτε για ένα δωρεάν κλειδί.
  - NewsAPI Key (Για προηγμένες ειδήσεις):
    1. Πηγαίνετε στο https://newsapi.org/register
    2. Εγγραφείτε για ένα δωρεάν κλειδί για developers.

ΒΗΜΑ 2: ΕΙΣΑΓΩΓΗ ΣΤΗΝ ΕΦΑΡΜΟΓΗ
  1. Στο αριστερό μενού της εφαρμογής, βρείτε την ενότητα "API Keys".
  2. Επικολλήστε κάθε κλειδί στο αντίστοιχο πεδίο.
  3. Πατήστε το κουμπί "Αποθήκευση Κλειδιών".

ΒΗΜΑ 3: ΕΠΙΛΟΓΗ ΜΟΝΤΕΛΟΥ AI
  - Gemini (Cloud): Αν έχετε βάλει το Gemini API Key, επιλέξτε
    "Gemini (Cloud)" από το μενού "Πάροχος AI". Τα διαθέσιμα
    μοντέλα θα φορτώσουν αυτόματα.
  - Ollama (Τοπικά): Αν θέλετε να χρησιμοποιήσετε δικά σας
    μοντέλα για 100% ιδιωτικότητα:
    1. Βεβαιωθείτε ότι έχετε εγκαταστήσει και τρέχετε το Ollama
       στον υπολογιστή σας (https://ollama.com/).
    2. Κατεβάστε ένα μοντέλο (π.χ. ανοίξτε μια γραμμή εντολών
       και γράψτε: `ollama run llama3`).
    3. Στην εφαρμογή, επιλέξτε "Ollama (Τοπικά)" από το μενού
       "Πάροχος AI". Τα τοπικά σας μοντέλα θα εμφανιστούν.

--- [ 3. ΒΑΣΙΚΗ ΡΟΗ ΧΡΗΣΗΣ ] -----------------------------
Η διαδικασία για μια ανάλυση είναι απλή:

1. ΔΙΑΧΕΙΡΙΣΗ WATCHLIST (ΑΡΙΣΤΕΡΟ ΜΕΝΟΥ)
   - Προσθέστε τις μετοχές, ETFs ή δείκτες που σας ενδιαφέρουν.
   - Το "Όνομα" είναι για εσάς. Το "Yahoo Symbol" είναι το πιο
     σημαντικό (π.χ. "AAPL" για την Apple, "^GSPC" για τον S&P 500).
   - Μπορείτε να προσθέσετε και προσωπικές σημειώσεις για κάθε μετοχή.
   - Χρησιμοποιήστε τα βελάκια (▲/▼) για να αλλάξετε τη σειρά.

2. ΕΠΙΛΟΓΗ ΜΕΤΟΧΗΣ & ΠΗΓΩΝ (ΚΕΝΤΡΙΚΟ ΠΑΡΑΘΥΡΟ)
   - Από το μενού "Επιλογή Μετοχής", διαλέξτε αυτή που θέλετε.
   - Τα δεδομένα (γράφημα, τιμές, ειδήσεις) θα φορτώσουν αυτόματα.
   - Τώρα, επιλέξτε ΤΙ θέλετε να "διαβάσει" το AI. Ενεργοποιήστε
     τα κουτάκια (checkboxes) για τις πηγές που επιθυμείτε:
     - Δεδομένα API: Alpha Vantage, Finnhub, NewsAPI.
     - Ειδήσεις: Από το DuckDuckGo (αυτόματο).
     - URLs & RSS: Επιλέξτε τα δικά σας URLs ή άρθρα από RSS.
     - Σελίδες Μετοχής: Επιλέξτε τις σελίδες Yahoo/FT/Investing.
     - Εταιρικό Site: Για να διαβάσει την επίσημη ιστοσελίδα.
     - Τοπικά Αρχεία: Πατήστε "Προσθήκη Αρχείου" για PDF/TXT.
     - Επικόλληση Άρθρων: Επικολλήστε κείμενο στα αντίστοιχα πεδία.

3. ΠΡΟΗΓΜΕΝΑ ΦΙΛΤΡΑ
   - Στα φίλτρα για RSS και NewsAPI, μπορείτε να κάνετε σύνθετες
     αναζητήσεις. Χρησιμοποιήστε:
     - Κόμμα (,) για συνθήκη 'Η' (OR). Π.χ. `Apple,Microsoft`
     - Συν (+) για συνθήκη 'ΚΑΙ' (AND). Π.χ. `Apple+earnings`

4. ΕΚΤΕΛΕΣΗ ΑΝΑΛΥΣΗΣ
   - Επιλέξτε τη μορφή ("Αναλυτικά" ή "Συνοπτικά").
   - Προσαρμόστε το "Temperature" (0.0 για αυστηρή ανάλυση,
     1.0 για πιο δημιουργική).
   - Πατήστε το μεγάλο κόκκινο κουμπί "Έναρξη Ανάλυσης".

5. ΑΠΟΤΕΛΕΣΜΑ & ΕΞΑΓΩΓΗ
   - Η ανάλυση θα εμφανιστεί στο μεγάλο πλαίσιο κειμένου.
   - Μπορείτε να την εκτυπώσετε ή να την εξάγετε σε αρχείο Word.
   - Η ανάλυση αποθηκεύεται αυτόματα στο "Ιστορικό Αναλύσεων".

=========================================================
      AI Stock Analyzer Desktop - Detailed Instructions
=========================================================

Welcome to the AI Stock Analyzer! This document contains all
the information you need to install, configure, and use the app.

--- [ 1. INSTALLATION ] -----------------------------------
The application is "portable," meaning it requires no installation.

1. Unzip the downloaded .zip file into a folder of your
   choice (e.g., on your Desktop).
2. Open the folder and double-click the file:
   > AI Stock Analyzer Desktop.exe

SECURITY NOTE: The first time you run the app, Windows might
display a blue "Windows protected your PC" screen. This is normal.
Click "More info" and then "Run anyway".

--- [ 2. CONFIGURING API KEYS & AI ] ----------------------
To function, the app needs "keys" (API Keys) to connect to
various services.

STEP 1: GETTING THE KEYS (FREE)
  - Gemini API Key (For AI analysis):
    1. Go to https://aistudio.google.com/app/apikey
    2. Sign in with your Google account.
    3. Click "Create API key" and copy the key.
  - Alpha Vantage Key (For fundamental data):
    1. Go to https://www.alphavantage.co/support/#api-key
    2. Fill out the form to get your free key.
  - Finnhub Key (For live prices):
    1. Go to https://finnhub.io/register
    2. Register for a free key.
  - NewsAPI Key (For advanced news):
    1. Go to https://newsapi.org/register
    2. Register for a free developer key.

STEP 2: ENTERING KEYS INTO THE APP
  1. In the app's left menu, find the "API Keys" section.
  2. Paste each key into its corresponding field.
  3. Click the "Save Keys" button.

STEP 3: CHOOSING AN AI MODEL
  - Gemini (Cloud): If you've entered your Gemini API Key, select
    "Gemini (Cloud)" from the "AI Provider" menu. The available
    models will load automatically.
  - Ollama (Local): If you want to use your own models for 100% privacy:
    1. Ensure you have Ollama installed and running on your
       computer (https://ollama.com/).
    2. Download a model (e.g., open a command prompt and type:
       `ollama run llama3`).
    3. In the app, select "Ollama (Local)" from the "AI Provider"
       menu. Your local models will appear.

--- [ 3. BASIC USAGE WORKFLOW ] ---------------------------
The process for an analysis is straightforward:

1. MANAGE WATCHLIST (LEFT MENU)
   - Add the stocks, ETFs, or indexes you're interested in.
   - The "Name" is for you. The "Yahoo Symbol" is the most
     important (e.g., "AAPL" for Apple, "^GSPC" for the S&P 500).
   - You can also add personal notes for each stock.
   - Use the arrows (▲/▼) to reorder your list.

2. SELECT STOCK & SOURCES (MAIN WINDOW)
   - From the "Select Stock" menu, choose the one you want.
   - The data (chart, prices, news) will load automatically.
   - Now, select WHAT you want the AI to "read". Enable the
     checkboxes for your desired sources:
     - API Data: Alpha Vantage, Finnhub, NewsAPI.
     - News: From DuckDuckGo (automatic).
     - URLs & RSS: Select your own URLs or articles from RSS feeds.
     - Stock Pages: Select the Yahoo/FT/Investing pages.
     - Corporate Site: To read the official website.
     - Local Files: Click "Add File" for PDF/TXT.
     - Paste Articles: Paste text into the corresponding fields.

3. ADVANCED FILTERS
   - In the filters for RSS and NewsAPI, you can perform complex
     searches. Use:
     - Comma (,) for an 'OR' condition. E.g., `Apple,Microsoft`
     - Plus (+) for an 'AND' condition. E.g., `Apple+earnings`

4. RUN ANALYSIS
   - Choose the format ("Detailed" or "Summary").
   - Adjust the "Temperature" (0.0 for strict analysis,
     1.0 for more creative).
   - Click the big red "Start Analysis" button.

5. RESULT & EXPORT
   - The analysis will appear in the large text box.
   - You can print it or export it to a Word file.
   - The analysis is automatically saved in the "Analysis History".