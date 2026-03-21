import docx
import logging

logger = logging.getLogger(__name__)

def save_to_word(text, stock_name, file_path):
    """Αποθηκεύει το εξαγόμενο κείμενο σε αρχείο .docx."""
    try:
        doc = docx.Document()
        doc.add_heading(f'Ανάλυση Μετοχής: {stock_name}', 0)
        doc.add_paragraph(text)
        doc.save(file_path)
        return True, None
    except Exception as e:
        logger.error(f"Σφάλμα εξαγωγής σε Word για το {stock_name}: {e}", exc_info=True)
        return False, str(e)