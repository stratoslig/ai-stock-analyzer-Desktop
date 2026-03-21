import json
import os
import logging

DATA_FILE = "user_data.json"
logger = logging.getLogger(__name__)

def load_data():
    """Φορτώνει τα δεδομένα χρήστη από το JSON αρχείο."""
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Σφάλμα κατά τη φόρτωση του {DATA_FILE}: {e}", exc_info=True)
    return {"api_key": "", "av_api_key": "", "finnhub_api_key": "", "marketaux_api_key": "", "watchlist": [], "urls": [], "history": [], "api_usage": {"date": "", "av": 0, "fh": 0, "ma": 0}}

def save_data(data):
    """Αποθηκεύει τα δεδομένα χρήστη στο JSON αρχείο."""
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f"Σφάλμα κατά την αποθήκευση στο {DATA_FILE}: {e}", exc_info=True)