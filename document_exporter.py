import docx
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_PARAGRAPH_ALIGNMENT
import re
import logging
import os
import sys
from io import BytesIO

try:
    from PIL import Image
except ImportError:
    Image = None

logger = logging.getLogger(__name__)

def get_resource_path(relative_path):
    """Επιστρέφει την απόλυτη διαδρομή για το αρχείο (συμβατό με PyInstaller)."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def save_to_word(text, stock_name, file_path):
    try:
        # Δημιουργία νέου εγγράφου Word
        doc = docx.Document()
        
        # --- Ρύθμιση περιθωρίων εγγράφου ---
        sections = doc.sections
        for section in sections:
            section.top_margin = Inches(1.0)
            section.bottom_margin = Inches(1.0)
            section.left_margin = Inches(1.0)
            section.right_margin = Inches(1.0)
        
        # --- Προσθήκη Λογότυπου ---
        icon_path = get_resource_path('icon.ico')
        if os.path.exists(icon_path):
            try:
                logo_para = doc.add_paragraph()
                logo_para.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
                
                if Image:
                    # Μετατροπή του .ico σε PNG στη μνήμη (το python-docx δεν υποστηρίζει άμεσα .ico)
                    with Image.open(icon_path) as img:
                        img_byte_arr = BytesIO()
                        img.save(img_byte_arr, format='PNG')
                        img_byte_arr.seek(0)
                        logo_para.add_run().add_picture(img_byte_arr, width=Inches(0.6))
                else:
                    logo_para.add_run().add_picture(icon_path, width=Inches(0.6))
            except Exception as e:
                logger.warning(f"Δεν ήταν δυνατή η προσθήκη του λογότυπου: {e}")
        
        # --- Προσθήκη Τίτλου ---
        title = doc.add_heading(f'Ανάλυση: {stock_name}', level=0)
        title.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        
        # --- Ρύθμιση Βασικού Στυλ (Normal) ---
        style = doc.styles['Normal']
        font = style.font
        font.name = 'Calibri'
        font.size = Pt(11)

        # Διαχωρισμός του κειμένου σε γραμμές για ανάλυση του Markdown
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            
            # Κενές γραμμές
            if not line:
                doc.add_paragraph()
                continue
            
            # Επικεφαλίδες (###, ##, #)
            if line.startswith('### '):
                doc.add_heading(line[4:], level=3)
                continue
            elif line.startswith('## '):
                doc.add_heading(line[3:], level=2)
                continue
            elif line.startswith('# '):
                doc.add_heading(line[2:], level=1)
                continue
            
            # Λίστες (Bullet points & Numbered)
            is_bullet = False
            if line.startswith('- ') or line.startswith('* '):
                line = line[2:]
                p = doc.add_paragraph(style='List Bullet')
                is_bullet = True
            elif re.match(r'^\d+\.\s', line):
                line = re.sub(r'^\d+\.\s', '', line)
                p = doc.add_paragraph(style='List Number')
                is_bullet = True
            else:
                p = doc.add_paragraph()

            # --- Επεξεργασία Bold (**κείμενο**) και Italic (*κείμενο*) ---
            # Χωρίζουμε το κείμενο με βάση τα **
            parts = re.split(r'(\*\*.*?\*\*)', line)
            
            for part in parts:
                if part.startswith('**') and part.endswith('**') and len(part) > 4:
                    # Είναι Bold
                    run = p.add_run(part[2:-2])
                    run.bold = True
                else:
                    # Ψάχνουμε για Italic μέσα στα απλά κομμάτια
                    sub_parts = re.split(r'(\*.*?\*)', part)
                    for sub_part in sub_parts:
                        if sub_part.startswith('*') and sub_part.endswith('*') and len(sub_part) > 2:
                            # Είναι Italic
                            run = p.add_run(sub_part[1:-1])
                            run.italic = True
                        else:
                            # Κανονικό κείμενο
                            p.add_run(sub_part)
                            
        # --- Προσθήκη Υποσέλιδου (Footer) ---
        footer = sections[0].footer
        footer_para = footer.paragraphs[0]
        footer_para.text = "Δημιουργήθηκε από το AI Stock Analyzer Desktop"
        footer_para.alignment = WD_PARAGRAPH_ALIGNMENT.CENTER
        footer_para.runs[0].font.size = Pt(9)
        footer_para.runs[0].font.color.rgb = RGBColor(128, 128, 128) # Γκρι χρώμα

        doc.save(file_path)
        return True, None
        
    except Exception as e:
        logger.error(f"Σφάλμα κατά την εξαγωγή Word: {e}", exc_info=True)
        return False, str(e)
