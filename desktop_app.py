import customtkinter as ctk
import threading
from tkinter import filedialog
import webbrowser
import logging
import tkinter as tk
from tkinter import messagebox
import requests
import datetime
import os
import sys
import tempfile
import subprocess
import concurrent.futures
from PIL import Image

from data_manager import load_data, save_data
import stock_fetcher
import ai_service
import document_exporter
from translations import TRANSLATIONS

logging.basicConfig(
    filename="app_errors.log",
    level=logging.ERROR,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

ctk.set_appearance_mode("Dark")
ctk.set_default_color_theme("blue")

# --- Monkey-patch για αλλαγή της προεπιλεγμένης γραμματοσειράς σε 'Segoe UI' (ιδανική για Ελληνικά) ---
_original_ctk_font = ctk.CTkFont
def _patched_ctk_font(*args, **kwargs):
    if "family" not in kwargs:
        kwargs["family"] = "Segoe UI"
    return _original_ctk_font(*args, **kwargs)
ctk.CTkFont = _patched_ctk_font
# ---------------------------------------------------------------------------------------------------

def resource_path(relative_path):
    """Επιστρέφει την απόλυτη διαδρομή για το αρχείο, συμβατό με το PyInstaller."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class ToolTip:
    """Κλάση για την εμφάνιση αναδυόμενων μηνυμάτων (tooltips) όταν το ποντίκι αιωρείται πάνω από ένα widget."""
    def __init__(self, widget, text_or_func):
        self.widget = widget
        self.text_or_func = text_or_func
        self.tw = None
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)

    def enter(self, event=None):
        text = self.text_or_func() if callable(self.text_or_func) else self.text_or_func
        if not text: return
        x = self.widget.winfo_rootx() + 20
        y = self.widget.winfo_rooty() + 20
        self.tw = tk.Toplevel(self.widget)
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry(f"+{x}+{y}")
        label = tk.Label(self.tw, text=text, justify='left',
                         background="#1c1c1c", foreground="white", relief='solid', borderwidth=1,
                         font=("Segoe UI", 10, "normal"), padx=4, pady=2, wraplength=400)
        label.pack()

    def leave(self, event=None):
        if self.tw:
            self.tw.destroy()
            self.tw = None

class App(ctk.CTk):
    """Η κύρια κλάση της εφαρμογής που διαχειρίζεται το γραφικό περιβάλλον (GUI) και τη ροή εκτέλεσης."""
    def __init__(self):
        super().__init__()
        self.user_data = load_data()
        if "language" not in self.user_data:
            self.user_data["language"] = "el"
        self.current_av_context = ""
        self.current_fh_context = ""
        self.current_analysis_stock = ""
        self.current_fig = None
        self.page_checkboxes = []
        self.ai_font_size = 14

        # Καθαρισμός τυχόν κενών εγγραφών από τα δεδομένα χρήστη
        self.user_data["watchlist"] = [
            w for w in self.user_data.get("watchlist", []) 
            if isinstance(w, dict) and w.get("Ονομασία") and str(w.get("Ονομασία")).strip()
        ]
        valid_urls = []
        for u in self.user_data.get("urls", []):
            if isinstance(u, dict) and u.get("url") and str(u.get("url")).strip():
                valid_urls.append(u)
            elif isinstance(u, str) and u.strip():
                valid_urls.append({"title": "", "url": u.strip()})
        self.user_data["urls"] = valid_urls

        self._sync_api_usage()

        self.title("AI Stock Analyzer Desktop")
        self.geometry("1200x900")
        self.minsize(1000, 700)
        
        try:
            self.iconbitmap(resource_path("icon.ico"))
            # Ενημέρωση των Windows για εμφάνιση του σωστού εικονιδίου στη γραμμή εργασιών (Taskbar)
            import ctypes
            myappid = 'aistockanalyzer.pro.desktop.1.4'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass
            
        try:
            img = Image.open(resource_path("icon.ico"))
            self.logo_image = ctk.CTkImage(light_image=img, dark_image=img, size=(30, 30))
            self.logo_image_about = ctk.CTkImage(light_image=img, dark_image=img, size=(24, 24))
        except Exception as e:
            logger.warning(f"Δεν ήταν δυνατή η φόρτωση του εικονιδίου: {e}")
            self.logo_image = None
            self.logo_image_about = None

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)

        # --- ΚΕΝΤΡΙΚΗ ΜΠΑΡΑ (HEADER) ---
        header_frame = ctk.CTkFrame(self, fg_color="transparent")
        header_frame.grid(row=0, column=0, sticky="ew", padx=10, pady=(10, 5))
        
        self.active_border_color = "#6aa3cc"
        
        self.toggle_settings_btn = ctk.CTkButton(header_frame, text=self.tr("settings_btn"), width=110, height=32, corner_radius=15, font=ctk.CTkFont(weight="bold"), border_width=1, border_color=self.active_border_color, command=self.toggle_settings)
        self.toggle_settings_btn.pack(side="left", padx=5)
        
        self.toggle_data_btn = ctk.CTkButton(header_frame, text=self.tr("data_btn"), width=110, height=32, corner_radius=15, font=ctk.CTkFont(weight="bold"), border_width=1, border_color=self.active_border_color, command=self.toggle_data)
        self.toggle_data_btn.pack(side="left", padx=5)
        
        self.toggle_overview_btn = ctk.CTkButton(header_frame, text=self.tr("overview_title"), width=130, height=32, corner_radius=15, font=ctk.CTkFont(weight="bold"), border_width=1, border_color=self.active_border_color, command=self.toggle_overview)
        self.toggle_overview_btn.pack(side="left", padx=5)

        self.active_btn_color = self.toggle_settings_btn.cget("fg_color")
        self.inactive_btn_color = "#444444"
        self.active_text_color = self.toggle_settings_btn.cget("text_color")
        self.inactive_text_color = "gray"

        title_text = "  AI Stock Analyzer Desktop" if self.logo_image else "📈 AI Stock Analyzer Desktop"
        title_lbl = ctk.CTkLabel(header_frame, text=title_text, image=self.logo_image, compound="left", font=ctk.CTkFont(size=24, weight="bold"))
        title_lbl.pack(side="left", expand=True)

        self.about_btn = ctk.CTkButton(header_frame, text=self.tr("about_btn"), width=80, height=32, corner_radius=15, font=ctk.CTkFont(weight="bold"), fg_color="transparent", border_width=1, text_color="gray", hover_color="#333", command=self.show_about_window)
        self.about_btn.pack(side="right", padx=5)

        # --- ΚΕΝΤΡΙΚΟ ΠΕΡΙΕΧΟΜΕΝΟ ---
        self.content_frame = ctk.CTkFrame(self, fg_color="transparent")
        self.content_frame.grid(row=1, column=0, sticky="nsew")
        self.content_frame.grid_rowconfigure(0, weight=1)
        self.content_frame.grid_columnconfigure(0, minsize=390, weight=0)
        self.content_frame.grid_columnconfigure(1, minsize=430, weight=1)
        self.content_frame.grid_columnconfigure(2, weight=3)

        # --- ΣΤΗΛΗ 1: ΡΥΘΜΙΣΕΙΣ ---
        self.sidebar_frame = ctk.CTkScrollableFrame(self.content_frame, width=380, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(4, weight=1)
        self.sidebar_frame.grid_columnconfigure(0, weight=1)

        # 1. ΠΛΑΙΣΙΟ ΓΛΩΣΣΑΣ
        lang_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="#141414", corner_radius=8, border_width=1, border_color="#333333")
        lang_frame.grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")
        lang_frame.grid_columnconfigure(0, weight=1)
        
        self.lang_header_btn = self._create_collapsible_header(lang_frame, self.tr("language"))
        self.lang_var = ctk.StringVar(value="Ελληνικά" if self.user_data.get("language", "el") == "el" else "English")
        self.lang_menu = ctk.CTkOptionMenu(lang_frame, variable=self.lang_var, values=["Ελληνικά", "English"], command=self.change_language)
        self.lang_menu.grid(row=1, column=0, padx=10, pady=(5, 10), sticky="ew")

        # 2. ΠΛΑΙΣΙΟ AI ΠΑΡΟΧΟΥ / ΜΟΝΤΕΛΟΥ
        ai_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="#141414", corner_radius=8, border_width=1, border_color="#333333")
        ai_frame.grid(row=1, column=0, padx=10, pady=5, sticky="ew")
        ai_frame.grid_columnconfigure(0, weight=1)

        self._create_collapsible_header(ai_frame, self.tr("ai_provider"))
        self.ai_provider_menu = ctk.CTkOptionMenu(ai_frame, values=["Gemini (Cloud)", "Ollama (Cloud)", "Ollama (Τοπικά)"], command=self.update_models)
        self.ai_provider_menu.grid(row=1, column=0, padx=10, pady=5, sticky="ew")

        temp_frame = ctk.CTkFrame(ai_frame, fg_color="transparent")
        temp_frame.grid(row=2, column=0, padx=10, pady=(5, 0), sticky="ew")
        ctk.CTkLabel(temp_frame, text=self.tr("temperature"), font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        self.temp_val_label = ctk.CTkLabel(temp_frame, text="0.7", font=ctk.CTkFont(size=12))
        self.temp_val_label.pack(side="right")
        
        self.temperature_slider = ctk.CTkSlider(ai_frame, from_=0.0, to=1.0, number_of_steps=10, command=self.update_temp_label)
        self.temperature_slider.set(0.7)
        self.temperature_slider.grid(row=3, column=0, padx=10, pady=5, sticky="ew")
        ToolTip(self.temperature_slider, self.tr("tt_temp"))

        ctk.CTkLabel(ai_frame, text=self.tr("installed_models"), font=ctk.CTkFont(size=12, weight="bold")).grid(row=4, column=0, padx=10, pady=(5, 0), sticky="w")
        self.ai_model_var = ctk.StringVar(value="Φόρτωση...")
        self.ai_model_var.trace_add("write", self.update_ai_info_label)
        self.ai_model_menu = ctk.CTkOptionMenu(ai_frame, variable=self.ai_model_var, values=["Φόρτωση..."])
        self.ai_model_menu.grid(row=5, column=0, padx=10, pady=(5, 10), sticky="ew")

        # 3. ΠΛΑΙΣΙΟ API KEYS
        api_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="#141414", corner_radius=8, border_width=1, border_color="#333333")
        api_frame.grid(row=2, column=0, padx=10, pady=5, sticky="ew")
        api_frame.grid_columnconfigure(0, weight=1)

        self.api_header_btn = self._create_collapsible_header(api_frame, self.tr("api_keys"))
        
        f_api1 = ctk.CTkFrame(api_frame, fg_color="transparent")
        f_api1.grid(row=1, column=0, padx=10, pady=2, sticky="ew")
        ctk.CTkLabel(f_api1, text="Gemini API Key:", font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w")
        row_api1 = ctk.CTkFrame(f_api1, fg_color="transparent")
        row_api1.pack(fill="x")
        self.api_key_entry = ctk.CTkEntry(row_api1, placeholder_text="Επικόλληση κλειδιού...", show="*")
        self.api_key_entry.pack(side="left", fill="x", expand=True)
        self.api_key_entry.insert(0, self.user_data.get("api_key", ""))
        ctk.CTkButton(row_api1, text="📋", width=25, fg_color="#444", hover_color="#555", command=lambda: self.paste_to_entry(self.api_key_entry)).pack(side="right", padx=(5, 0))
        ToolTip(self.api_key_entry, self.tr("tt_api_gemini"))

        f_api2 = ctk.CTkFrame(api_frame, fg_color="transparent")
        f_api2.grid(row=2, column=0, padx=10, pady=2, sticky="ew")
        ctk.CTkLabel(f_api2, text="Alpha Vantage Key:", font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w")
        row_api2 = ctk.CTkFrame(f_api2, fg_color="transparent")
        row_api2.pack(fill="x")
        self.av_key_entry = ctk.CTkEntry(row_api2, placeholder_text="Επικόλληση κλειδιού...", show="*")
        self.av_key_entry.pack(side="left", fill="x", expand=True)
        self.av_key_entry.insert(0, self.user_data.get("av_api_key", ""))
        ctk.CTkButton(row_api2, text="📋", width=25, fg_color="#444", hover_color="#555", command=lambda: self.paste_to_entry(self.av_key_entry)).pack(side="right", padx=(5, 0))
        ToolTip(self.av_key_entry, self.tr("tt_api_av"))

        f_api3 = ctk.CTkFrame(api_frame, fg_color="transparent")
        f_api3.grid(row=3, column=0, padx=10, pady=2, sticky="ew")
        ctk.CTkLabel(f_api3, text="Finnhub Key:", font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w")
        row_api3 = ctk.CTkFrame(f_api3, fg_color="transparent")
        row_api3.pack(fill="x")
        self.finnhub_key_entry = ctk.CTkEntry(row_api3, placeholder_text="Επικόλληση κλειδιού...", show="*")
        self.finnhub_key_entry.pack(side="left", fill="x", expand=True)
        self.finnhub_key_entry.insert(0, self.user_data.get("finnhub_api_key", ""))
        ctk.CTkButton(row_api3, text="📋", width=25, fg_color="#444", hover_color="#555", command=lambda: self.paste_to_entry(self.finnhub_key_entry)).pack(side="right", padx=(5, 0))
        ToolTip(self.finnhub_key_entry, self.tr("tt_api_fh"))

        f_api4 = ctk.CTkFrame(api_frame, fg_color="transparent")
        f_api4.grid(row=4, column=0, padx=10, pady=2, sticky="ew")
        ctk.CTkLabel(f_api4, text="NewsAPI Key:", font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w")
        row_api4 = ctk.CTkFrame(f_api4, fg_color="transparent")
        row_api4.pack(fill="x")
        self.newsapi_key_entry = ctk.CTkEntry(row_api4, placeholder_text="Επικόλληση κλειδιού...", show="*")
        self.newsapi_key_entry.pack(side="left", fill="x", expand=True)
        self.newsapi_key_entry.insert(0, self.user_data.get("newsapi_key", ""))
        ctk.CTkButton(row_api4, text="📋", width=25, fg_color="#444", hover_color="#555", command=lambda: self.paste_to_entry(self.newsapi_key_entry)).pack(side="right", padx=(5, 0))
        ToolTip(self.newsapi_key_entry, self.tr("tt_api_news"))

        f_api5 = ctk.CTkFrame(api_frame, fg_color="transparent")
        f_api5.grid(row=5, column=0, padx=10, pady=2, sticky="ew")
        ctk.CTkLabel(f_api5, text="Ollama Cloud Key/URL:", font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w")
        row_api5 = ctk.CTkFrame(f_api5, fg_color="transparent")
        row_api5.pack(fill="x")
        self.ollama_cloud_key_entry = ctk.CTkEntry(row_api5, placeholder_text="Επικόλληση URL/Κλειδιού...", show="*")
        self.ollama_cloud_key_entry.pack(side="left", fill="x", expand=True)
        self.ollama_cloud_key_entry.insert(0, self.user_data.get("ollama_cloud_key", ""))
        ctk.CTkButton(row_api5, text="📋", width=25, fg_color="#444", hover_color="#555", command=lambda: self.paste_to_entry(self.ollama_cloud_key_entry)).pack(side="right", padx=(5, 0))
        ToolTip(self.ollama_cloud_key_entry, self.tr("tt_api_ollama_cloud"))

        self.save_settings_btn = ctk.CTkButton(api_frame, text=self.tr("save_keys"), command=self.save_keys, fg_color="#2b2b2b", hover_color="#3b3b3b")
        self.save_settings_btn.grid(row=6, column=0, padx=10, pady=(5, 10), sticky="ew")
        self.add_hover_border(self.save_settings_btn, "#6aa3cc")

        # 4. ΠΛΑΙΣΙΟ ΔΙΑΧΕΙΡΙΣΗΣ ΜΕΤΟΧΗΣ
        self.stock_mng_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="#141414", corner_radius=8, border_width=1, border_color="#333333")
        self.stock_mng_frame.grid(row=3, column=0, padx=10, pady=5, sticky="ew")
        self.stock_mng_frame.grid_columnconfigure(0, weight=1)

        self.stock_mng_header_btn = self._create_collapsible_header(self.stock_mng_frame, self.tr("stock_management"))

        f_stk1 = ctk.CTkFrame(self.stock_mng_frame, fg_color="transparent")
        f_stk1.grid(row=1, column=0, padx=10, pady=2, sticky="ew")
        self.stock_name_entry = ctk.CTkEntry(f_stk1, placeholder_text=self.tr("stock_name"))
        self.stock_name_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(f_stk1, text="📋", width=25, fg_color="#444", hover_color="#555", command=lambda: self.paste_to_entry(self.stock_name_entry)).pack(side="right", padx=(5, 0))
        
        f_stk2 = ctk.CTkFrame(self.stock_mng_frame, fg_color="transparent")
        f_stk2.grid(row=2, column=0, padx=10, pady=2, sticky="ew")
        self.stock_yahoo_entry = ctk.CTkEntry(f_stk2, placeholder_text="Yahoo Symbol")
        self.stock_yahoo_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(f_stk2, text="📋", width=25, fg_color="#444", hover_color="#555", command=lambda: self.paste_to_entry(self.stock_yahoo_entry)).pack(side="right", padx=(5, 0))
        
        f_stk3 = ctk.CTkFrame(self.stock_mng_frame, fg_color="transparent")
        f_stk3.grid(row=3, column=0, padx=10, pady=2, sticky="ew")
        self.stock_ft_entry = ctk.CTkEntry(f_stk3, placeholder_text="Financial Times Symbol")
        self.stock_ft_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(f_stk3, text="📋", width=25, fg_color="#444", hover_color="#555", command=lambda: self.paste_to_entry(self.stock_ft_entry)).pack(side="right", padx=(5, 0))
        
        f_stk4 = ctk.CTkFrame(self.stock_mng_frame, fg_color="transparent")
        f_stk4.grid(row=4, column=0, padx=10, pady=2, sticky="ew")
        self.stock_inv_entry = ctk.CTkEntry(f_stk4, placeholder_text="Investing.com Symbol")
        self.stock_inv_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(f_stk4, text="📋", width=25, fg_color="#444", hover_color="#555", command=lambda: self.paste_to_entry(self.stock_inv_entry)).pack(side="right", padx=(5, 0))

        f_stk5 = ctk.CTkFrame(self.stock_mng_frame, fg_color="transparent")
        f_stk5.grid(row=5, column=0, padx=10, pady=2, sticky="ew")
        ctk.CTkLabel(f_stk5, text=self.tr("stock_notes"), font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w")
        self.stock_notes_entry = ctk.CTkTextbox(f_stk5, height=60)
        self.stock_notes_entry.pack(fill="x", expand=True)

        self.save_stock_btn = ctk.CTkButton(self.stock_mng_frame, text=self.tr("save_stock"), command=self.save_stock, fg_color="#2b2b2b", hover_color="#3b3b3b")
        self.save_stock_btn.grid(row=6, column=0, padx=10, pady=(5, 10), sticky="ew")
        self.add_hover_border(self.save_stock_btn, "#6aa3cc")

        # 5. ΠΛΑΙΣΙΟ WATCHLIST
        wl_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="#141414", corner_radius=8, border_width=1, border_color="#333333")
        wl_frame.grid(row=4, column=0, padx=10, pady=5, sticky="nsew")
        wl_frame.grid_columnconfigure(0, weight=1)
        wl_frame.grid_rowconfigure(2, weight=1)

        self._create_collapsible_header(wl_frame, self.tr("watchlist"))

        self.wl_search_var = ctk.StringVar()
        self.wl_search_var.trace_add("write", lambda *args: self.update_watchlist_table())
        self.wl_search_entry = ctk.CTkEntry(wl_frame, textvariable=self.wl_search_var, placeholder_text=self.tr("wl_search_ph"), height=28)
        self.wl_search_entry.grid(row=1, column=0, padx=10, pady=(5, 5), sticky="ew")

        self.watchlist_frame = ctk.CTkScrollableFrame(wl_frame, height=280)
        self.watchlist_frame.grid(row=2, column=0, padx=10, pady=(0, 10), sticky="nsew")

        # 5.5 ΠΛΑΙΣΙΟ METATAGS
        self.meta_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="#141414", corner_radius=8, border_width=1, border_color="#333333")
        self.meta_frame.grid(row=5, column=0, padx=10, pady=5, sticky="nsew")
        self.meta_frame.grid_columnconfigure(0, weight=1)
        self.meta_header_btn = self._create_collapsible_header(self.meta_frame, self.tr("metatags_title"))

        f_meta1 = ctk.CTkFrame(self.meta_frame, fg_color="transparent")
        f_meta1.grid(row=1, column=0, padx=10, pady=2, sticky="ew")
        self.meta_name_entry = ctk.CTkEntry(f_meta1, placeholder_text=self.tr("meta_name"))
        self.meta_name_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(f_meta1, text="📋", width=25, fg_color="#444", hover_color="#555", command=lambda: self.paste_to_entry(self.meta_name_entry)).pack(side="right", padx=(5, 0))
        
        f_meta1_5 = ctk.CTkFrame(self.meta_frame, fg_color="transparent")
        f_meta1_5.grid(row=2, column=0, padx=10, pady=2, sticky="ew")
        
        lbl_btn_info = ctk.CTkFrame(f_meta1_5, fg_color="transparent")
        lbl_btn_info.pack(fill="x")
        ctk.CTkLabel(lbl_btn_info, text=self.tr("meta_info"), font=ctk.CTkFont(size=11), text_color="gray").pack(side="left")
        ctk.CTkButton(lbl_btn_info, text="📋 Επικόλληση", width=60, height=20, fg_color="#444", hover_color="#555", command=lambda: self.paste_to_textbox(self.meta_info_entry)).pack(side="right")
        
        self.meta_info_entry = ctk.CTkTextbox(f_meta1_5, height=40)
        self.meta_info_entry.pack(fill="x", expand=True, pady=(2, 0))
        
        f_meta2 = ctk.CTkFrame(self.meta_frame, fg_color="transparent")
        f_meta2.grid(row=3, column=0, padx=10, pady=2, sticky="ew")
        
        lbl_btn_content = ctk.CTkFrame(f_meta2, fg_color="transparent")
        lbl_btn_content.pack(fill="x")
        ctk.CTkLabel(lbl_btn_content, text=self.tr("meta_content"), font=ctk.CTkFont(size=11), text_color="gray").pack(side="left")
        ctk.CTkButton(lbl_btn_content, text="📋 Επικόλληση", width=60, height=20, fg_color="#444", hover_color="#555", command=lambda: self.paste_to_textbox(self.meta_content_box)).pack(side="right")
        
        self.meta_content_box = ctk.CTkTextbox(f_meta2, height=80)
        self.meta_content_box.pack(fill="x", expand=True, pady=(2, 0))
        
        self.save_meta_btn = ctk.CTkButton(self.meta_frame, text=self.tr("save_meta"), command=self.save_metatag, fg_color="#2b2b2b", hover_color="#3b3b3b")
        self.save_meta_btn.grid(row=4, column=0, padx=10, pady=(5, 10), sticky="ew")
        self.add_hover_border(self.save_meta_btn, "#6aa3cc")
        
        self.meta_list_frame = ctk.CTkScrollableFrame(self.meta_frame, height=150)
        self.meta_list_frame.grid(row=5, column=0, padx=10, pady=(0, 10), sticky="nsew")
        self.meta_list_frame.grid_columnconfigure(0, weight=1)

        # 6. ΠΛΑΙΣΙΟ ΕΚΚΑΘΑΡΙΣΗΣ ΚΛΠ
        sys_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="#141414", corner_radius=8, border_width=1, border_color="#333333")
        sys_frame.grid(row=6, column=0, padx=10, pady=(5, 10), sticky="ew")
        sys_frame.grid_columnconfigure(0, weight=1)

        self.sys_header_btn = self._create_collapsible_header(sys_frame, "⚙️ Σύστημα")

        self.backup_btn = ctk.CTkButton(sys_frame, text=self.tr("backup_data"), fg_color="#2b2b2b", hover_color="#3b3b3b", border_width=1, border_color="#444", command=self.backup_data)
        self.backup_btn.grid(row=1, column=0, padx=10, pady=(10, 5), sticky="ew")
        ToolTip(self.backup_btn, self.tr("tt_backup_data"))

        self.restore_btn = ctk.CTkButton(sys_frame, text=self.tr("restore_data"), fg_color="#2b2b2b", hover_color="#3b3b3b", border_width=1, border_color="#444", command=self.restore_data)
        self.restore_btn.grid(row=2, column=0, padx=10, pady=(0, 5), sticky="ew")
        ToolTip(self.restore_btn, self.tr("tt_restore_data"))

        self.clear_cache_btn = ctk.CTkButton(sys_frame, text=self.tr("clear_cache"), fg_color="transparent", border_width=1, text_color="gray", command=self.clear_cache)
        self.clear_cache_btn.grid(row=3, column=0, padx=10, pady=(5, 5), sticky="ew")
        ToolTip(self.clear_cache_btn, self.tr("tt_clear_cache"))

        self.clear_all_data_btn = ctk.CTkButton(sys_frame, text=self.tr("clear_all"), fg_color="transparent", border_width=1, text_color="#d9534f", hover_color="#3b1a1a", command=self.clear_all_data)
        self.clear_all_data_btn.grid(row=4, column=0, padx=10, pady=(5, 10), sticky="ew")
        ToolTip(self.clear_all_data_btn, self.tr("tt_clear_all"))

        self.status_label = ctk.CTkLabel(sys_frame, text="", text_color="green")
        self.status_label.grid(row=5, column=0, pady=(0, 10))

        self.update_watchlist_table()

        # --- ΣΤΗΛΗ 2: ΔΕΔΟΜΕΝΑ ---
        self.data_scroll_frame = ctk.CTkScrollableFrame(self.content_frame)
        self.data_scroll_frame.grid(row=0, column=1, sticky="nsew", padx=(5, 5), pady=(0, 10))
        self.data_scroll_frame.grid_columnconfigure(0, weight=1)

        # --- ΣΤΗΛΗ 3: ΕΠΙΣΚΟΠΗΣΗ ---
        self.overview_scroll_frame = ctk.CTkScrollableFrame(self.content_frame)
        self.overview_scroll_frame.grid(row=0, column=2, sticky="nsew", padx=(5, 10), pady=(0, 10))
        self.overview_scroll_frame.grid_columnconfigure(0, weight=1)

        ToolTip(self.toggle_settings_btn, lambda: self.tr("cannot_hide") if (self.sidebar_frame.winfo_viewable() and not self.data_scroll_frame.winfo_viewable() and not self.overview_scroll_frame.winfo_viewable()) else "")
        ToolTip(self.toggle_data_btn, lambda: self.tr("cannot_hide") if (self.data_scroll_frame.winfo_viewable() and not self.sidebar_frame.winfo_viewable() and not self.overview_scroll_frame.winfo_viewable()) else "")
        ToolTip(self.toggle_overview_btn, lambda: self.tr("cannot_hide") if (self.overview_scroll_frame.winfo_viewable() and not self.sidebar_frame.winfo_viewable() and not self.data_scroll_frame.winfo_viewable()) else "")

        self._build_data_pane(row=0, col=0)
        self._build_overview_pane(row=0, col=0)

        self.update_dropdown()
        self.update_models()
        self.update_history_ui()
        
        self.check_for_updates()

        self._toggle_collapsible(lang_frame, self.lang_header_btn, self.tr("language"))
        self._toggle_collapsible(api_frame, self.api_header_btn, self.tr("api_keys"))
        self._toggle_collapsible(self.stock_mng_frame, self.stock_mng_header_btn, self.tr("stock_management"))
        self._toggle_collapsible(self.meta_frame, self.meta_header_btn, self.tr("metatags_title"))
        self._toggle_collapsible(sys_frame, self.sys_header_btn, "⚙️ Σύστημα")
        self._toggle_collapsible(self.api_data_frame, self.api_data_header_btn, "🔌 Ενσωμάτωση Δεδομένων")
        
        self._toggle_collapsible(self.articles_frame, self.articles_header_btn, self.tr("paste_articles"))
        self._toggle_collapsible(self.extra_frame, self.extra_header_btn, self.tr("extra_prompt"))
        self._toggle_collapsible(self.hist_container, self.hist_header_btn, self.tr("history_title"))

        self.update_metatags_table()
        self.isolate_scrolling()
        
    def isolate_scrolling(self):
        """
        Εμποδίζει τα εξωτερικά ScrollableFrames από το να κάνουν scroll όταν το ποντίκι
        βρίσκεται πάνω από εσωτερικά στοιχεία που έχουν τη δική τους κύλιση.
        """
        def patch_scroll(outer, inners):
            old_wheel = outer._mouse_wheel_all
            def new_wheel(event):
                x, y = outer.winfo_pointerxy()
                for inner in inners:
                    if inner and inner.winfo_viewable():
                        x1 = inner.winfo_rootx()
                        y1 = inner.winfo_rooty()
                        x2 = x1 + inner.winfo_width()
                        y2 = y1 + inner.winfo_height()
                        if x1 <= x <= x2 and y1 <= y <= y2:
                            return # Αποτροπή scroll στο εξωτερικό frame
                old_wheel(event)
            outer._mouse_wheel_all = new_wheel
            
        patch_scroll(self.sidebar_frame, [self.watchlist_frame, self.stock_notes_entry, self.meta_list_frame, self.meta_content_box, getattr(self, "meta_info_entry", None)])
        patch_scroll(self.data_scroll_frame, [self.urls_frame, self.extra_prompt_box] + getattr(self, 'article_boxes', []))
        patch_scroll(self.overview_scroll_frame, [self.news_frame, self.newsapi_frame, self.rss_frame, self.notes_display_box, self.result_textbox])
        
        # Επιδιόρθωση bug του CustomTkinter (χάνει το scroll όταν βγαίνει το ποντίκι από εσωτερικό στοιχείο)
        def restore_outer_scroll(event, outer):
            if outer.winfo_viewable() and hasattr(outer, '_on_enter'):
                outer._on_enter()
                
        for inner, outer in [
            (self.watchlist_frame, self.sidebar_frame),
            (self.meta_list_frame, self.sidebar_frame),
            (self.urls_frame, self.data_scroll_frame),
            (self.news_frame, self.overview_scroll_frame),
            (self.newsapi_frame, self.overview_scroll_frame),
            (self.rss_frame, self.overview_scroll_frame)
        ]:
            if hasattr(inner, '_parent_canvas'):
                inner._parent_canvas.bind("<Leave>", lambda e, o=outer: restore_outer_scroll(e, o), add="+")

    def show_about_window(self):
        about_win = ctk.CTkToplevel(self)
        about_win.title(self.tr("about_title"))
        about_win.geometry("450x490")
        about_win.resizable(False, False)
        
        def set_icon():
            try:
                about_win.iconbitmap(resource_path("icon.ico"))
            except Exception:
                pass
        about_win.after(200, set_icon)
        
        about_win.transient(self) # Το κρατάει μπροστά από το κεντρικό παράθυρο
        about_win.grab_set()      # "Κλειδώνει" το κεντρικό παράθυρο μέχρι να κλείσει το About

        about_title_text = "  AI Stock Analyzer Desktop" if getattr(self, "logo_image_about", None) else "📈 AI Stock Analyzer Desktop"
        ctk.CTkLabel(about_win, text=about_title_text, image=getattr(self, "logo_image_about", None), compound="left", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 5))
        ctk.CTkLabel(about_win, text=self.tr("about_version"), font=ctk.CTkFont(size=12), text_color="gray").pack(pady=(0, 5))
        ctk.CTkLabel(about_win, text=self.tr("about_creator"), font=ctk.CTkFont(size=13, slant="italic", weight="bold"), text_color="#1f77b4").pack(pady=(0, 5))

        github_link = ctk.CTkLabel(about_win, text="🔗 GitHub Repository", text_color="#1f77b4", cursor="hand2", font=ctk.CTkFont(size=12, underline=True))
        github_link.pack(pady=(0, 10))
        github_link.bind("<Button-1>", lambda e: webbrowser.open("https://github.com/stratoslig/ai-stock-analyzer-Desktop"))
        
        desc = self.tr("about_desc")
        ctk.CTkLabel(about_win, text=desc, wraplength=400, justify="center").pack(pady=10, padx=20)

        disclaimer = self.tr("about_disclaimer")
        ctk.CTkLabel(about_win, text=disclaimer, wraplength=400, justify="center", font=ctk.CTkFont(size=11, slant="italic"), text_color="#d9534f").pack(pady=(10, 5))

        legal = f"⚖️ {self.tr('legal_notice_title')}: {self.tr('legal_notice_text')}"
        ctk.CTkLabel(about_win, text=legal, wraplength=400, justify="center", font=ctk.CTkFont(size=11, slant="italic"), text_color="#d9534f").pack(pady=(5, 20))

        ctk.CTkButton(about_win, text=self.tr("close_btn"), command=about_win.destroy, width=100, fg_color="#444", hover_color="#555").pack(pady=(0, 20))

    def tr(self, key):
        """Επιστρέφει τη μεταφρασμένη συμβολοσειρά για το δοσμένο κλειδί, βάσει της επιλεγμένης γλώσσας."""
        lang = self.user_data.get("language", "el")
        return TRANSLATIONS.get(lang, TRANSLATIONS["el"]).get(key, key)
        
    def change_language(self, choice):
        """Αλλάζει τη γλώσσα της εφαρμογής και αποθηκεύει την επιλογή στο προφίλ του χρήστη."""
        new_lang = "en" if choice == "English" else "el"
        if self.user_data.get("language") != new_lang:
            self.user_data["language"] = new_lang
            save_data(self.user_data)
            messagebox.showinfo("Επανεκκίνηση / Restart", "Παρακαλώ κάντε επανεκκίνηση της εφαρμογής (κλείσιμο και άνοιγμα) για να εφαρμοστεί πλήρως η αλλαγή γλώσσας.\n\nPlease restart the application to fully apply the language change.")

    def check_for_updates(self):
        """Ελέγχει αθόρυβα για νέες εκδόσεις μέσω του GitHub API."""
        def fetch():
            try:
                # Το API endpoint που φέρνει το πιο πρόσφατο release
                url = "https://api.github.com/repos/stratoslig/ai-stock-analyzer-Desktop/releases/latest"
                resp = requests.get(url, timeout=5)
                if resp.status_code == 200:
                    data = resp.json()
                    latest_version = data.get("tag_name", "").replace("v", "")
                    current_version = "1.4"
                    
                    # Απλή σύγκριση εκδόσεων (π.χ. "1.3" > "1.2")
                    if latest_version and latest_version != current_version:
                        try:
                            if tuple(map(int, latest_version.split("."))) > tuple(map(int, current_version.split("."))):
                                release_url = data.get("html_url")
                                # Εμφάνιση του μηνύματος μετά από 2 δευτερόλεπτα για να έχει φορτώσει το UI
                                self.after(2000, lambda: self._show_update_dialog(latest_version, release_url))
                        except Exception:
                            pass
            except Exception as e:
                logger.error(f"Σφάλμα ελέγχου ενημερώσεων: {e}")
        threading.Thread(target=fetch, daemon=True).start()

    def _show_update_dialog(self, version, url):
        msg = self.tr("update_msg").replace("{version}", version)
        if messagebox.askyesno(self.tr("update_title"), msg):
            webbrowser.open(url)

    def _sync_api_usage(self):
        """Συγχρονίζει τη χρήση των API. Μηδενίζει αυτόματα αν άλλαξε η μέρα."""
        today = datetime.date.today().isoformat()
        if "api_usage" not in self.user_data or self.user_data["api_usage"].get("date") != today:
            self.user_data["api_usage"] = {"date": today, "av": 0, "fh": 0, "newsapi": 0}
            save_data(self.user_data)
            
        usage = self.user_data.get("api_usage", {})
        
        if hasattr(self, 'cb_av'):
            av_rem = max(0, 25 - usage.get("av", 0))
            self.cb_av.configure(text=f"{self.tr('include_av')}{av_rem}/25)")
        if hasattr(self, 'cb_fh'):
            fh_rem = max(0, 60 - usage.get("fh", 0))
            self.cb_fh.configure(text=f"{self.tr('include_fh')}{fh_rem}/60)")
        if hasattr(self, 'cb_newsapi'):
            newsapi_rem = max(0, 100 - usage.get("newsapi", 0))
            self.cb_newsapi.configure(text=f"{self.tr('include_newsapi')}{newsapi_rem}/100)")

    def toggle_settings(self):
        """Εναλλάσσει την ορατότητα της αριστερής στήλης 'Ρυθμίσεις'."""
        if self.sidebar_frame.winfo_viewable():
            if not (self.data_scroll_frame.winfo_viewable() or self.overview_scroll_frame.winfo_viewable()):
                self.shake_button(self.toggle_settings_btn)
                return
            self.sidebar_frame.grid_remove()
            self.content_frame.grid_columnconfigure(0, minsize=0, weight=0)
            self.toggle_settings_btn.configure(fg_color=self.inactive_btn_color, text_color=self.inactive_text_color, border_color=self.inactive_btn_color)
        else:
            self.sidebar_frame.grid()
            self.content_frame.grid_columnconfigure(0, minsize=390, weight=0)
            self.toggle_settings_btn.configure(fg_color=self.active_btn_color, text_color=self.active_text_color, border_color=self.active_border_color)

    def toggle_data(self):
        """Εναλλάσσει την ορατότητα της μεσαίας στήλης 'Δεδομένα'."""
        if self.data_scroll_frame.winfo_viewable():
            if not (self.sidebar_frame.winfo_viewable() or self.overview_scroll_frame.winfo_viewable()):
                self.shake_button(self.toggle_data_btn)
                return
            self.data_scroll_frame.grid_remove()
            self.content_frame.grid_columnconfigure(1, minsize=0, weight=0)
            self.toggle_data_btn.configure(fg_color=self.inactive_btn_color, text_color=self.inactive_text_color, border_color=self.inactive_btn_color)
        else:
            self.data_scroll_frame.grid()
            self.content_frame.grid_columnconfigure(1, minsize=430, weight=1)
            self.toggle_data_btn.configure(fg_color=self.active_btn_color, text_color=self.active_text_color, border_color=self.active_border_color)

    def toggle_overview(self):
        """Εναλλάσσει την ορατότητα της δεξιάς στήλης 'Επισκόπηση'."""
        if self.overview_scroll_frame.winfo_viewable():
            if not (self.sidebar_frame.winfo_viewable() or self.data_scroll_frame.winfo_viewable()):
                self.shake_button(self.toggle_overview_btn)
                return
            self.overview_scroll_frame.grid_remove()
            self.content_frame.grid_columnconfigure(2, weight=0)
            self.toggle_overview_btn.configure(fg_color=self.inactive_btn_color, text_color=self.inactive_text_color, border_color=self.inactive_btn_color)
        else:
            self.overview_scroll_frame.grid()
            self.content_frame.grid_columnconfigure(2, weight=3)
            self.toggle_overview_btn.configure(fg_color=self.active_btn_color, text_color=self.active_text_color, border_color=self.active_border_color)

    def shake_button(self, widget, distance=4, count=4, delay=35):
        """Προσθέτει ένα οπτικό εφέ κουνήματος (shake) και κοκκινίσματος σε ένα κουμπί."""
        # Εναλλαγή περιθωρίων ώστε να κουνιέται, αλλά το συνολικό άθροισμα (10) να παραμένει
        # σταθερό για να μην επηρεάζονται τα διπλανά κουμπιά.
        def move_left(c):
            widget.pack_configure(padx=(5 - distance, 5 + distance))
            self.after(delay, lambda: move_right(c))
            
        def move_right(c):
            widget.pack_configure(padx=(5 + distance, 5 - distance))
            if c > 0:
                self.after(delay, lambda: move_left(c - 1))
            else:
                self.after(delay, lambda: widget.pack_configure(padx=5))
        
        # Στιγμιαία αλλαγή χρώματος σε κόκκινο προειδοποίησης
        widget.configure(fg_color="#d9534f", text_color="white", border_color="#d9534f")
        self.after(delay * count * 2, lambda: widget.configure(fg_color=self.active_btn_color, text_color=self.active_text_color, border_color=self.active_border_color))
        
        move_left(count)

    def add_hover_border(self, widget, hover_color="#888888"):
        """Προσθέτει ένα εφέ περιγράμματος όταν το ποντίκι περνάει πάνω από το κουμπί."""
        original_color = widget.cget("fg_color")
        widget.configure(border_width=1, border_color=original_color)
        
        def on_enter(e):
            widget.configure(border_color=hover_color)
            
        def on_leave(e):
            widget.configure(border_color=original_color)
            
        widget.bind("<Enter>", on_enter, add="+")
        widget.bind("<Leave>", on_leave, add="+")

    def _create_collapsible_header(self, parent_frame, title_text):
        header_btn = ctk.CTkButton(
            parent_frame,
            text=f"▼  {title_text}",
            font=ctk.CTkFont(size=15, weight="bold"),
            fg_color="transparent",
            text_color="#82c8fa",
            hover_color="#333333",
            anchor="w",
            command=lambda: self._toggle_collapsible(parent_frame, header_btn, title_text)
        )
        header_btn.grid(row=0, column=0, padx=5, pady=5, sticky="ew")
        return header_btn

    def _toggle_collapsible(self, parent_frame, header_btn, title_text):
        is_open = "▼" in header_btn.cget("text")
        for child in parent_frame.winfo_children():
            if child != header_btn:
                child.grid_remove() if is_open else child.grid()
        header_btn.configure(text=f"▶  {title_text}" if is_open else f"▼  {title_text}")

    def paste_to_entry(self, entry_widget):
        try:
            text = self.clipboard_get()
            if text:
                entry_widget.delete(0, "end")
                entry_widget.insert(0, text)
        except Exception:
            pass

    def paste_to_textbox(self, textbox_widget):
        try:
            text = self.clipboard_get()
            if text:
                textbox_widget.delete("1.0", "end")
                textbox_widget.insert("1.0", text)
        except Exception:
            pass

    def validate_scrape_articles(self, *args):
        val = self.scrape_articles_var.get()
        if not val:
            self.user_data["scrape_limit"] = ""
            save_data(self.user_data)
            return
        clean_val = "".join(filter(str.isdigit, val))
        if clean_val != val:
            self.scrape_articles_var.set(clean_val)
            return
        if int(clean_val) > 50:
            self.scrape_articles_var.set("50")
            return
        self.user_data["scrape_limit"] = clean_val
        save_data(self.user_data)

    def validate_scrape_chars(self, *args):
        val = self.scrape_chars_var.get()
        if not val:
            self.user_data["scrape_chars"] = ""
            save_data(self.user_data)
            return
        clean_val = "".join(filter(str.isdigit, val))
        if clean_val != val:
            self.scrape_chars_var.set(clean_val)
            return
        if int(clean_val) > 3000:
            self.scrape_chars_var.set("3000")
            return
        self.user_data["scrape_chars"] = clean_val
        save_data(self.user_data)

    def _build_data_pane(self, row, col):
        pane = ctk.CTkFrame(self.data_scroll_frame, fg_color="transparent")
        pane.grid(row=row, column=col, padx=(15, 10), pady=10, sticky="nsew")
        
        # --- ΤΙΤΛΟΣ ΔΕΔΟΜΕΝΩΝ ---
        data_title_lbl = ctk.CTkLabel(pane, text=self.tr("data_title"), font=ctk.CTkFont(size=18, weight="bold"))
        data_title_lbl.pack(anchor="w", pady=(0, 10))

        # 1. ΠΛΑΙΣΙΟ ΕΠΙΛΟΓΗΣ ΜΕΤΟΧΗΣ
        stock_sel_frame = ctk.CTkFrame(pane, fg_color="#141414", corner_radius=8, border_width=1, border_color="#333333")
        stock_sel_frame.pack(fill="x", pady=5)
        stock_sel_frame.grid_columnconfigure(0, weight=1)
        
        ctk.CTkLabel(stock_sel_frame, text=self.tr("select_stock"), font=ctk.CTkFont(size=15, weight="bold"), anchor="w").grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")

        stock_ctrl_frame = ctk.CTkFrame(stock_sel_frame, fg_color="transparent")
        stock_ctrl_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.stock_var = ctk.StringVar(value=self.tr("choose_stock_default"))
        self.stock_menu = ctk.CTkOptionMenu(stock_ctrl_frame, variable=self.stock_var, values=[self.tr("choose_stock_default")], command=self.on_stock_select)
        self.stock_menu.pack(side="left", fill="x", expand=True)
        
        # 2. ΠΛΑΙΣΙΟ URLS & RSS
        urls_main_frame = ctk.CTkFrame(pane, fg_color="#141414", corner_radius=8, border_width=1, border_color="#333333")
        urls_main_frame.pack(fill="x", pady=5)
        urls_main_frame.grid_columnconfigure(0, weight=1)
        
        self._create_collapsible_header(urls_main_frame, self.tr("saved_urls_rss"))
        
        self.urls_frame = ctk.CTkScrollableFrame(urls_main_frame, height=150)
        self.urls_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        
        self.url_rows = []
        for url_item in self.user_data.get("urls", []):
            self.add_url_row(url_item.get("title", ""), url_item.get("url", ""), url_item.get("type", "URL"))
            
        url_btns_frame = ctk.CTkFrame(urls_main_frame, fg_color="transparent")
        url_btns_frame.grid(row=2, column=0, sticky="w", padx=10, pady=2)
        
        self.add_url_btn = ctk.CTkButton(url_btns_frame, text=self.tr("add_url"), width=120, command=lambda: self.add_url_row("", "", "URL"))
        self.add_url_btn.pack(side="left", padx=(0, 5))
        
        self.save_urls_btn = ctk.CTkButton(url_btns_frame, text=self.tr("save_urls"), width=140, fg_color="#2b2b2b", hover_color="#3b3b3b", command=self.save_urls)
        self.save_urls_btn.pack(side="left")
        self.add_hover_border(self.save_urls_btn, "#6aa3cc")
            
        self.rss_filters_frame = ctk.CTkFrame(urls_main_frame, fg_color="transparent")
        self.rss_filters_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(5, 10))
        
        ctk.CTkLabel(self.rss_filters_frame, text=self.tr("rss_filters"), font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(0, 5))
        
        self.rss_keyword_entry = ctk.CTkEntry(self.rss_filters_frame, placeholder_text=self.tr("rss_keyword_ph"), width=180, height=24, font=ctk.CTkFont(size=11))
        self.rss_keyword_entry.pack(side="left", padx=(0, 5))
        ToolTip(self.rss_keyword_entry, self.tr("tt_rss_keyword"))
        self.rss_time_var = ctk.StringVar(value="Όλα")
        self.rss_time_menu = ctk.CTkOptionMenu(self.rss_filters_frame, variable=self.rss_time_var, values=["Όλα", "24 Ώρες", "3 Ημέρες", "7 Ημέρες"], width=90, height=24)
        self.rss_time_menu.pack(side="left")
        
        self.rss_apply_btn = ctk.CTkButton(self.rss_filters_frame, text=self.tr("rss_apply"), width=60, height=24, fg_color="#1f77b4", hover_color="#145c8f", command=self.apply_rss_filters)
        self.rss_apply_btn.pack(side="left", padx=(5, 0))
            
        self.scrape_settings_frame = ctk.CTkFrame(urls_main_frame, fg_color="transparent")
        self.scrape_settings_frame.grid(row=4, column=0, sticky="ew", padx=10, pady=(0, 10))
        
        ctk.CTkLabel(self.scrape_settings_frame, text=self.tr("scrape_settings"), font=ctk.CTkFont(size=11, weight="bold")).pack(side="left", padx=(0, 5))
        
        ctk.CTkLabel(self.scrape_settings_frame, text=self.tr("scrape_articles_lbl"), font=ctk.CTkFont(size=11)).pack(side="left", padx=(5, 2))
        self.scrape_articles_var = ctk.StringVar(value=self.user_data.get("scrape_limit", "10"))
        self.scrape_articles_var.trace_add("write", self.validate_scrape_articles)
        self.scrape_articles_entry = ctk.CTkEntry(self.scrape_settings_frame, textvariable=self.scrape_articles_var, width=40, height=24)
        self.scrape_articles_entry.pack(side="left", padx=(0, 5))
        ToolTip(self.scrape_articles_entry, self.tr("tt_scrape_articles"))
        
        ctk.CTkLabel(self.scrape_settings_frame, text=self.tr("scrape_chars_lbl"), font=ctk.CTkFont(size=11)).pack(side="left", padx=(5, 2))
        self.scrape_chars_var = ctk.StringVar(value=self.user_data.get("scrape_chars", "250"))
        self.scrape_chars_var.trace_add("write", self.validate_scrape_chars)
        self.scrape_chars_entry = ctk.CTkEntry(self.scrape_settings_frame, textvariable=self.scrape_chars_var, width=50, height=24)
        self.scrape_chars_entry.pack(side="left", padx=(0, 5))
        ToolTip(self.scrape_chars_entry, self.tr("tt_scrape_chars"))

        ToolTip(self.rss_time_menu, self.tr("tt_rss_time"))
        ToolTip(self.rss_apply_btn, self.tr("tt_rss_apply"))
        # 3. ΠΛΑΙΣΙΟ ΕΝΣΩΜΑΤΩΣΗΣ ΔΕΔΟΜΕΝΩΝ (APIs)
        self.api_data_frame = ctk.CTkFrame(pane, fg_color="#141414", corner_radius=8, border_width=1, border_color="#333333")
        self.api_data_frame.pack(fill="x", pady=5)
        self.api_data_frame.grid_columnconfigure(0, weight=1)
        
        self.api_data_header_btn = self._create_collapsible_header(self.api_data_frame, "🔌 Ενσωμάτωση Δεδομένων")

        usage = self.user_data.get("api_usage", {})
        av_rem = max(0, 25 - usage.get("av", 0))
        fh_rem = max(0, 60 - usage.get("fh", 0))
        newsapi_rem = max(0, 100 - usage.get("newsapi", 0))
            
        self.av_var = ctk.IntVar(value=0)
        self.cb_av = ctk.CTkCheckBox(self.api_data_frame, text=f"{self.tr('include_av')}{av_rem}/25)", variable=self.av_var, command=self.on_av_toggle)
        self.cb_av.grid(row=1, column=0, sticky="w", padx=10, pady=8)
        ToolTip(self.cb_av, self.tr("tt_cb_av"))
        
        self.fh_var = ctk.IntVar(value=0)
        self.cb_fh = ctk.CTkCheckBox(self.api_data_frame, text=f"{self.tr('include_fh')}{fh_rem}/60)", variable=self.fh_var, command=self.on_fh_toggle)
        self.cb_fh.grid(row=2, column=0, sticky="w", padx=10, pady=8)
        ToolTip(self.cb_fh, self.tr("tt_cb_fh"))

        self.newsapi_var = ctk.IntVar(value=0)
        self.cb_newsapi = ctk.CTkCheckBox(self.api_data_frame, text=f"{self.tr('include_newsapi')}{newsapi_rem}/100)", variable=self.newsapi_var, command=self.on_newsapi_toggle)
        self.cb_newsapi.grid(row=3, column=0, sticky="w", padx=10, pady=(8, 2))
        ToolTip(self.cb_newsapi, self.tr("tt_cb_newsapi"))
        
        self.newsapi_filters_frame = ctk.CTkFrame(self.api_data_frame, fg_color="transparent")
        self.newsapi_filters_frame.grid(row=4, column=0, sticky="ew", padx=30, pady=(0, 8))
        self.newsapi_q_entry = ctk.CTkEntry(self.newsapi_filters_frame, placeholder_text=self.tr("newsapi_ph_q"), width=100, height=24, font=ctk.CTkFont(size=11))
        self.newsapi_q_entry.pack(side="left", padx=(0, 5))
        self.newsapi_lang_entry = ctk.CTkEntry(self.newsapi_filters_frame, placeholder_text=self.tr("newsapi_ph_lang"), width=70, height=24, font=ctk.CTkFont(size=11))
        self.newsapi_lang_entry.pack(side="left", padx=(0, 5))
        self.newsapi_date_entry = ctk.CTkEntry(self.newsapi_filters_frame, placeholder_text=self.tr("newsapi_ph_date"), width=110, height=24, font=ctk.CTkFont(size=11))
        self.newsapi_date_entry.pack(side="left")
        ToolTip(self.newsapi_q_entry, self.tr("tt_newsapi_q"))
        ToolTip(self.newsapi_lang_entry, self.tr("tt_newsapi_lang"))
        ToolTip(self.newsapi_date_entry, self.tr("tt_newsapi_date"))

        self.cb_news = ctk.CTkCheckBox(self.api_data_frame, text=self.tr("include_news"))
        self.cb_news.grid(row=5, column=0, sticky="w", padx=10, pady=(8, 10))
        ToolTip(self.cb_news, self.tr("tt_cb_news"))
        
        # 4. ΠΛΑΙΣΙΟ ΕΠΙΚΟΛΛΗΣΗΣ ΑΡΘΡΩΝ
        self.articles_frame = ctk.CTkFrame(pane, fg_color="#141414", corner_radius=8, border_width=1, border_color="#333333")
        self.articles_frame.pack(fill="x", pady=5)
        self.articles_frame.grid_columnconfigure(0, weight=1)
        
        self.articles_header_btn = self._create_collapsible_header(self.articles_frame, self.tr("paste_articles"))

        self.article_boxes = []
        for i in range(3):
            art_frame = ctk.CTkFrame(self.articles_frame, fg_color="transparent")
            art_frame.grid(row=i+1, column=0, sticky="ew", padx=10, pady=2)
            lbl_btn_frame = ctk.CTkFrame(art_frame, fg_color="transparent")
            lbl_btn_frame.pack(fill="x")
            ctk.CTkLabel(lbl_btn_frame, text=f"{self.tr('article_num')}{i+1}:", font=ctk.CTkFont(size=11)).pack(side="left")
            
            box = ctk.CTkTextbox(art_frame, height=28, font=ctk.CTkFont(size=11))
            
            def resize_box(event=None, b=box):
                text = b.get("1.0", "end-1c")
                if not text:
                    b.configure(height=28)
                    return
                lines = sum(len(line) // 80 + 1 for line in text.split('\n'))
                new_height = min(max(1, lines), 12) * 16 + 12
                b.configure(height=new_height)
                
            box._textbox.bind("<KeyRelease>", resize_box)
            
            def paste_and_resize(b=box, r=resize_box):
                self.paste_to_textbox(b)
                r()
                
            def clear_and_resize(b=box):
                b.delete("1.0", "end")
                b.configure(height=28)
                
            clear_btn = ctk.CTkButton(lbl_btn_frame, text="❌", width=25, height=20, fg_color="#d9534f", hover_color="#c9302c", command=clear_and_resize)
            clear_btn.pack(side="right", padx=(5, 0))
            ToolTip(clear_btn, self.tr("tt_clear_article"))
            
            paste_btn = ctk.CTkButton(lbl_btn_frame, text=self.tr("paste"), width=60, height=20, fg_color="#444", hover_color="#555", command=paste_and_resize)
            paste_btn.pack(side="right")
            ToolTip(paste_btn, self.tr("tt_paste_article"))
            box.pack(fill="x", pady=(2, 5))
            self.article_boxes.append(box)

        # 5. ΠΛΑΙΣΙΟ ΕΠΙΠΛΕΟΝ ΟΔΗΓΙΩΝ & ΑΡΧΕΙΩΝ
        self.extra_frame = ctk.CTkFrame(pane, fg_color="#141414", corner_radius=8, border_width=1, border_color="#333333")
        self.extra_frame.pack(fill="x", pady=5)
        self.extra_frame.grid_columnconfigure(0, weight=1)
        
        self.extra_header_btn = self._create_collapsible_header(self.extra_frame, self.tr("extra_prompt"))
        
        prompt_header_frame = ctk.CTkFrame(self.extra_frame, fg_color="transparent")
        prompt_header_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(5, 2))

        self.metatag_insert_var = ctk.StringVar(value=self.tr("insert_meta"))
        self.metatag_insert_menu = ctk.CTkOptionMenu(prompt_header_frame, variable=self.metatag_insert_var, values=[self.tr("insert_meta")], width=140, height=24, command=self.insert_selected_metatag)
        self.metatag_insert_menu.pack(side="right", padx=(0, 10))

        def metatag_menu_tooltip():
            tags = self.user_data.get("metatags", [])
            lines = [self.tr("meta_info_tooltip_title")]
            has_info = False
            for t in tags:
                info = t.get('info', '').strip()
                if info:
                    lines.append(f"• {t['name']}: {info}")
                    has_info = True
            return "\n".join(lines) if has_info else self.tr("insert_meta")
            
        ToolTip(self.metatag_insert_menu, metatag_menu_tooltip)

        ctk.CTkButton(prompt_header_frame, text=self.tr("paste"), width=80, height=24, fg_color="#444", hover_color="#555", command=lambda: self.paste_to_textbox(self.extra_prompt_box)).pack(side="right")
        
        self.extra_prompt_box = ctk.CTkTextbox(self.extra_frame, height=80, font=ctk.CTkFont(size=12))
        self.extra_prompt_box.grid(row=2, column=0, sticky="ew", padx=10, pady=(0, 10))
        ToolTip(self.extra_prompt_box, self.tr("tt_extra_prompt"))

        self.attached_files = []
        self.files_frame = ctk.CTkFrame(self.extra_frame, fg_color="transparent")
        self.files_frame.grid(row=3, column=0, sticky="ew", padx=10, pady=(0, 10))
        
        attach_btn = ctk.CTkButton(self.files_frame, text=self.tr("add_file"), width=150, height=24, fg_color="#1f77b4", hover_color="#145c8f", command=self.attach_file)
        attach_btn.pack(side="left")
        
        self.clear_files_btn = ctk.CTkButton(self.files_frame, text="❌", width=24, height=24, fg_color="#d9534f", hover_color="#c9302c", command=self.clear_attached_files)
        
        self.files_list_label = ctk.CTkLabel(self.files_frame, text="", text_color="gray", font=ctk.CTkFont(size=11), wraplength=180)
        self.files_list_label.pack(side="left", padx=10)

        # 6. ΠΛΑΙΣΙΟ ΜΟΡΦΗΣ ΑΝΑΛΥΣΗΣ
        format_frame = ctk.CTkFrame(pane, fg_color="#141414", corner_radius=8, border_width=1, border_color="#333333")
        format_frame.pack(fill="x", pady=5)
        format_frame.grid_columnconfigure(0, weight=1)
        
        self._create_collapsible_header(format_frame, self.tr("analysis_format"))
        
        inner_format_frame = ctk.CTkFrame(format_frame, fg_color="transparent")
        inner_format_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        
        self.format_var = ctk.StringVar(value="Αναλυτικά")
        ctk.CTkRadioButton(inner_format_frame, text=self.tr("format_detailed"), variable=self.format_var, value="Αναλυτικά").pack(anchor="w", padx=10, pady=5)
        ctk.CTkRadioButton(inner_format_frame, text=self.tr("format_summary"), variable=self.format_var, value="Συνοπτικά").pack(anchor="w", padx=10, pady=5)

        # 7. ΕΝΑΡΞΗ ΑΝΑΛΥΣΗΣ & ΚΑΤΑΣΤΑΣΗ
        action_frame = ctk.CTkFrame(pane, fg_color="#141414", corner_radius=8, border_width=1, border_color="#333333")
        action_frame.pack(fill="x", pady=5)
        action_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(action_frame, text=self.tr("start_analysis"), font=ctk.CTkFont(size=15, weight="bold"), anchor="w").grid(row=0, column=0, padx=10, pady=(10, 5), sticky="ew")

        inner_action_frame = ctk.CTkFrame(action_frame, fg_color="transparent")
        inner_action_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=(5, 10))

        self.analyze_btn = ctk.CTkButton(inner_action_frame, text=self.tr("start_analysis"), font=ctk.CTkFont(weight="bold"), fg_color="#d9534f", hover_color="#c9302c", command=self.fetch_data, height=40)
        self.analyze_btn.pack(fill="x", pady=(0, 10))
        self.add_hover_border(self.analyze_btn, "#ff9999")
        
        self.ai_info_label = ctk.CTkLabel(inner_action_frame, text="", font=ctk.CTkFont(size=11, slant="italic"), text_color="gray")
        self.ai_info_label.pack(pady=(0, 5))
        
        self.status_main = ctk.CTkLabel(inner_action_frame, text="", text_color="orange")
        self.status_main.pack()

        # 8. ΙΣΤΟΡΙΚΟ (Collapse)
        self.hist_container = ctk.CTkFrame(pane, fg_color="#141414", corner_radius=8, border_width=1, border_color="#333333")
        self.hist_container.pack(fill="x", pady=5)
        self.hist_container.grid_columnconfigure(0, weight=1)
        
        self.hist_header_btn = self._create_collapsible_header(self.hist_container, self.tr("history_title"))
        
        self.hist_frame = ctk.CTkFrame(self.hist_container, fg_color="transparent")
        self.hist_frame.grid(row=1, column=0, sticky="ew", pady=(5, 10))

    def attach_file(self):
        file_paths = filedialog.askopenfilenames(
            title="Επιλογή Αρχείων",
            filetypes=[("Text & PDF Files", "*.txt *.pdf"), ("All Files", "*.*")]
        )
        for path in file_paths:
            if path not in self.attached_files:
                self.attached_files.append(path)
        self.update_attached_files_ui()

    def clear_attached_files(self):
        self.attached_files = []
        self.update_attached_files_ui()

    def update_attached_files_ui(self):
        if not self.attached_files:
            self.files_list_label.configure(text="")
            self.clear_files_btn.pack_forget()
        else:
            names = [os.path.basename(f) for f in self.attached_files]
            self.files_list_label.configure(text=", ".join(names))
            self.clear_files_btn.pack(side="left", padx=(5, 0))

    def add_url_row(self, title, url, typ="URL"):
        f = ctk.CTkFrame(self.urls_frame, fg_color="transparent")
        f.pack(fill="x", pady=2)
        
        type_var = ctk.StringVar(value=typ)
        chk_var = ctk.IntVar(value=0)
        
        def on_check():
            if type_var.get() in ["RSS", "Scraping"]:
                self.apply_rss_filters()
                
        cb = ctk.CTkCheckBox(f, text="", variable=chk_var, width=20, command=on_check)
        cb.pack(side="left")
        t_entry = ctk.CTkEntry(f, placeholder_text="Τίτλος", width=80)
        t_entry.pack(side="left", padx=5)
        if title: t_entry.insert(0, title)
        ToolTip(t_entry, lambda: t_entry.get())
        u_entry = ctk.CTkEntry(f, placeholder_text="https://...", width=150)
        
        row_dict = {}
        def delete_row():
            is_active_rss = (chk_var.get() == 1 and type_var.get() in ["RSS", "Scraping"])
            if row_dict in self.url_rows: self.url_rows.remove(row_dict)
            f.destroy()
            self.save_urls(silent=True, skip_validation=True)
            if is_active_rss:
                self.apply_rss_filters()
            
        def move_up():
            if row_dict in self.url_rows:
                idx = self.url_rows.index(row_dict)
                if idx > 0:
                    self.url_rows[idx - 1], self.url_rows[idx] = self.url_rows[idx], self.url_rows[idx - 1]
                    self._repack_url_rows()
                    self.save_urls(silent=True, skip_validation=True)

        def move_down():
            if row_dict in self.url_rows:
                idx = self.url_rows.index(row_dict)
                if idx < len(self.url_rows) - 1:
                    self.url_rows[idx + 1], self.url_rows[idx] = self.url_rows[idx], self.url_rows[idx + 1]
                    self._repack_url_rows()
                    self.save_urls(silent=True, skip_validation=True)
            
        del_btn = ctk.CTkButton(f, text="❌", width=25, fg_color="#d9534f", hover_color="#c9302c", command=delete_row)
        del_btn.pack(side="right", padx=(5, 0))
        
        paste_btn = ctk.CTkButton(f, text="📋", width=25, fg_color="#444", hover_color="#555", command=lambda: self.paste_to_entry(u_entry))
        paste_btn.pack(side="right", padx=(5, 0))
        ToolTip(paste_btn, self.tr("tt_paste_url"))

        down_btn = ctk.CTkButton(f, text="▼", width=20, fg_color="#444", hover_color="#555", command=move_down)
        down_btn.pack(side="right", padx=(2, 0))

        up_btn = ctk.CTkButton(f, text="▲", width=20, fg_color="#444", hover_color="#555", command=move_up)
        up_btn.pack(side="right", padx=(5, 0))
        
        def on_type_change(v):
            u_entry.configure(text_color="#ff9933" if v in ["RSS", "Scraping"] else "white")
            self.save_urls(silent=True, skip_validation=True)
            if chk_var.get() == 1:
                self.apply_rss_filters()
                
        type_menu = ctk.CTkOptionMenu(f, variable=type_var, values=["URL", "RSS", "Scraping"], width=85, command=on_type_change)
        type_menu.pack(side="left", padx=(0, 5))
        if typ in ["RSS", "Scraping"]:
            u_entry.configure(text_color="#ff9933")
            
        u_entry.pack(side="left", fill="x", expand=True)
        if url: u_entry.insert(0, url)
        ToolTip(u_entry, lambda: u_entry.get())
        
        row_dict.update({"frame": f, "chk": chk_var, "type": type_var, "title": t_entry, "url": u_entry})
        self.url_rows.append(row_dict)

    def _repack_url_rows(self):
        for row in self.url_rows:
            row["frame"].pack_forget()
        for row in self.url_rows:
            row["frame"].pack(fill="x", pady=2)

    def save_urls(self, silent=False, skip_validation=False):
        urls = []
        for row in self.url_rows:
            t = row["title"].get().strip()
            u = row["url"].get().strip()
            typ = row["type"].get()
            if u:
                if not skip_validation and typ == "RSS" and not stock_fetcher.validate_rss(u):
                    messagebox.showwarning(self.tr("rss_error_title"), self.tr("rss_error_invalid").replace("{u}", u))
                urls.append({"title": t, "url": u, "type": typ})
        self.user_data["urls"] = urls
        save_data(self.user_data)
        if not silent:
            self.status_main.configure(text="✅ Τα URLs αποθηκεύτηκαν!", text_color="green")

    def _build_overview_pane(self, row, col):
        pane = ctk.CTkFrame(self.overview_scroll_frame, fg_color="transparent")
        pane.grid(row=row, column=col, padx=10, pady=10, sticky="nsew")
        
        title_logo_frame = ctk.CTkFrame(pane, fg_color="transparent")
        title_logo_frame.pack(anchor="w", pady=(0, 10), fill="x")
        self.overview_title = ctk.CTkLabel(title_logo_frame, text=self.tr("overview_title"), font=ctk.CTkFont(size=18, weight="bold"))
        self.overview_title.pack(side="left")
        
        self.website_url = ""
        self.website_var = ctk.IntVar(value=1)
        self.website_link_label = ctk.CTkLabel(title_logo_frame, text="", text_color="#1f77b4", cursor="hand2", font=ctk.CTkFont(size=12, underline=True))
        self.website_link_label.bind("<Button-1>", lambda e: webbrowser.open(self.website_url) if self.website_url else None)
        ToolTip(self.website_link_label, self.tr("tt_website_link"))
        
        self.website_cb = ctk.CTkCheckBox(title_logo_frame, text=self.tr("include_website"), variable=self.website_var, font=ctk.CTkFont(size=11), width=20)
        ToolTip(self.website_cb, self.tr("tt_website_cb"))
        
        prices_container = ctk.CTkFrame(pane, fg_color="#141414", corner_radius=8, border_width=1, border_color="#333333")
        prices_container.pack(fill="x", pady=5)
        prices_container.grid_columnconfigure(0, weight=1)
        self._create_collapsible_header(prices_container, "Τιμές & Χρονικό Διάστημα")

        time_frame = ctk.CTkFrame(prices_container, fg_color="transparent")
        time_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        ctk.CTkLabel(time_frame, text=self.tr("chart_timeframe"), font=ctk.CTkFont(size=12)).pack(side="left")
        self.time_var = ctk.StringVar(value="6mo")
        self.time_menu = ctk.CTkOptionMenu(time_frame, variable=self.time_var, values=["1mo", "3mo", "6mo", "1y", "5y"], command=self.on_time_period_change)
        self.time_menu.pack(side="left", padx=10)
        
        prices_frame = ctk.CTkFrame(prices_container, fg_color="transparent")
        prices_frame.grid(row=2, column=0, sticky="ew", padx=10, pady=5)
        prices_frame.grid_columnconfigure((0,1,2), weight=1)
        self.l_yahoo = self.create_metric(prices_frame, "Yahoo Finance ⏱", "---", 0, 0, self.tr("tt_yahoo_price"))
        self.l_ft = self.create_metric(prices_frame, "Financial Times ⏱", "---", 0, 1, self.tr("tt_ft_price"))
        self.l_inv = self.create_metric(prices_frame, "Investing.com ⏱", "---", 0, 2, self.tr("tt_inv_price"))
        
        tabs_container = ctk.CTkFrame(pane, fg_color="#141414", corner_radius=8, border_width=1, border_color="#333333")
        tabs_container.pack(fill="x", pady=5)
        tabs_container.grid_columnconfigure(0, weight=1)
        self._create_collapsible_header(tabs_container, "Διαγράμματα & Πηγές")

        self.overview_tabs = ctk.CTkTabview(tabs_container, height=650)
        self.overview_tabs.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)
        
        self.tab_chart_name = self.tr("tab_chart")
        self.tab_news_name = self.tr("tab_news")
        self.tab_newsapi_name = self.tr("tab_newsapi")
        self.tab_pages_name = self.tr("tab_pages")
        self.tab_rss_name = self.tr("tab_rss")
        
        self.overview_tabs.add(self.tab_chart_name)
        self.overview_tabs.add(self.tab_pages_name)
        self.overview_tabs.add(self.tab_newsapi_name)
        self.overview_tabs.add(self.tab_news_name)
        self.overview_tabs.add(self.tab_rss_name)
        
        self.chart_tab = self.overview_tabs.tab(self.tab_chart_name)
        
        self.chart_inner_frame = ctk.CTkFrame(self.chart_tab, fg_color="transparent")
        self.chart_inner_frame.pack(fill="both", expand=True)
        self.chart_lbl = ctk.CTkLabel(self.chart_inner_frame, text="[Χώρος Γραφήματος Matplotlib]\nΤο γράφημα θα εμφανιστεί εδώ.", text_color="gray")
        self.chart_lbl.pack(fill="both", expand=True, pady=40)
        
        self.ind_frame = ctk.CTkFrame(self.chart_tab, fg_color="transparent")
        self.ind_frame.pack(fill="x", pady=5)
        
        self.show_sma_var = ctk.IntVar(value=1)
        ctk.CTkCheckBox(self.ind_frame, text="SMA (20, 50)", variable=self.show_sma_var, command=self.redraw_current_chart).pack(side="left", padx=10)
        
        self.show_ema_var = ctk.IntVar(value=0)
        ctk.CTkCheckBox(self.ind_frame, text="EMA (20, 50)", variable=self.show_ema_var, command=self.redraw_current_chart).pack(side="left", padx=10)
        
        self.news_search_var = ctk.StringVar()
        self.news_search_var.trace_add("write", self._filter_news_ui)
        self.news_search_entry = ctk.CTkEntry(self.overview_tabs.tab(self.tab_news_name), textvariable=self.news_search_var, placeholder_text="Αναζήτηση στα πρόσφατα νέα...", height=28)
        self.news_search_entry.pack(fill="x", padx=5, pady=(5, 0))

        ToolTip(self.news_search_entry, self.tr("tt_news_search"))

        self.news_frame = ctk.CTkScrollableFrame(self.overview_tabs.tab(self.tab_news_name))
        self.news_frame.pack(fill="both", expand=True, padx=5, pady=5)
        ctk.CTkLabel(self.news_frame, text="Οι ειδήσεις θα εμφανιστούν εδώ.", text_color="gray").pack(pady=20)
        
        self.newsapi_search_var = ctk.StringVar()
        self.newsapi_search_var.trace_add("write", self._filter_newsapi_ui)
        self.newsapi_search_entry = ctk.CTkEntry(self.overview_tabs.tab(self.tab_newsapi_name), textvariable=self.newsapi_search_var, placeholder_text="Αναζήτηση στο NewsAPI...", height=28)
        self.newsapi_search_entry.pack(fill="x", padx=5, pady=(5, 0))

        ToolTip(self.newsapi_search_entry, self.tr("tt_newsapi_search"))

        self.newsapi_frame = ctk.CTkScrollableFrame(self.overview_tabs.tab(self.tab_newsapi_name))
        self.newsapi_frame.pack(fill="both", expand=True, padx=5, pady=5)
        ctk.CTkLabel(self.newsapi_frame, text="Ενεργοποιήστε το NewsAPI αριστερά για προβολή.", text_color="gray").pack(pady=20)
        self.newsapi_checkboxes = []
        
        self.pages_frame = ctk.CTkFrame(self.overview_tabs.tab(self.tab_pages_name), fg_color="transparent")
        self.pages_frame.pack(fill="both", expand=True, padx=20, pady=20)
        ctk.CTkLabel(self.pages_frame, text="Επιλέξτε μια μετοχή για να δείτε τους συνδέσμους.", text_color="gray").pack(pady=20)
        
        self.rss_search_var = ctk.StringVar()
        self.rss_search_var.trace_add("write", self._filter_rss_ui)
        self.rss_search_entry = ctk.CTkEntry(self.overview_tabs.tab(self.tab_rss_name), textvariable=self.rss_search_var, placeholder_text="Αναζήτηση στα αποτελέσματα...", height=28)
        self.rss_search_entry.pack(fill="x", padx=5, pady=(5, 0))

        ToolTip(self.rss_search_entry, self.tr("tt_rss_search"))

        self.rss_frame = ctk.CTkScrollableFrame(self.overview_tabs.tab(self.tab_rss_name))
        self.rss_frame.pack(fill="both", expand=True, padx=5, pady=5)
        ctk.CTkLabel(self.rss_frame, text=self.tr("rss_empty_msg"), text_color="gray").pack(pady=20)
        
        self.stats_container = ctk.CTkFrame(pane, fg_color="#141414", corner_radius=8, border_width=1, border_color="#333333")
        self.stats_container.pack(fill="x", pady=5)
        self.stats_container.grid_columnconfigure(0, weight=1)
        self._create_collapsible_header(self.stats_container, self.tr("stats_title"))
        
        self.stats_frame = ctk.CTkFrame(self.stats_container, fg_color="transparent")
        self.stats_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        self.stats_frame.grid_columnconfigure((0,1,2,3), weight=1)
        self.l_mcap = self.create_metric(self.stats_frame, "Market Cap", "---", 0, 0, self.tr("tt_mcap"))
        self.l_pe = self.create_metric(self.stats_frame, "P/E Ratio", "---", 0, 1, self.tr("tt_pe"))
        self.l_div = self.create_metric(self.stats_frame, "Div Yield", "---", 0, 2, self.tr("tt_div"))
        self.l_beta = self.create_metric(self.stats_frame, "Beta", "---", 0, 3, self.tr("tt_beta"))

        self.notes_frame = ctk.CTkFrame(pane, fg_color="#141414", corner_radius=8, border_width=1, border_color="#333333")
        self.notes_frame.grid_columnconfigure(0, weight=1)
        self._create_collapsible_header(self.notes_frame, self.tr("stock_notes"))
        self.notes_display_box = ctk.CTkTextbox(self.notes_frame, wrap="word", font=ctk.CTkFont(size=12), fg_color="transparent", height=60)
        self.notes_display_box.grid(row=1, column=0, sticky="ew", padx=10, pady=(0, 10))
        self.notes_display_box.configure(state="disabled")

        # --- RSS/Scraping Controls ---
        self.rss_controls_frame = ctk.CTkFrame(self.overview_tabs.tab(self.tab_rss_name), fg_color="transparent")
        self.rss_controls_frame.pack(fill="x", padx=5, pady=(0, 5))

        self.rss_select_all_btn = ctk.CTkButton(self.rss_controls_frame, text=self.tr("select_all"), width=100, height=24, fg_color="#1f77b4", hover_color="#145c8f", command=self.select_all_rss)
        self.rss_select_all_btn.pack(side="left", padx=(0, 5))
        ToolTip(self.rss_select_all_btn, self.tr("tt_select_all"))

        self.rss_deselect_all_btn = ctk.CTkButton(self.rss_controls_frame, text=self.tr("deselect_all"), width=100, height=24, fg_color="#d9534f", hover_color="#c9302c", command=self.deselect_all_rss)
        self.rss_deselect_all_btn.pack(side="left", padx=(0, 5))
        ToolTip(self.rss_deselect_all_btn, self.tr("tt_deselect_all"))

        self.rss_show_selected_only = False
        self.rss_show_selected_btn = ctk.CTkButton(self.rss_controls_frame, text=self.tr("show_selected"), width=120, height=24, fg_color="#5cb85c", hover_color="#4cae4c", command=self.toggle_show_selected_rss)
        self.rss_show_selected_btn.pack(side="left", padx=(0, 10))
        ToolTip(self.rss_show_selected_btn, self.tr("tt_show_selected"))

        self.rss_selected_count_lbl = ctk.CTkLabel(self.rss_controls_frame, text=f"{self.tr('selected_articles')} 0", font=ctk.CTkFont(size=11, weight="bold"))
        self.rss_selected_count_lbl.pack(side="left", padx=(0, 5))

        # --- Recent News Controls ---
        self.news_controls_frame = ctk.CTkFrame(self.overview_tabs.tab(self.tab_news_name), fg_color="transparent")
        self.news_controls_frame.pack(fill="x", padx=5, pady=(0, 5))

        self.news_select_all_btn = ctk.CTkButton(self.news_controls_frame, text=self.tr("select_all"), width=100, height=24, fg_color="#1f77b4", hover_color="#145c8f", command=self.select_all_news)
        self.news_select_all_btn.pack(side="left", padx=(0, 5))
        ToolTip(self.news_select_all_btn, self.tr("tt_select_all"))

        self.news_deselect_all_btn = ctk.CTkButton(self.news_controls_frame, text=self.tr("deselect_all"), width=100, height=24, fg_color="#d9534f", hover_color="#c9302c", command=self.deselect_all_news)
        self.news_deselect_all_btn.pack(side="left", padx=(0, 5))
        ToolTip(self.news_deselect_all_btn, self.tr("tt_deselect_all"))

        self.news_show_selected_only = False
        self.news_show_selected_btn = ctk.CTkButton(self.news_controls_frame, text=self.tr("show_selected"), width=120, height=24, fg_color="#5cb85c", hover_color="#4cae4c", command=self.toggle_show_selected_news)
        self.news_show_selected_btn.pack(side="left", padx=(0, 10))
        ToolTip(self.news_show_selected_btn, self.tr("tt_show_selected"))

        self.news_selected_count_lbl = ctk.CTkLabel(self.news_controls_frame, text=f"{self.tr('selected_articles')} 0", font=ctk.CTkFont(size=11, weight="bold"))
        self.news_selected_count_lbl.pack(side="left", padx=(0, 5))

        # --- NewsAPI Controls ---
        self.newsapi_controls_frame = ctk.CTkFrame(self.overview_tabs.tab(self.tab_newsapi_name), fg_color="transparent")
        self.newsapi_controls_frame.pack(fill="x", padx=5, pady=(0, 5))

        self.newsapi_select_all_btn = ctk.CTkButton(self.newsapi_controls_frame, text=self.tr("select_all"), width=100, height=24, fg_color="#1f77b4", hover_color="#145c8f", command=self.select_all_newsapi)
        self.newsapi_select_all_btn.pack(side="left", padx=(0, 5))
        ToolTip(self.newsapi_select_all_btn, self.tr("tt_select_all"))

        self.newsapi_deselect_all_btn = ctk.CTkButton(self.newsapi_controls_frame, text=self.tr("deselect_all"), width=100, height=24, fg_color="#d9534f", hover_color="#c9302c", command=self.deselect_all_newsapi)
        self.newsapi_deselect_all_btn.pack(side="left", padx=(0, 5))
        ToolTip(self.newsapi_deselect_all_btn, self.tr("tt_deselect_all"))

        self.newsapi_show_selected_only = False
        self.newsapi_show_selected_btn = ctk.CTkButton(self.newsapi_controls_frame, text=self.tr("show_selected"), width=120, height=24, fg_color="#5cb85c", hover_color="#4cae4c", command=self.toggle_show_selected_newsapi)
        self.newsapi_show_selected_btn.pack(side="left", padx=(0, 10))
        ToolTip(self.newsapi_show_selected_btn, self.tr("tt_show_selected"))

        self.newsapi_selected_count_lbl = ctk.CTkLabel(self.newsapi_controls_frame, text=f"{self.tr('selected_articles')} 0", font=ctk.CTkFont(size=11, weight="bold"))
        self.newsapi_selected_count_lbl.pack(side="left", padx=(0, 5))

        # Re-pack the frames to ensure correct order
        self.news_search_entry.pack_forget()
        self.news_controls_frame.pack_forget()
        self.news_frame.pack_forget()
        self.newsapi_search_entry.pack_forget()
        self.newsapi_controls_frame.pack_forget()
        self.newsapi_frame.pack_forget()
        self.rss_search_entry.pack_forget()
        self.rss_controls_frame.pack_forget()
        self.rss_frame.pack_forget()

        self.news_search_entry.pack(fill="x", padx=5, pady=(5, 0))
        self.news_controls_frame.pack(fill="x", padx=5, pady=(0, 5))
        self.news_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.newsapi_search_entry.pack(fill="x", padx=5, pady=(5, 0))
        self.newsapi_controls_frame.pack(fill="x", padx=5, pady=(0, 5))
        self.newsapi_frame.pack(fill="both", expand=True, padx=5, pady=5)

        self.rss_search_entry.pack(fill="x", padx=5, pady=(5, 0))
        self.rss_controls_frame.pack(fill="x", padx=5, pady=(0, 5))
        self.rss_frame.pack(fill="both", expand=True, padx=5, pady=5)

        # Initial update of counts
        self._update_rss_selected_count()
        self._update_news_selected_count()
        self._update_newsapi_selected_count()

        # Ensure initial state for "Show Selected" buttons
        self.rss_show_selected_btn.configure(fg_color="#5cb85c" if not self.rss_show_selected_only else "#f0ad4e", hover_color="#4cae4c" if not self.rss_show_selected_only else "#ec971f")
        self.news_show_selected_btn.configure(fg_color="#5cb85c" if not self.news_show_selected_only else "#f0ad4e", hover_color="#4cae4c" if not self.news_show_selected_only else "#ec971f")
        self.newsapi_show_selected_btn.configure(fg_color="#5cb85c" if not self.newsapi_show_selected_only else "#f0ad4e", hover_color="#4cae4c" if not self.newsapi_show_selected_only else "#ec971f")

        
        health_container = ctk.CTkFrame(pane, fg_color="#141414", corner_radius=8, border_width=1, border_color="#333333")
        health_container.pack(fill="x", pady=5)
        health_container.grid_columnconfigure(0, weight=1)
        self._create_collapsible_header(health_container, self.tr("health_title"))
        
        health_frame = ctk.CTkFrame(health_container, fg_color="transparent")
        health_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        health_frame.grid_columnconfigure((0,1,2,3), weight=1)
        self.l_rev_growth = self.create_metric(health_frame, "Rev Growth", "---", 0, 0, self.tr("tt_rev_growth"))
        self.l_roe = self.create_metric(health_frame, "ROE", "---", 0, 1, self.tr("tt_roe"))
        self.l_op_margin = self.create_metric(health_frame, "Op Margin", "---", 0, 2, self.tr("tt_op_margin"))
        self.l_dte = self.create_metric(health_frame, "Debt/Eq", "---", 0, 3, self.tr("tt_dte"))
        self.l_fcf = self.create_metric(health_frame, "Free Cash Flow", "---", 1, 0, self.tr("tt_fcf"))
        
        tech_container = ctk.CTkFrame(pane, fg_color="#141414", corner_radius=8, border_width=1, border_color="#333333")
        tech_container.pack(fill="x", pady=5)
        tech_container.grid_columnconfigure(0, weight=1)
        self._create_collapsible_header(tech_container, self.tr("tech_title"))
        
        tech_frame = ctk.CTkFrame(tech_container, fg_color="transparent")
        tech_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        tech_frame.grid_columnconfigure((0,1,2,3), weight=1)
        self.l_rsi = self.create_metric(tech_frame, "RSI (14)", "---", 0, 0, self.tr("tt_rsi"))
        self.l_macd = self.create_metric(tech_frame, "MACD", "---", 0, 1, self.tr("tt_macd"))
        self.l_sma20 = self.create_metric(tech_frame, "SMA 20", "---", 0, 2, self.tr("tt_sma20"))
        self.l_sma50 = self.create_metric(tech_frame, "SMA 50", "---", 0, 3, self.tr("tt_sma50"))

        self.av_container = ctk.CTkFrame(pane, fg_color="#141414", corner_radius=8, border_width=1, border_color="#333333")
        self.av_container.grid_columnconfigure(0, weight=1)
        self._create_collapsible_header(self.av_container, self.tr("av_title"))
        
        self.av_frame = ctk.CTkFrame(self.av_container, fg_color="transparent")
        self.av_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        self.av_frame.grid_columnconfigure((0,1,2), weight=1)
        self.l_av_pe = self.create_metric(self.av_frame, "PE Ratio (AV)", "---", 0, 0, self.tr("tt_av_pe"))
        self.l_av_div = self.create_metric(self.av_frame, "Div Yield (AV)", "---", 0, 1, self.tr("tt_av_div"))
        self.l_av_eps = self.create_metric(self.av_frame, "EPS (AV)", "---", 0, 2, self.tr("tt_av_eps"))

        self.fh_container = ctk.CTkFrame(pane, fg_color="#141414", corner_radius=8, border_width=1, border_color="#333333")
        self.fh_container.grid_columnconfigure(0, weight=1)
        self._create_collapsible_header(self.fh_container, self.tr("fh_title"))
        
        self.fh_frame = ctk.CTkFrame(self.fh_container, fg_color="transparent")
        self.fh_frame.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        self.fh_frame.grid_columnconfigure((0,1,2,3), weight=1)
        self.l_fh_cur = self.create_metric(self.fh_frame, self.tr("fh_lbl_cur"), "---", 0, 0, self.tr("tt_fh_cur"))
        self.l_fh_open = self.create_metric(self.fh_frame, self.tr("fh_lbl_open"), "---", 0, 1, self.tr("tt_fh_open"))
        self.l_fh_high = self.create_metric(self.fh_frame, self.tr("fh_lbl_high"), "---", 0, 2, self.tr("tt_fh_high"))
        self.l_fh_low = self.create_metric(self.fh_frame, self.tr("fh_lbl_low"), "---", 0, 3, self.tr("tt_fh_low"))

        self.ai_container = ctk.CTkFrame(pane, fg_color="#141414", corner_radius=8, border_width=1, border_color="#333333")
        self.ai_container.pack(fill="x", pady=5)
        self.ai_container.grid_columnconfigure(0, weight=1)
        self._create_collapsible_header(self.ai_container, self.tr("ai_analysis_title"))
        
        self.result_textbox = ctk.CTkTextbox(self.ai_container, wrap="word", font=ctk.CTkFont(size=self.ai_font_size), height=300)
        self.result_textbox.grid(row=1, column=0, sticky="ew", padx=10, pady=5)
        
        actions_frame = ctk.CTkFrame(self.ai_container, fg_color="transparent")
        actions_frame.grid(row=2, column=0, sticky="e", padx=10, pady=(0, 10))
        
        zoom_frame = ctk.CTkFrame(actions_frame, fg_color="transparent")
        zoom_frame.pack(side="left", padx=(0, 15))
        ctk.CTkLabel(zoom_frame, text="Μέγεθος:", font=ctk.CTkFont(size=11), text_color="gray").pack(side="left", padx=(0, 5))
        ctk.CTkButton(zoom_frame, text="-", width=22, height=22, fg_color="#444", hover_color="#555", font=ctk.CTkFont(weight="bold"), command=self.decrease_ai_font).pack(side="left", padx=2)
        ctk.CTkButton(zoom_frame, text="+", width=22, height=22, fg_color="#444", hover_color="#555", font=ctk.CTkFont(weight="bold"), command=self.increase_ai_font).pack(side="left", padx=2)
        
        print_btn = ctk.CTkButton(actions_frame, text=self.tr("print"), fg_color="#1f77b4", hover_color="#145c8f", command=self.print_analysis)
        print_btn.pack(side="left", padx=(0, 10))
        self.add_hover_border(print_btn, "#99c2ff")
        
        export_btn = ctk.CTkButton(actions_frame, text=self.tr("export_word"), fg_color="#28a745", hover_color="#218838", command=self.export_to_word)
        export_btn.pack(side="left")
        self.add_hover_border(export_btn, "#99e699")
        
        export_pdf_btn = ctk.CTkButton(actions_frame, text=self.tr("export_pdf"), fg_color="#d9534f", hover_color="#c9302c", command=self.export_to_pdf)
        export_pdf_btn.pack(side="left", padx=(10, 0))
        self.add_hover_border(export_pdf_btn, "#ff9999")

    def increase_ai_font(self):
        self.ai_font_size = min(30, self.ai_font_size + 2)
        self.result_textbox.configure(font=ctk.CTkFont(size=self.ai_font_size))

    def decrease_ai_font(self):
        self.ai_font_size = max(10, self.ai_font_size - 2)
        self.result_textbox.configure(font=ctk.CTkFont(size=self.ai_font_size))

    def redraw_current_chart(self):
        if hasattr(self, 'current_df') and self.current_df is not None:
            self.draw_chart(self.current_df)

    def update_history_ui(self):
        for widget in self.hist_frame.winfo_children():
            widget.destroy()
            
        history = self.user_data.get("history", [])
        if not history:
            ctk.CTkLabel(self.hist_frame, text="Δεν υπάρχει ιστορικό αναλύσεων.", text_color="gray").pack(pady=10)
            return
            
        for item in reversed(history): # Εμφάνιση των πιο πρόσφατων πάνω-πάνω
            btn_text = f"▶ {item.get('stock', 'Άγνωστο')} - {item.get('date', '')}"
            
            row_f = ctk.CTkFrame(self.hist_frame, fg_color="transparent")
            row_f.pack(fill="x", padx=10, pady=2)
            
            del_btn = ctk.CTkButton(row_f, text="❌", width=30, fg_color="#d9534f", hover_color="#c9302c", command=lambda i=item: self.delete_history_item(i))
            del_btn.pack(side="right", padx=(5, 0))
            
            btn = ctk.CTkButton(row_f, text=btn_text, fg_color="#1c1c1c", text_color="white", anchor="w", hover_color="#2b2b2b", command=lambda i=item: self.load_history_item(i))
            btn.pack(side="left", fill="x", expand=True)

    def load_history_item(self, item):
        stock_name = item.get("stock", "")
        
        # Έλεγχος αν η μετοχή υπάρχει ακόμα στη Watchlist
        watchlist_names = [w.get("Ονομασία") for w in self.user_data.get("watchlist", [])]
        if stock_name in watchlist_names:
            # Αυτόματη επιλογή της μετοχής και φόρτωση των δεδομένων της
            self.stock_var.set(stock_name)
            self.on_stock_select(stock_name)
        else:
            lang = self.user_data.get("language", "el")
            warn_title = "Warning" if lang == "en" else "Προσοχή"
            warn_msg = f"The stock '{stock_name}' is no longer in the Watchlist.\nThe analysis text was loaded, but charts and prices cannot be updated." if lang == "en" else f"Η μετοχή '{stock_name}' δεν υπάρχει πλέον στη Watchlist.\nΤο κείμενο της ανάλυσης φορτώθηκε, αλλά τα γραφήματα και οι τιμές δεν μπορούν να ανανεωθούν."
            messagebox.showwarning(warn_title, warn_msg)

        self.result_textbox.delete("1.0", "end")
        self.result_textbox.insert("1.0", item.get("text", ""))
        self.overview_title.configure(text=f"{stock_name} - Ανάγνωση από Ιστορικό")
        self.status_main.configure(text="✅ Φορτώθηκε από το ιστορικό", text_color="green")
        self.current_analysis_stock = stock_name

    def delete_history_item(self, item):
        history = self.user_data.get("history", [])
        if item in history:
            history.remove(item)
            self.user_data["history"] = history
            save_data(self.user_data)
            self.update_history_ui()

    def create_metric(self, parent, title, value, row, col, tooltip_text=""):
        frame = ctk.CTkFrame(parent, fg_color="transparent")
        frame.grid(row=row, column=col, padx=5, pady=2, sticky="w")
        title_lbl = ctk.CTkLabel(frame, text=title, font=ctk.CTkFont(size=11), text_color="gray")
        title_lbl.pack(anchor="w")
        value_label = ctk.CTkLabel(frame, text=value, font=ctk.CTkFont(size=15, weight="bold"))
        value_label.pack(anchor="w")
        if tooltip_text:
            ToolTip(title_lbl, tooltip_text)
            ToolTip(value_label, tooltip_text)
        return value_label

    def _create_highlighted_textbox(self, parent_frame, scrollable_frame, text, terms, font, text_color, width, is_title=False, url=""):
        chars_per_line = 60 if is_title else 75
        line_height = 22 if is_title else 18
        lines = (len(text) // chars_per_line) + 1 + text.count('\n')
        h = (lines + 1) * line_height
        
        box = ctk.CTkTextbox(parent_frame, wrap="word", font=font, text_color=text_color, fg_color="transparent", width=width, height=h)
        box.insert("1.0", text)
        
        box._textbox.tag_config("hl", background="#e6c300", foreground="black")
        if terms:
            for term in terms:
                start_idx = "1.0"
                while True:
                    pos = box._textbox.search(term, start_idx, stopindex="end", nocase=True)
                    if not pos:
                        break
                    end_idx = f"{pos}+{len(term)}c"
                    box._textbox.tag_add("hl", pos, end_idx)
                    start_idx = end_idx
                    
        box.configure(state="disabled")
        
        if url:
            box._textbox.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
            box._textbox.configure(cursor="hand2")
            
        def pass_wheel(event):
            if sys.platform == "darwin":
                scrollable_frame._parent_canvas.yview_scroll(int(-1 * event.delta), "units")
            else:
                scrollable_frame._parent_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
                
        box._textbox.bind("<MouseWheel>", pass_wheel)
        box._textbox.bind("<Button-4>", lambda e: scrollable_frame._parent_canvas.yview_scroll(-1, "units"))
        box._textbox.bind("<Button-5>", lambda e: scrollable_frame._parent_canvas.yview_scroll(1, "units"))
        
        return box

    def on_av_toggle(self):
        if self.av_var.get() == 1:
            self.av_container.pack(fill="x", pady=5, before=self.ai_container)
            self._trigger_av_fetch()
        else:
            self.av_container.pack_forget()
            self.l_av_pe.configure(text="---")
            self.l_av_div.configure(text="---")
            self.l_av_eps.configure(text="---")
            self.current_av_context = ""

    def on_fh_toggle(self):
        if self.fh_var.get() == 1:
            self.fh_container.pack(fill="x", pady=5, before=self.ai_container)
            self._trigger_fh_fetch()
        else:
            self.fh_container.pack_forget()
            self.l_fh_cur.configure(text="---")
            self.l_fh_open.configure(text="---")
            self.l_fh_high.configure(text="---")
            self.l_fh_low.configure(text="---")
            self.current_fh_context = ""

    def _get_current_symbol(self):
        selected_name = self.stock_var.get()
        stock_data = next((item for item in self.user_data.get("watchlist", []) if item.get("Ονομασία") == selected_name), None)
        return stock_data.get("Yahoo") if stock_data else None

    def _trigger_av_fetch(self):
        self._sync_api_usage()
        symbol = self._get_current_symbol()
        av_key = self.user_data.get("av_api_key")
        if not symbol: return
        if not av_key:
            self.status_main.configure(text="⚠️ Το API Key του Alpha Vantage απουσιάζει!", text_color="orange")
            self.av_var.set(0)
            return
        if self.user_data.get("api_usage", {}).get("av", 0) >= 25:
            self.status_main.configure(text="⚠️ Το ημερήσιο όριο Alpha Vantage εξαντλήθηκε!", text_color="orange")
            self.av_var.set(0)
            return
        self.l_av_pe.configure(text="...")
        self.l_av_div.configure(text="...")
        self.l_av_eps.configure(text="...")
        threading.Thread(target=self._fetch_av_thread, args=(symbol, av_key), daemon=True).start()

    def _fetch_av_thread(self, symbol, av_key):
        av_data = stock_fetcher.get_alpha_vantage_data(symbol, av_key)
        self.after(0, self._update_av_ui, av_data)

    def _update_av_ui(self, av_data):
        if not av_data.get("error"):
            self.user_data["api_usage"]["av"] = self.user_data.get("api_usage", {}).get("av", 0) + 1
            save_data(self.user_data)
            self._sync_api_usage()
            
            self.l_av_pe.configure(text=av_data.get("pe", "N/A"))
            self.l_av_eps.configure(text=av_data.get("eps", "N/A"))
            self.l_av_div.configure(text=av_data.get("div", "N/A"))
            self.current_av_context = f"\n\n[ΘΕΜΕΛΙΩΔΗ ALPHA VANTAGE]\nPE Ratio: {av_data.get('pe')} | EPS: {av_data.get('eps')} | Div Yield: {av_data.get('div')} | Target Price: {av_data.get('target')} | 52W High: {av_data.get('52high')} | 52W Low: {av_data.get('52low')}"
        else:
            self.status_main.configure(text=f"⚠️ Σφάλμα AV: {av_data.get('error')}", text_color="orange")
            self.l_av_pe.configure(text="Σφάλμα")
            self.l_av_eps.configure(text="Σφάλμα")
            self.l_av_div.configure(text="Σφάλμα")
            self.current_av_context = ""
            self.av_var.set(0)

    def _trigger_fh_fetch(self):
        self._sync_api_usage()
        symbol = self._get_current_symbol()
        fh_key = self.user_data.get("finnhub_api_key")
        if not symbol: return
        if not fh_key:
            self.status_main.configure(text="⚠️ Το API Key του Finnhub απουσιάζει!", text_color="orange")
            self.fh_var.set(0)
            return
        if self.user_data.get("api_usage", {}).get("fh", 0) >= 60:
            self.status_main.configure(text="⚠️ Το ημερήσιο όριο Finnhub εξαντλήθηκε!", text_color="orange")
            self.fh_var.set(0)
            return
        self.l_fh_cur.configure(text="...")
        self.l_fh_open.configure(text="...")
        self.l_fh_high.configure(text="...")
        self.l_fh_low.configure(text="...")
        threading.Thread(target=self._fetch_fh_thread, args=(symbol, fh_key), daemon=True).start()

    def _fetch_fh_thread(self, symbol, fh_key):
        fh_data = stock_fetcher.get_finnhub_data(symbol, fh_key)
        self.after(0, self._update_fh_ui, fh_data)

    def _update_fh_ui(self, fh_data):
        if not fh_data.get("error"):
            self.user_data["api_usage"]["fh"] = self.user_data.get("api_usage", {}).get("fh", 0) + 1
            save_data(self.user_data)
            self._sync_api_usage()
            
            self.l_fh_cur.configure(text=fh_data.get("current", "N/A"))
            self.l_fh_open.configure(text=fh_data.get("open", "N/A"))
            self.l_fh_high.configure(text=fh_data.get("high", "N/A"))
            self.l_fh_low.configure(text=fh_data.get("low", "N/A"))
            self.current_fh_context = f"\n\n[ΖΩΝΤΑΝΑ ΔΕΔΟΜΕΝΑ FINNHUB]\nΤρέχουσα: {fh_data.get('current')} | Άνοιγμα: {fh_data.get('open')} | Υψηλό: {fh_data.get('high')} | Χαμηλό: {fh_data.get('low')}"
        else:
            self.status_main.configure(text=f"⚠️ Σφάλμα Finnhub: {fh_data.get('error')}", text_color="orange")
            self.l_fh_cur.configure(text="Σφάλμα")
            self.l_fh_open.configure(text="Σφάλμα")
            self.l_fh_high.configure(text="Σφάλμα")
            self.l_fh_low.configure(text="Σφάλμα")
            self.current_fh_context = ""
            self.fh_var.set(0)

    def apply_rss_filters(self):
        rss_urls = []
        scrape_urls = []
        if hasattr(self, 'url_rows'):
            for row in self.url_rows:
                if row["chk"].get() == 1:
                    typ = row["type"].get()
                    u_val = row["url"].get().strip()
                    if u_val:
                        if typ == "RSS": rss_urls.append(u_val)
                        elif typ == "Scraping": scrape_urls.append(u_val)
                    
        if not rss_urls and not scrape_urls:
            for widget in self.rss_frame.winfo_children():
                widget.destroy()
            ctk.CTkLabel(self.rss_frame, text=self.tr("rss_empty_msg"), text_color="gray").pack(pady=20)
            self.rss_checkboxes = []
            return

        for widget in self.rss_frame.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.rss_frame, text=self.tr("rss_fetching"), text_color="orange").pack(pady=20)

        kw = self.rss_keyword_entry.get().strip()
        t_val = self.rss_time_var.get()
        
        try: scrape_limit = int(self.scrape_articles_var.get())
        except ValueError: scrape_limit = 10
        try: scrape_chars = int(self.scrape_chars_var.get())
        except ValueError: scrape_chars = 250
        
        threading.Thread(target=self._fetch_rss_thread, args=(rss_urls, scrape_urls, kw, t_val, scrape_limit, scrape_chars), daemon=True).start()

    def _fetch_rss_thread(self, rss_urls, scrape_urls, kw, t_val, scrape_limit=10, scrape_chars=250):
        days_map = {"24 Ώρες": 1, "3 Ημέρες": 3, "7 Ημέρες": 7}
        combined_data = []
        if rss_urls:
            combined_data.extend(stock_fetcher.get_rss_news(rss_urls, keyword=kw, days_limit=days_map.get(t_val)))
        if scrape_urls:
            combined_data.extend(stock_fetcher.get_scraped_articles(scrape_urls, keyword=kw, limit=scrape_limit, char_limit=scrape_chars))
        combined_data.sort(key=lambda x: x.get("date", ""), reverse=True)
        self.after(0, self._update_rss_ui, combined_data)

    def _update_rss_ui(self, rss_data):
        for widget in self.rss_frame.winfo_children():
            widget.destroy()
        self.rss_checkboxes = []
        self.rss_article_frames = []
        
        kw = self.rss_keyword_entry.get().strip()
        search_terms = []
        if kw:
            for group in kw.split(','):
                for term in group.split('+'):
                    t = term.strip()
                    if t and t not in search_terms:
                        search_terms.append(t)
        # Ταξινομούμε κατά μήκος ώστε να επισημαίνονται πρώτα οι μεγαλύτερες φράσεις
        search_terms.sort(key=len, reverse=True)

        if not rss_data:
            msg = self.tr("rss_no_news") if hasattr(self, 'url_rows') and any(r["chk"].get() == 1 and r["type"].get() in ["RSS", "Scraping"] for r in self.url_rows) else self.tr("rss_empty_msg")
            ctk.CTkLabel(self.rss_frame, text=msg, text_color="gray").pack(pady=20)
        else:
            for article in rss_data:
                f = ctk.CTkFrame(self.rss_frame, fg_color="#1c1c1c", corner_radius=8, border_width=1, border_color="#333333")
                f.pack(fill="x", pady=4, padx=4)
                
                chk_var = ctk.IntVar(value=0)
                cb = ctk.CTkCheckBox(f, text="", variable=chk_var, width=20, command=self._on_rss_chk_toggle)
                cb.pack(side="left", anchor="n", pady=10, padx=10)
                self.rss_checkboxes.append((chk_var, article))
                self.rss_article_frames.append((f, article))
                
                text_f = ctk.CTkFrame(f, fg_color="transparent")
                text_f.pack(side="left", fill="x", expand=True, pady=10, padx=(0, 10))
                
                title = article.get("title", "Χωρίς Τίτλο")
                desc = article.get("description", "")
                        
                url = article.get("url", "")
                source = article.get("source", "")
                date = article.get("date", "")
                
                title_box = self._create_highlighted_textbox(text_f, self.rss_frame, f"📰 {title}", search_terms, ctk.CTkFont(weight="bold", size=12), "#ff9933", 550, True, url)
                title_box.pack(anchor="w", pady=(0, 2))
                    
                ctk.CTkLabel(text_f, text=f"Πηγή: {source} | Ημ/νία: {date}", font=ctk.CTkFont(size=10), text_color="gray", anchor="w").pack(anchor="w")
                
                if desc:
                    desc_box = self._create_highlighted_textbox(text_f, self.rss_frame, desc, search_terms, ctk.CTkFont(size=11), "white", 550, False, "")
                    desc_box.pack(anchor="w", pady=(0, 4))
        self._update_rss_selected_count()
                    
        self._filter_rss_ui()

    def _filter_rss_ui(self, *args):
        """Φιλτράρει τα εμφανιζόμενα RSS άρθρα βάσει του κειμένου αναζήτησης."""
        if not hasattr(self, 'rss_article_frames') or not hasattr(self, 'rss_checkboxes'):
            return
        search_text = self.rss_search_var.get().lower()

        for frame, article in self.rss_article_frames:
            frame.pack_forget()

        for i, (frame, article) in enumerate(self.rss_article_frames):
            is_selected = self.rss_checkboxes[i][0].get() == 1
            
            # Filter by "Show Selected Only"
            if self.rss_show_selected_only and not is_selected:
                continue

            # Filter by search text
            title = article.get("title", "").lower()
            desc = article.get("description", "").lower()

            if not search_text or search_text in title or search_text in desc:
                frame.pack(fill="x", pady=2, padx=2)

    def _filter_news_ui(self, *args):
        """Φιλτράρει τις πρόσφατες ειδήσεις (DuckDuckGo) βάσει του κειμένου αναζήτησης."""
        if not hasattr(self, 'news_article_frames') or not hasattr(self, 'news_checkboxes'):
            return
        search_text = self.news_search_var.get().lower()

        for frame, article in self.news_article_frames:
            frame.pack_forget()

        for i, (frame, article) in enumerate(self.news_article_frames):
            is_selected = self.news_checkboxes[i][0].get() == 1

            # Filter by "Show Selected Only"
            if self.news_show_selected_only and not is_selected:
                continue

            # Filter by search text
            title = article.get("title", "").lower()
            body = article.get("body", "").lower()

            if not search_text or search_text in title or search_text in body:
                frame.pack(fill="x", pady=2, padx=2)

    def _filter_newsapi_ui(self, *args):
        """Φιλτράρει τις ειδήσεις του NewsAPI βάσει του κειμένου αναζήτησης."""
        if not hasattr(self, 'newsapi_article_frames') or not hasattr(self, 'newsapi_checkboxes'):
            return
        search_text = self.newsapi_search_var.get().lower()

        for frame, article in self.newsapi_article_frames:
            frame.pack_forget()

        for i, (frame, article) in enumerate(self.newsapi_article_frames):
            is_selected = self.newsapi_checkboxes[i][0].get() == 1

            # Filter by "Show Selected Only"
            if self.newsapi_show_selected_only and not is_selected:
                continue

            # Filter by search text
            title = article.get("title", "").lower()
            desc = article.get("description", "").lower()

            if not search_text or search_text in title or search_text in desc:
                frame.pack(fill="x", pady=2, padx=2)

    def on_newsapi_toggle(self):
        if self.newsapi_var.get() == 1:
            self._trigger_newsapi_fetch()
        else:
            for widget in self.newsapi_frame.winfo_children():
                widget.destroy()
            ctk.CTkLabel(self.newsapi_frame, text="Ενεργοποιήστε το NewsAPI αριστερά για προβολή.", text_color="gray").pack(pady=20)
            self.newsapi_checkboxes = []
            self.newsapi_article_frames = []
            if hasattr(self, 'newsapi_search_var'):
                self.newsapi_search_var.set("")

    def _trigger_newsapi_fetch(self):
        self._sync_api_usage()
        stock_name = self.stock_var.get()
        if stock_name in ["Επίλεξε Μετοχή...", "Δεν υπάρχουν μετοχές"]: return
        
        api_key = self.user_data.get("newsapi_key")
        if not api_key:
            self.status_main.configure(text="⚠️ Το API Key του NewsAPI απουσιάζει!", text_color="orange")
            self.newsapi_var.set(0)
            return
        if self.user_data.get("api_usage", {}).get("newsapi", 0) >= 100:
            self.status_main.configure(text="⚠️ Το ημερήσιο όριο NewsAPI εξαντλήθηκε!", text_color="orange")
            self.newsapi_var.set(0)
            return
            
        extra_q = self.newsapi_q_entry.get().strip()
        lang = self.newsapi_lang_entry.get().strip()
        from_date = self.newsapi_date_entry.get().strip()
        
        for widget in self.newsapi_frame.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.newsapi_frame, text="Λήψη δεδομένων NewsAPI...", text_color="orange").pack(pady=20)
        threading.Thread(target=self._fetch_newsapi_thread, args=(stock_name, api_key, extra_q, lang, from_date), daemon=True).start()

    def _fetch_newsapi_thread(self, query, api_key, extra_q, lang, from_date):
        news_data = stock_fetcher.get_newsapi_data(query, api_key, extra_q, lang, from_date)
        self.after(0, self._update_newsapi_ui, news_data)

    def _update_newsapi_ui(self, news_data):
        for widget in self.newsapi_frame.winfo_children():
            widget.destroy()
        self.newsapi_checkboxes = []
        self.newsapi_article_frames = []

        if news_data.get("error"):
            self.status_main.configure(text=f"⚠️ Σφάλμα NewsAPI: {news_data.get('error')}", text_color="orange")
            ctk.CTkLabel(self.newsapi_frame, text=f"Σφάλμα: {news_data.get('error')}", text_color="red").pack(pady=20)
            self.newsapi_var.set(0)
            return
            
        kw = self.newsapi_q_entry.get().strip()
        search_terms = []
        if kw:
            for group in kw.split(','):
                for term in group.split('+'):
                    t = term.strip()
                    if t and t not in search_terms:
                        search_terms.append(t)
        search_terms.sort(key=len, reverse=True)
            
        self.user_data["api_usage"]["newsapi"] = self.user_data.get("api_usage", {}).get("newsapi", 0) + 1
        save_data(self.user_data)
        self._sync_api_usage()

        news_list = news_data.get("news", [])
        if not news_list:
            ctk.CTkLabel(self.newsapi_frame, text="Δεν βρέθηκαν ειδήσεις στο NewsAPI.", text_color="gray").pack(pady=20)
            return

        for article in news_list:
            f = ctk.CTkFrame(self.newsapi_frame, fg_color="#1c1c1c", corner_radius=8, border_width=1, border_color="#333333")
            f.pack(fill="x", pady=4, padx=4)
            
            chk_var = ctk.IntVar(value=0)
            cb = ctk.CTkCheckBox(f, text="", variable=chk_var, width=20, command=self._on_newsapi_chk_toggle)
            cb.pack(side="left", anchor="n", pady=10, padx=10)
            self.newsapi_checkboxes.append((chk_var, article))
            self.newsapi_article_frames.append((f, article))
            
            text_f = ctk.CTkFrame(f, fg_color="transparent")
            text_f.pack(side="left", fill="x", expand=True, pady=10, padx=(0, 10))
            
            title = article.get("title", "Χωρίς Τίτλο")
            desc = article.get("description", "")
            url = article.get("url", "")
            source = article.get("source", "")
            date = article.get("date", "")
            
            title_box = self._create_highlighted_textbox(text_f, self.newsapi_frame, f"📰 {title}", search_terms, ctk.CTkFont(weight="bold", size=12), "#1f77b4", 550, True, url)
            title_box.pack(anchor="w", pady=(0, 2))
                
            ctk.CTkLabel(text_f, text=f"Πηγή: {source} | Ημ/νία: {date}", font=ctk.CTkFont(size=10), text_color="gray", anchor="w").pack(anchor="w")
            
            if desc:
                desc_box = self._create_highlighted_textbox(text_f, self.newsapi_frame, desc, search_terms, ctk.CTkFont(size=11), "white", 550, False, "")
                desc_box.pack(anchor="w", pady=(0, 4))
        self._update_newsapi_selected_count()
                
        self._filter_newsapi_ui()

    def on_time_period_change(self, selected_period):
        current_stock = self.stock_var.get()
        if current_stock not in [self.tr("choose_stock_default"), self.tr("no_stocks_found"), "Επίλεξε Μετοχή...", "Δεν υπάρχουν μετοχές"]:
            self.on_stock_select(current_stock)

    def on_stock_select(self, selected_name):
        if selected_name in [self.tr("choose_stock_default"), self.tr("no_stocks_found"), "Επίλεξε Μετοχή...", "Δεν υπάρχουν μετοχές"]:
            return
            
        stock_data = next((item for item in self.user_data.get("watchlist", []) if item.get("Ονομασία") == selected_name), None)
        if not stock_data:
            return

        self.l_yahoo.configure(text="Φόρτωση...")
        self.l_ft.configure(text="Φόρτωση...")
        self.l_inv.configure(text="Φόρτωση...")
        
        labels_to_reset = [
            self.l_mcap, self.l_pe, self.l_div, self.l_beta,
            self.l_rsi, self.l_macd, self.l_sma20, self.l_sma50,
            self.l_rev_growth, self.l_roe, self.l_op_margin, self.l_dte, self.l_fcf
        ]
        for lbl in labels_to_reset:
            lbl.configure(text="---")
            
        for widget in self.chart_inner_frame.winfo_children():
            widget.destroy()
        self.chart_lbl = ctk.CTkLabel(self.chart_inner_frame, text="Λήψη δεδομένων...\nΤο γράφημα θα εμφανιστεί σύντομα.", text_color="orange")
        self.chart_lbl.pack(fill="both", expand=True, pady=40)
        self.current_df = None

        self.overview_title.configure(text=f"{selected_name} - {self.tr('overview_short')}")
        self.website_url = ""
        self.website_link_label.pack_forget()
        self.website_cb.pack_forget()

        threading.Thread(target=self._fetch_overview_data_thread, args=(stock_data,), daemon=True).start()

        if self.av_var.get() == 1:
            self._trigger_av_fetch()
        if self.fh_var.get() == 1:
            self._trigger_fh_fetch()
        if hasattr(self, 'newsapi_var') and self.newsapi_var.get() == 1:
            self._trigger_newsapi_fetch()
        elif hasattr(self, 'newsapi_frame'):
            for widget in self.newsapi_frame.winfo_children():
                widget.destroy()
            ctk.CTkLabel(self.newsapi_frame, text="Ενεργοποιήστε το NewsAPI αριστερά για προβολή.", text_color="gray").pack(pady=20)
            self.newsapi_checkboxes = []
            self.newsapi_article_frames = []
            if hasattr(self, 'newsapi_search_var'):
                self.newsapi_search_var.set("")

    def _fetch_overview_data_thread(self, stock_data):
        yahoo_sym = stock_data.get("Yahoo")
        ft_sym = stock_data.get("FT")
        inv_sym = stock_data.get("Investing")
        period = self.time_var.get()
        
        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            future_yahoo = executor.submit(stock_fetcher.get_stock_data, yahoo_sym, period) if yahoo_sym else None
            future_ft = executor.submit(stock_fetcher.get_ft_price, ft_sym) if ft_sym else None
            future_inv = executor.submit(stock_fetcher.get_investing_price, inv_sym) if inv_sym else None
            
            # Ανάκτηση ειδήσεων
            symbols_list = [yahoo_sym, ft_sym, inv_sym]
            future_news = executor.submit(stock_fetcher.get_stock_news, stock_data.get("Ονομασία", yahoo_sym), symbols_list)
            
            # Ανάκτηση δεδομένων RSS
            rss_urls = []
            scrape_urls = []
            if hasattr(self, 'url_rows'):
                for row in self.url_rows:
                    if row["chk"].get() == 1:
                        typ = row["type"].get()
                        u_val = row["url"].get().strip()
                        if u_val:
                            if typ == "RSS": rss_urls.append(u_val)
                            elif typ == "Scraping": scrape_urls.append(u_val)
            
            future_rss = None
            if rss_urls or scrape_urls:
                kw = self.rss_keyword_entry.get().strip()
                t_val = self.rss_time_var.get()
                days_map = {"24 Ώρες": 1, "3 Ημέρες": 3, "7 Ημέρες": 7}
                
                try: scrape_limit = int(self.scrape_articles_var.get())
                except ValueError: scrape_limit = 10
                try: scrape_chars = int(self.scrape_chars_var.get())
                except ValueError: scrape_chars = 250
                
                def fetch_both():
                    res = []
                    if rss_urls: res.extend(stock_fetcher.get_rss_news(rss_urls, keyword=kw, days_limit=days_map.get(t_val)))
                    if scrape_urls: res.extend(stock_fetcher.get_scraped_articles(scrape_urls, keyword=kw, limit=scrape_limit, char_limit=scrape_chars))
                    res.sort(key=lambda x: x.get("date", ""), reverse=True)
                    return res
                    
                future_rss = executor.submit(fetch_both)
                
            res_yahoo = future_yahoo.result() if future_yahoo else {"error": "No Yahoo Symbol"}
            ft_price = future_ft.result() if future_ft else "N/A"
            inv_price = future_inv.result() if future_inv else "N/A"
            news_data = future_news.result()
            rss_data = future_rss.result() if future_rss else []

        self.after(0, self._update_overview_ui, res_yahoo, ft_price, inv_price, news_data, rss_data)

    def _update_overview_ui(self, res_yahoo, ft_price, inv_price, news_data=None, rss_data=None):
        quote_type = res_yahoo.get("quote_type")
        is_index = (quote_type == 'INDEX')

        # Απενεργοποίηση των on-demand APIs για δείκτες, καθώς δεν υποστηρίζονται
        if is_index:
            self.cb_av.configure(state="disabled")
            self.cb_fh.configure(state="disabled")
            if self.av_var.get() == 1: self.av_var.set(0); self.on_av_toggle()
            if self.fh_var.get() == 1: self.fh_var.set(0); self.on_fh_toggle()
        else:
            self.cb_av.configure(state="normal")
            self.cb_fh.configure(state="normal")

        if not res_yahoo.get("error"):
            self.l_yahoo.configure(text=res_yahoo.get("price", "N/A"))
            self.l_mcap.configure(text=res_yahoo.get("mcap", "N/A"))
            self.l_pe.configure(text=res_yahoo.get("pe", "N/A"))
            self.l_div.configure(text=res_yahoo.get("div", "N/A"))
            self.l_beta.configure(text=res_yahoo.get("beta", "N/A"))
            self.l_rsi.configure(text=res_yahoo.get("rsi", "N/A"))
            self.l_macd.configure(text=res_yahoo.get("macd", "N/A"))
            self.l_sma20.configure(text=res_yahoo.get("sma20", "N/A"))
            self.l_sma50.configure(text=res_yahoo.get("sma50", "N/A"))
            # Αυτά τα πεδία είναι N/A για ETFs/Indices, οπότε η ενημέρωση είναι ασφαλής
            self.l_rev_growth.configure(text=res_yahoo.get("rev_growth", "N/A")); self.l_roe.configure(text=res_yahoo.get("roe", "N/A")); self.l_op_margin.configure(text=res_yahoo.get("op_margin", "N/A")); self.l_dte.configure(text=res_yahoo.get("dte", "N/A")); self.l_fcf.configure(text=res_yahoo.get("fcf", "N/A"))
            if "df" in res_yahoo:
                self.draw_chart(res_yahoo["df"])
                
            self.website_url = res_yahoo.get("website", "")
            domain_text = res_yahoo.get('domain', '')
            
            if self.website_url: # Για μετοχές
                self.website_link_label.configure(text=f"🔗 {domain_text or 'Website'}", cursor="hand2")
                self.website_link_label.bind("<Button-1>", lambda e: webbrowser.open(self.website_url) if self.website_url else None)
                self.website_link_label.pack(side="left", padx=(20, 10))
                self.website_cb.pack(side="left")
            else:
                if domain_text: # Για ETFs (fundFamily) ή αν δεν υπάρχει URL
                    self.website_link_label.configure(text=f"🏛️ {domain_text}", cursor="arrow")
                    self.website_link_label.unbind("<Button-1>")
                    self.website_link_label.pack(side="left", padx=(20, 10))
                else: # Για δείκτες
                    self.website_link_label.pack_forget()
                self.website_cb.pack_forget() # Κρύβουμε το checkbox αν δεν υπάρχει link
        else:
            self.l_yahoo.configure(text="Σφάλμα")
            self.website_link_label.pack_forget()
            self.website_cb.pack_forget()
            for widget in self.chart_inner_frame.winfo_children():
                widget.destroy()
            ctk.CTkLabel(self.chart_inner_frame, text="⚠️ Σφάλμα λήψης γραφήματος.", text_color="red").pack(fill="both", expand=True, pady=40)
            
        self.l_ft.configure(text=ft_price)
        self.l_inv.configure(text=inv_price)

        selected_name = self.stock_var.get()
        current_stock_data = next((item for item in self.user_data.get("watchlist", []) if item.get("Ονομασία") == selected_name), None)
        notes_text = current_stock_data.get("Notes", "") if current_stock_data else ""

        if notes_text:
            self.notes_frame.pack(fill="x", pady=5, after=self.stats_container)
            self.notes_display_box.configure(state="normal")
            self.notes_display_box.delete("1.0", "end")
            self.notes_display_box.insert("1.0", notes_text)
            self.notes_display_box.configure(state="disabled")
        else:
            self.notes_frame.pack_forget()
        
        # Ενημέρωση Ειδήσεων
        for widget in self.news_frame.winfo_children():
            widget.destroy()

        self.news_checkboxes = []
        self.news_article_frames = []
        if hasattr(self, 'news_search_var'):
            self.news_search_var.set("")

        if not news_data:
            ctk.CTkLabel(self.news_frame, text="Δεν βρέθηκαν πρόσφατες ειδήσεις.", text_color="gray").pack(pady=20)
        else:
            for article in news_data:
                f = ctk.CTkFrame(self.news_frame, fg_color="#1c1c1c", corner_radius=8, border_width=1, border_color="#333333")
                f.pack(fill="x", pady=4, padx=4)
                
                chk_var = ctk.IntVar(value=0)
                cb = ctk.CTkCheckBox(f, text="", variable=chk_var, width=20, command=self._on_news_chk_toggle)
                cb.pack(side="left", anchor="n", pady=10, padx=10)
                self.news_checkboxes.append((chk_var, article))
                self.news_article_frames.append((f, article))
                
                text_f = ctk.CTkFrame(f, fg_color="transparent")
                text_f.pack(side="left", fill="x", expand=True, pady=10, padx=(0, 10))
                
                title = article.get("title", "Χωρίς Τίτλο")
                url = article.get("url", "")
                source = article.get("source", "")
                date = article.get("date", "")[:10]
                
                title_lbl = ctk.CTkLabel(text_f, text=f"📰 {title}", font=ctk.CTkFont(weight="bold", size=12), text_color="#1f77b4", cursor="hand2", anchor="w", justify="left", wraplength=550)
                title_lbl.pack(anchor="w")
                if url:
                    title_lbl.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
                    
                ctk.CTkLabel(text_f, text=f"Πηγή: {source} | Ημ/νία: {date}", font=ctk.CTkFont(size=10), text_color="gray", anchor="w").pack(anchor="w")
                
                body = article.get("body", "")
                if body:
                    ctk.CTkLabel(text_f, text=body, font=ctk.CTkFont(size=11), anchor="w", justify="left", wraplength=550).pack(anchor="w", pady=(0, 4))

        self._filter_news_ui()
        self._update_news_selected_count()

        # Ενημέρωση Σελίδων Μετοχής
        for widget in self.pages_frame.winfo_children():
            widget.destroy()
        self.page_checkboxes = []
            
        selected_name = self.stock_var.get()
        stock_data = next((item for item in self.user_data.get("watchlist", []) if item.get("Ονομασία") == selected_name), {})
        y_sym = stock_data.get("Yahoo", "")
        ft_sym = stock_data.get("FT", "")
        inv_sym = stock_data.get("Investing", "")
        
        if y_sym or ft_sym or inv_sym:
            ctk.CTkLabel(self.pages_frame, text=f"Απευθείας σύνδεσμοι για {selected_name}:", font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", pady=(0, 5))
            ctk.CTkLabel(self.pages_frame, text="Τσεκάρετε το κουτάκι αριστερά για να διαβάσει το AI την αντίστοιχη σελίδα.", font=ctk.CTkFont(size=11, slant="italic"), text_color="gray").pack(anchor="w", pady=(0, 15))
            
            if y_sym and y_sym != "N/A":
                y_url = f"https://finance.yahoo.com/quote/{y_sym}/"
                row_f = ctk.CTkFrame(self.pages_frame, fg_color="transparent")
                row_f.pack(anchor="w", pady=5)
                c_var = ctk.IntVar(value=0)
                ctk.CTkCheckBox(row_f, text="", variable=c_var, width=20).pack(side="left", padx=(0, 5))
                y_btn = ctk.CTkButton(row_f, text="🟣 Yahoo Finance", fg_color="#720e9e", hover_color="#5a0b7d", font=ctk.CTkFont(weight="bold"), command=lambda u=y_url: webbrowser.open(u))
                y_btn.pack(side="left")
                self.page_checkboxes.append((c_var, "Yahoo Finance", y_url))
                
            if ft_sym and ft_sym != "N/A":
                ft_url = ft_sym if ft_sym.startswith("http") else f"https://markets.ft.com/data/equities/tearsheet/summary?s={ft_sym}"
                row_f = ctk.CTkFrame(self.pages_frame, fg_color="transparent")
                row_f.pack(anchor="w", pady=5)
                c_var = ctk.IntVar(value=0)
                ctk.CTkCheckBox(row_f, text="", variable=c_var, width=20).pack(side="left", padx=(0, 5))
                ft_btn = ctk.CTkButton(row_f, text="🟠 Financial Times", fg_color="#ff9933", text_color="black", hover_color="#cc7a29", font=ctk.CTkFont(weight="bold"), command=lambda u=ft_url: webbrowser.open(u))
                ft_btn.pack(side="left")
                self.page_checkboxes.append((c_var, "Financial Times", ft_url))
                
            if inv_sym and inv_sym != "N/A":
                if inv_sym.startswith("http"): i_url = inv_sym
                elif "/" in inv_sym: i_url = f"https://gr.investing.com/{inv_sym}"
                else: i_url = f"https://gr.investing.com/equities/{inv_sym}"
                row_f = ctk.CTkFrame(self.pages_frame, fg_color="transparent")
                row_f.pack(anchor="w", pady=5)
                c_var = ctk.IntVar(value=0)
                ctk.CTkCheckBox(row_f, text="", variable=c_var, width=20).pack(side="left", padx=(0, 5))
                inv_btn = ctk.CTkButton(row_f, text="⚫ Investing.com", fg_color="#1c1c1c", hover_color="#2b2b2b", border_width=1, border_color="gray", font=ctk.CTkFont(weight="bold"), command=lambda u=i_url: webbrowser.open(u))
                inv_btn.pack(side="left")
                self.page_checkboxes.append((c_var, "Investing.com", i_url))
        else:
            ctk.CTkLabel(self.pages_frame, text="Δεν υπάρχουν αποθηκευμένα σύμβολα για αυτή τη μετοχή.", text_color="gray").pack(pady=20)
            
        # Ενημέρωση RSS Feeds
        self.rss_show_selected_only = False # Reset this when new data is loaded
        self._update_rss_ui(rss_data)

    def fetch_data(self):
        """Συλλέγει όλα τα επιλεγμένα δεδομένα (API, URLs, Αρχεία) και ξεκινά την ανάλυση AI."""
        selected_name = self.stock_var.get()
        if selected_name in [self.tr("choose_stock_default"), "Επίλεξε Μετοχή..."]:
            self.status_main.configure(text="Επίλεξε μια μετοχή πρώτα!", text_color="red")
            return
            
        stock_data = next((item for item in self.user_data.get("watchlist", []) if item.get("Ονομασία") == selected_name), None)
        if not stock_data or not stock_data.get("Yahoo"):
            self.status_main.configure(text="Σφάλμα: Δεν βρέθηκε σύμβολο Yahoo.", text_color="red")
            return

        symbol = stock_data["Yahoo"]
        period = self.time_var.get()
        
        selected_news_count = sum(1 for chk, _ in getattr(self, 'news_checkboxes', []) if chk.get() == 1)
        selected_rss_count = sum(1 for chk, _ in getattr(self, 'rss_checkboxes', []) if chk.get() == 1)
        selected_newsapi_count = sum(1 for chk, _ in getattr(self, 'newsapi_checkboxes', []) if chk.get() == 1)
        pasted_articles_count = sum(1 for box in getattr(self, 'article_boxes', []) if box.get("1.0", "end-1c").strip())
        attached_files_count = len(getattr(self, 'attached_files', []))
        
        if (selected_news_count + selected_rss_count + selected_newsapi_count + pasted_articles_count + attached_files_count) == 0:
            if not messagebox.askyesno(self.tr("no_articles_title"), self.tr("no_articles_msg")):
                self.status_main.configure(text=self.tr("analysis_cancelled"), text_color="orange")
                return

        self.status_main.configure(text="Ανάκτηση δεδομένων & υπολογισμός δεικτών...", text_color="orange")
        self.result_textbox.delete("0.0", "end")
        self.update()

        result = stock_fetcher.get_stock_data(symbol, period)
        
        if result.get("error"):
            self.status_main.configure(text=f"❌ {result['error']}", text_color="red")
            return
            
        self.l_yahoo.configure(text=result["price"])
        self.l_mcap.configure(text=result["mcap"])
        self.l_pe.configure(text=result["pe"])
        self.l_div.configure(text=result["div"])
        self.l_beta.configure(text=result["beta"])
        self.l_rsi.configure(text=result["rsi"])
        self.l_macd.configure(text=result["macd"])
        self.l_sma20.configure(text=result["sma20"])
        self.l_sma50.configure(text=result["sma50"])
        self.l_rev_growth.configure(text=result.get("rev_growth", "N/A"))
        self.l_roe.configure(text=result.get("roe", "N/A"))
        self.l_op_margin.configure(text=result.get("op_margin", "N/A"))
        self.l_dte.configure(text=result.get("dte", "N/A"))
        self.l_fcf.configure(text=result.get("fcf", "N/A"))
        if "df" in result:
            self.draw_chart(result["df"])
        
        context = result["context"]
        
        # Προσθήκη επιλεγμένων ειδήσεων
        selected_news = []
        used_sources = []
        if hasattr(self, 'news_checkboxes'):
            for chk_var, article in self.news_checkboxes:
                if chk_var.get() == 1:
                    title = " ".join(article.get('title', '').split())
                    body = " ".join(article.get('body', '').split())
                    news_url = article.get('url', '')
                    selected_news.append(f"• {title}: {body}")
                    used_sources.append(f"Είδηση: {title}" + (f" ({news_url})" if news_url else ""))
                    
        if selected_news:
            context += "\n\n[ΠΡΟΣΦΑΤΕΣ ΕΙΔΗΣΕΙΣ DUCKDUCKGO]\n" + "\n".join(selected_news)

        # Δεδομένα Alpha Vantage
        if self.av_var.get() == 1 and getattr(self, 'current_av_context', ""):
            context += self.current_av_context

        # Δεδομένα Finnhub
        if self.fh_var.get() == 1 and getattr(self, 'current_fh_context', ""):
            context += self.current_fh_context

        # Δεδομένα NewsAPI
        if hasattr(self, 'newsapi_var') and self.newsapi_var.get() == 1 and hasattr(self, 'newsapi_checkboxes'):
            newsapi_selected = []
            for chk_var, article in self.newsapi_checkboxes:
                if chk_var.get() == 1:
                    title = " ".join(article.get('title', '').split())
                    desc = article.get('description', '')
                    content = " ".join(desc.split()) if desc else ""
                    
                    n_url = article.get('url', '')
                    newsapi_selected.append(f"• {title}: {content}")
                    used_sources.append(f"NewsAPI Είδηση: {title}" + (f" ({n_url})" if n_url else ""))
            if newsapi_selected:
                context += "\n\n[NEWSAPI.ORG - ΕΙΔΗΣΕΙΣ]\n" + "\n".join(newsapi_selected)

        # Ανάγνωση επιλεγμένων Custom URLs & Εταιρικού Site
        selected_urls = []
        
        comp_website = result.get("website", "")
        if hasattr(self, 'website_var') and self.website_var.get() == 1 and comp_website:
            self.status_main.configure(text=f"Ανάγνωση εταιρικού site: {comp_website}...", text_color="orange")
            self.update()
            scraped_site = stock_fetcher.scrape_url_text(comp_website)
            if scraped_site:
                selected_urls.append(f"• Πηγή: Εταιρικό Site\nΚείμενο: {scraped_site}")
                used_sources.append(f"Εταιρικό Site: {comp_website}")
                
        if hasattr(self, 'url_rows'):
            for row in self.url_rows:
                if row["chk"].get() == 1 and row["type"].get() == "URL":
                    t_val = row["title"].get().strip()
                    u_val = row["url"].get().strip()
                    if u_val:
                        self.status_main.configure(text=f"Ανάγνωση: {t_val or u_val}...", text_color="orange")
                        self.update()
                        scraped_text = stock_fetcher.scrape_url_text(u_val)
                        if scraped_text:
                            selected_urls.append(f"• Πηγή: {t_val}\nΚείμενο: {scraped_text}")
                            used_sources.append(f"Άρθρο: {t_val or 'Custom URL'} ({u_val})")
                            
        if hasattr(self, 'page_checkboxes'):
            for chk_var, p_title, p_url in self.page_checkboxes:
                if chk_var.get() == 1:
                    self.status_main.configure(text=f"Ανάγνωση: {p_title}...", text_color="orange")
                    self.update()
                    scraped_text = stock_fetcher.scrape_url_text(p_url)
                    if scraped_text:
                        selected_urls.append(f"• Πηγή: Σελίδα Μετοχής ({p_title})\nΚείμενο: {scraped_text}")
                        used_sources.append(f"Σελίδα Μετοχής: {p_title} ({p_url})")
                            
        if selected_urls:
            context += "\n\n[ΕΠΙΠΛΕΟΝ ΠΗΓΕΣ (WEB SCRAPING)]\n" + "\n\n".join(selected_urls)
            
        # Προσθήκη επιλεγμένων άρθρων RSS
        if hasattr(self, 'rss_checkboxes'):
            rss_selected = []
            for chk_var, article in self.rss_checkboxes:
                if chk_var.get() == 1:
                    title = " ".join(article.get('title', '').split())
                    desc = article.get('description', '')
                    content = " ".join(desc.split()) if desc else ""
                    
                    r_url = article.get('url', '')
                    rss_selected.append(f"• {title}: {content}")
                    used_sources.append(f"RSS/Scraped: {title}" + (f" ({r_url})" if r_url else ""))
            if rss_selected:
                context += "\n\n[ΕΠΙΛΕΓΜΕΝΑ ΑΡΘΡΑ ΑΠΟ RSS & WEB SCRAPING]\n" + "\n".join(rss_selected)

        # Προσθήκη χειροκίνητων άρθρων
        if hasattr(self, 'article_boxes'):
            for i, box in enumerate(self.article_boxes):
                art_text = box.get("1.0", "end-1c").strip()
                if art_text:
                    art_text = " ".join(art_text.split())
                    context += f"\n\n[ΕΠΙΚΟΛΛΗΜΕΝΟ ΑΡΘΡΟ {i+1}]\n{art_text}"
                    used_sources.append(f"Επικολλημένο Άρθρο {i+1}")

        # Προσθήκη αρχείων TXT/PDF
        if getattr(self, 'attached_files', []):
            import PyPDF2
            for fpath in self.attached_files:
                try:
                    fname = os.path.basename(fpath)
                    self.status_main.configure(text=f"Ανάγνωση αρχείου: {fname}...", text_color="orange")
                    self.update()
                    text = ""
                    if fpath.lower().endswith('.pdf'):
                        with open(fpath, "rb") as f:
                            reader = PyPDF2.PdfReader(f)
                            for page in reader.pages:
                                ext = page.extract_text()
                                if ext: text += ext + "\n"
                    else:
                        with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                            text = f.read()
                            
                    if text.strip():
                        text = " ".join(text.split())
                        context += f"\n\n[ΠΕΡΙΕΧΟΜΕΝΟ ΑΡΧΕΙΟΥ: {fname}]\n{text}"
                        used_sources.append(f"Αρχείο: {fname}")
                except Exception as e:
                    logger.error(f"Error reading file {fpath}: {e}")
                    self.status_main.configure(text=f"⚠️ Σφάλμα ανάγνωσης {fname}", text_color="orange")
                    self.update()

        self.status_main.configure(text="Επικοινωνία με το AI...", text_color="orange")
        self.overview_title.configure(text=f"{selected_name} - {self.tr('overview_short')}")
        self.update()
        
        user_extra_prompt = self.extra_prompt_box.get("1.0", "end-1c").strip()
        analysis_format = self.format_var.get()
        
        common_table_instructions = self.tr("prompt_common_table")
        
        if analysis_format == 'Συνοπτικά':
            format_instructions = self.tr("prompt_summary") + common_table_instructions + self.tr("prompt_summary_points")
        else:
            format_instructions = self.tr("prompt_detailed") + common_table_instructions + self.tr("prompt_detailed_points")
        
        final_extra_prompt = format_instructions
        if user_extra_prompt:
            final_extra_prompt += self.tr("prompt_user_extra") + user_extra_prompt

        # Ενημέρωση του AI Info Label
        total_chars = len(context) + len(final_extra_prompt) + 150  # +150 για το σταθερό κείμενο του prompt
        provider = self.ai_provider_menu.get()
        model = self.ai_model_var.get()
        info_text = f"🤖 AI: {provider} ({model}) | Characters: {total_chars:,}" if self.user_data.get("language") == "en" else f"🤖 AI: {provider} ({model}) | Χαρακτήρες: {total_chars:,}"
        self.ai_info_label.configure(text=info_text)
        
        if total_chars > 30000:
            warn_title = "Large Context Warning" if self.user_data.get("language") == "en" else "Προειδοποίηση Μεγάλου Κειμένου"
            warn_msg = f"The text to be analyzed is very large ({total_chars:,} characters) and may exceed the AI model's limits or consume many tokens.\n\nDo you want to proceed anyway?" if self.user_data.get("language") == "en" else f"Το κείμενο προς ανάλυση είναι πολύ μεγάλο ({total_chars:,} χαρακτήρες) και ενδέχεται να ξεπεράσει τα όρια του μοντέλου ή να καταναλώσει πολλά tokens.\n\nΘέλετε να συνεχίσετε οπωσδήποτε;"
            if not messagebox.askyesno(warn_title, warn_msg):
                self.status_main.configure(text=self.tr("analysis_cancelled"), text_color="orange")
                return

        # Εκτέλεση του AI σε ξεχωριστό Thread
        threading.Thread(target=self.run_ai, args=(selected_name, context, used_sources, final_extra_prompt), daemon=True).start()

    def draw_chart(self, df):
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
        from matplotlib.figure import Figure
        import matplotlib.dates as mdates
        from matplotlib.widgets import MultiCursor

        self.current_df = df
        # Καθαρισμός προηγούμενου γραφήματος
        for widget in self.chart_inner_frame.winfo_children():
            widget.destroy()

        fig = Figure(figsize=(8, 7), dpi=100, facecolor='#2b2b2b')
        axes = fig.subplots(nrows=4, ncols=1, sharex=True, gridspec_kw={'height_ratios': [0.5, 3, 1, 1]})
        ax0, ax1, ax2, ax3 = axes
        
        for ax in axes:
            ax.set_facecolor('#2b2b2b')
            ax.tick_params(axis='x', colors='white')
            ax.tick_params(axis='y', colors='white')
            for spine in ax.spines.values():
                spine.set_color('gray')

        up = df[df['Close'] >= df['Open']]
        down = df[df['Close'] < df['Open']]
        width = 0.6 if len(df) < 100 else 0.4
        width2 = 0.1 if len(df) < 100 else 0.05

        x_vals = mdates.date2num(df.index)
        up_idx = mdates.date2num(up.index)
        down_idx = mdates.date2num(down.index)

        # Ειδικό, μικρό γράφημα στην κορυφή ΜΟΝΟ για το Hover
        ax0.plot(x_vals, df['Close'].values, color='#1f77b4', linewidth=1.5, alpha=0.8)
        ax0.set_yticks([]) # Κρύβουμε τις τιμές Y για να είναι καθαρό
        ax0.set_title("⬇️ Περάστε το ποντίκι από αυτή τη μπλε γραμμή για να δείτε τις τιμές ⬇️", fontsize=9, color='gray')

        ax1.bar(up_idx, (up['Close'] - up['Open']).values, width, bottom=up['Open'].values, color='#2ca02c')
        ax1.bar(up_idx, (up['High'] - up['Low']).values, width2, bottom=up['Low'].values, color='#2ca02c')
        ax1.bar(down_idx, (down['Close'] - down['Open']).values, width, bottom=down['Open'].values, color='#d9534f')
        ax1.bar(down_idx, (down['High'] - down['Low']).values, width2, bottom=down['Low'].values, color='#d9534f')
        
        if hasattr(self, 'show_sma_var') and self.show_sma_var.get() == 1:
            if 'SMA_20' in df.columns: ax1.plot(x_vals, df['SMA_20'].values, color='#1f77b4', label='SMA 20', linewidth=1.2)
            if 'SMA_50' in df.columns: ax1.plot(x_vals, df['SMA_50'].values, color='#ff7f0e', label='SMA 50', linewidth=1.2)
            
        if hasattr(self, 'show_ema_var') and self.show_ema_var.get() == 1:
            if 'EMA_20' in df.columns: ax1.plot(x_vals, df['EMA_20'].values, color='#e377c2', label='EMA 20', linewidth=1.2, linestyle='--')
            if 'EMA_50' in df.columns: ax1.plot(x_vals, df['EMA_50'].values, color='#8c564b', label='EMA 50', linewidth=1.2, linestyle='--')
            
        ax1.legend(facecolor='#2b2b2b', labelcolor='white', loc='upper left')
        
        # Σκληρή επιβολή ορίων στον άξονα Υ (αποτρέπει το μηδενισμό της κλίμακας από τη χρήση των bar)
        min_p = df['Low'].min()
        max_p = df['High'].max()
        pad = (max_p - min_p) * 0.05 if max_p != min_p else min_p * 0.05
        ax1.set_ylim(min_p - pad, max_p + pad)

        if 'Volume' in df.columns:
            ax2.bar(up_idx, up['Volume'].values, width=width, color='#2ca02c', alpha=0.7)
            ax2.bar(down_idx, down['Volume'].values, width=width, color='#d9534f', alpha=0.7)
        ax2.set_ylabel('Όγκος', color='white')
            
        if 'RSI_14' in df.columns:
            ax3.plot(x_vals, df['RSI_14'].values, color='#9467bd', linewidth=1.2)
            ax3.axhline(70, color='#d9534f', linestyle='--', alpha=0.6)
            ax3.axhline(30, color='#2ca02c', linestyle='--', alpha=0.6)
            ax3.fill_between(x_vals, 70, 30, color='gray', alpha=0.1)
        ax3.set_ylabel('RSI', color='white')
        ax3.set_ylim(0, 100)

        ax3.xaxis_date()
        ax3.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m/%Y'))

        fig.tight_layout()
        fig.autofmt_xdate()

        self.multi_cursor = MultiCursor(fig.canvas, axes, color='white', lw=0.8, ls='--', alpha=0.5, horizOn=False, vertOn=True, useblit=False)
        
        annot = ax0.annotate(
            "", xy=(0,0), xytext=(10, 10), textcoords="offset points",
            bbox=dict(boxstyle="round", fc="#1c1c1c", ec="gray", alpha=0.9),
            color="white", zorder=10, fontsize=9, clip_on=False
        )
        annot.set_visible(False)

        def on_hover(event):
            if not event.inaxes or event.xdata is None or event.ydata is None:
                if annot.get_visible():
                    annot.set_visible(False)
                    fig.canvas.draw_idle()
                return

            x, y = event.xdata, event.ydata
            diffs = [abs(xv - x) for xv in x_vals]
            idx = diffs.index(min(diffs))
            closest_x = x_vals[idx]
            row = df.iloc[idx]

            if event.inaxes == ax0:
                annot.xy = (closest_x, y)
                date_str = df.index[idx].strftime('%d/%m/%Y')
                text = f"Ημ: {date_str} | O: {row['Open']:.2f} | H: {row['High']:.2f} | L: {row['Low']:.2f} | C: {row['Close']:.2f}"
                if 'Volume' in df.columns:
                    text += f" | Vol: {int(row['Volume']):,}"
                annot.set_text(text)
                
                xlim = ax0.get_xlim()
                annot.set_position((-330, 10) if closest_x > (xlim[0] + 0.6 * (xlim[1] - xlim[0])) else (10, 10))
                annot.set_visible(True)
            else:
                annot.set_visible(False)

            fig.canvas.draw_idle()

        fig.canvas.mpl_connect('motion_notify_event', on_hover)

        canvas = FigureCanvasTkAgg(fig, master=self.chart_inner_frame)
        canvas.draw()
        widget = canvas.get_tk_widget()
        widget.pack(fill="both", expand=True)
        
        self.current_fig = fig
        
        # Μετατροπή του δείκτη του ποντικιού σε "χεράκι" και σύνδεση του κλικ
        widget.configure(cursor="hand2")
        fig.canvas.mpl_connect('button_press_event', lambda event: self.show_large_chart(df))

    def show_large_chart(self, df):
        """Ανοίγει το γράφημα σε νέο μεγάλο παράθυρο με εργαλεία περιήγησης."""
        from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
        from matplotlib.figure import Figure
        import matplotlib.dates as mdates
        from matplotlib.widgets import MultiCursor

        top = ctk.CTkToplevel(self)
        top.title(f"Αναλυτικό Γράφημα - {self.stock_var.get()}")
        top.geometry("1200x850")

        fig = Figure(figsize=(12, 8), dpi=100, facecolor='#2b2b2b')
        axes = fig.subplots(nrows=4, ncols=1, sharex=True, gridspec_kw={'height_ratios': [0.5, 3, 1, 1]})
        ax0, ax1, ax2, ax3 = axes
        
        for ax in axes:
            ax.set_facecolor('#2b2b2b')
            ax.tick_params(axis='x', colors='white')
            ax.tick_params(axis='y', colors='white')
            for spine in ax.spines.values():
                spine.set_color('gray')

        up = df[df['Close'] >= df['Open']]
        down = df[df['Close'] < df['Open']]
        width = 0.6 if len(df) < 100 else 0.4
        width2 = 0.1 if len(df) < 100 else 0.05

        x_vals = mdates.date2num(df.index)
        up_idx = mdates.date2num(up.index)
        down_idx = mdates.date2num(down.index)

        ax0.plot(x_vals, df['Close'].values, color='#1f77b4', linewidth=1.5, alpha=0.8)
        ax0.set_yticks([])
        ax0.set_title("⬇️ Περάστε το ποντίκι από αυτή τη μπλε γραμμή για να δείτε τις τιμές ⬇️", fontsize=10, color='gray')

        ax1.bar(up_idx, (up['Close'] - up['Open']).values, width, bottom=up['Open'].values, color='#2ca02c')
        ax1.bar(up_idx, (up['High'] - up['Low']).values, width2, bottom=up['Low'].values, color='#2ca02c')
        ax1.bar(down_idx, (down['Close'] - down['Open']).values, width, bottom=down['Open'].values, color='#d9534f')
        ax1.bar(down_idx, (down['High'] - down['Low']).values, width2, bottom=down['Low'].values, color='#d9534f')
        
        if hasattr(self, 'show_sma_var') and self.show_sma_var.get() == 1:
            if 'SMA_20' in df.columns: ax1.plot(x_vals, df['SMA_20'].values, color='#1f77b4', label='SMA 20', linewidth=1.2)
            if 'SMA_50' in df.columns: ax1.plot(x_vals, df['SMA_50'].values, color='#ff7f0e', label='SMA 50', linewidth=1.2)
            
        if hasattr(self, 'show_ema_var') and self.show_ema_var.get() == 1:
            if 'EMA_20' in df.columns: ax1.plot(x_vals, df['EMA_20'].values, color='#e377c2', label='EMA 20', linewidth=1.2, linestyle='--')
            if 'EMA_50' in df.columns: ax1.plot(x_vals, df['EMA_50'].values, color='#8c564b', label='EMA 50', linewidth=1.2, linestyle='--')
                
        ax1.legend(facecolor='#2b2b2b', labelcolor='white', loc='upper left')
        
        # Σκληρή επιβολή ορίων στον άξονα Υ (αποτρέπει το μηδενισμό της κλίμακας από τη χρήση των bar)
        min_p = df['Low'].min()
        max_p = df['High'].max()
        pad = (max_p - min_p) * 0.05 if max_p != min_p else min_p * 0.05
        ax1.set_ylim(min_p - pad, max_p + pad)

        if 'Volume' in df.columns:
            ax2.bar(up_idx, up['Volume'].values, width=width, color='#2ca02c', alpha=0.7)
            ax2.bar(down_idx, down['Volume'].values, width=width, color='#d9534f', alpha=0.7)
        ax2.set_ylabel('Όγκος', color='white')
            
        if 'RSI_14' in df.columns:
            ax3.plot(x_vals, df['RSI_14'].values, color='#9467bd', linewidth=1.2)
            ax3.axhline(70, color='#d9534f', linestyle='--', alpha=0.6)
            ax3.axhline(30, color='#2ca02c', linestyle='--', alpha=0.6)
            ax3.fill_between(x_vals, 70, 30, color='gray', alpha=0.1)
        ax3.set_ylabel('RSI', color='white')
        ax3.set_ylim(0, 100)

        ax3.xaxis_date()
        ax3.xaxis.set_major_formatter(mdates.DateFormatter('%d/%m/%Y'))

        fig.tight_layout()
        fig.autofmt_xdate()

        top.multi_cursor = MultiCursor(fig.canvas, axes, color='white', lw=0.8, ls='--', alpha=0.5, horizOn=False, vertOn=True, useblit=False)
        
        annot = ax0.annotate(
            "", xy=(0,0), xytext=(10, 10), textcoords="offset points",
            bbox=dict(boxstyle="round", fc="#1c1c1c", ec="gray", alpha=0.9),
            color="white", zorder=10, fontsize=10, clip_on=False
        )
        annot.set_visible(False)

        def on_hover_large(event):
            if not event.inaxes or event.xdata is None or event.ydata is None:
                if annot.get_visible():
                    annot.set_visible(False)
                    fig.canvas.draw_idle()
                return

            x, y = event.xdata, event.ydata
            diffs = [abs(xv - x) for xv in x_vals]
            idx = diffs.index(min(diffs))
            closest_x = x_vals[idx]
            row = df.iloc[idx]

            if event.inaxes == ax0:
                annot.xy = (closest_x, y)
                date_str = df.index[idx].strftime('%d/%m/%Y')
                text = f"Ημ/νία: {date_str} | Open: {row['Open']:.2f} | High: {row['High']:.2f} | Low: {row['Low']:.2f} | Close: {row['Close']:.2f}"
                if 'Volume' in df.columns:
                    text += f" | Vol: {int(row['Volume']):,}"
                annot.set_text(text)
                
                xlim = ax0.get_xlim()
                annot.set_position((-380, 10) if closest_x > (xlim[0] + 0.7 * (xlim[1] - xlim[0])) else (10, 10))
                annot.set_visible(True)
            else:
                annot.set_visible(False)

            fig.canvas.draw_idle()

        fig.canvas.mpl_connect('motion_notify_event', on_hover_large)

        canvas = FigureCanvasTkAgg(fig, master=top)
        canvas.draw()
        
        toolbar = NavigationToolbar2Tk(canvas, top)
        toolbar.update()
        toolbar.pack(side="bottom", fill="x")
        
        canvas.get_tk_widget().pack(side="top", fill="both", expand=True)

    def run_ai(self, name, context, used_sources=None, extra_prompt=""):
        """Επικοινωνεί με τον πάροχο AI (Gemini ή Ollama) και παράγει την τελική αναφορά."""
        provider = self.ai_provider_menu.get()
        selected_model = self.ai_model_var.get()
        temperature = self.temperature_slider.get()

        if not selected_model or selected_model in ["Φόρτωση...", "Απαιτείται API Key", "Κανένα διαθέσιμο μοντέλο", "Σφάλμα φόρτωσης"]:
            self.after(0, self.update_ai_result, "❌ Παρακαλώ επιλέξτε ένα έγκυρο μοντέλο AI.", "red")
            return

        if provider == "Gemini (Cloud)":
            api_key = self.user_data.get("api_key")
        elif provider == "Ollama (Cloud)":
            api_key = self.user_data.get("ollama_cloud_key")
        else:
            api_key = None
            
        lang = self.user_data.get("language", "el")
        result, error = ai_service.generate_analysis(provider, selected_model, name, context, api_key, temperature, extra_prompt, lang)
        
        if error:
            self.after(0, self.update_ai_result, error, "red")
        else:
            date_str = datetime.datetime.now().strftime("%d/%m/%Y")
            final_text = f"{self.tr('analysis_date')}{date_str}\n\n{result}"
            
            if used_sources:
                sources_text = self.tr("sources_used") + "\n".join(f"- {s}" for s in used_sources)
                final_text += sources_text
            self.after(0, self.update_ai_result, final_text, "green")

    def update_ai_result(self, text, status_color):
        self.result_textbox.insert("1.0", text)
        stock_name = self.stock_var.get()
        self.current_analysis_stock = stock_name
        if status_color == "green":
            msg = "✅ Η ανάλυση ολοκληρώθηκε!"
            history = self.user_data.get("history", [])
            stock_name = self.stock_var.get()
            date_str = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
            
            history.append({"stock": stock_name, "date": date_str, "text": text})
            if len(history) > 10:
                history = history[-10:]
                
            self.user_data["history"] = history
            save_data(self.user_data)
            self.update_history_ui()
        else:
            msg = "Αποτυχία Ανάλυσης AI"
        self.status_main.configure(text=msg, text_color=status_color)

    def _prepare_export_data(self):
        """Βοηθητική μέθοδος για συγκέντρωση δεδομένων προς εξαγωγή (Word/PDF)."""
        text = self.result_textbox.get("1.0", "end-1c").strip()
        if not text:
            return None, None, None, None, None

        stock_name = getattr(self, 'current_analysis_stock', self.stock_var.get())
        if not stock_name or stock_name in [self.tr("choose_stock_default"), "Επίλεξε Μετοχή..."]:
            stock_name = "Άγνωστη_Μετοχή"

        chart_path = None
        if hasattr(self, 'current_fig') and self.current_fig is not None:
            try:
                import tempfile
                import os
                fd, chart_path = tempfile.mkstemp(suffix=".png")
                os.close(fd)
                
                # --- Μετατροπή σε φωτεινό (λευκό) θέμα για την εξαγωγή ---
                original_facecolor = self.current_fig.get_facecolor()
                self.current_fig.set_facecolor('white')
                for ax in self.current_fig.axes:
                    ax.set_facecolor('white')
                    ax.tick_params(axis='x', colors='black')
                    ax.tick_params(axis='y', colors='black')
                    ax.xaxis.label.set_color('black')
                    ax.yaxis.label.set_color('black')
                    if ax.get_title(): ax.title.set_color('black')
                    for spine in ax.spines.values():
                        spine.set_color('black')
                    legend = ax.get_legend()
                    if legend:
                        legend.get_frame().set_facecolor('white')
                        for leg_text in legend.get_texts():
                            leg_text.set_color('black')

                # Αποθήκευση με λευκό φόντο στο αρχείο
                self.current_fig.savefig(chart_path, format='png', facecolor='white', bbox_inches='tight')
                
                # --- Επαναφορά στο σκοτεινό θέμα της εφαρμογής ---
                self.current_fig.set_facecolor(original_facecolor)
                for ax in self.current_fig.axes:
                    ax.set_facecolor('#2b2b2b')
                    ax.tick_params(axis='x', colors='white')
                    ax.tick_params(axis='y', colors='white')
                    ax.xaxis.label.set_color('white')
                    ax.yaxis.label.set_color('white')
                    if ax.get_title(): ax.title.set_color('gray')
                    for spine in ax.spines.values():
                        spine.set_color('gray')
                    legend = ax.get_legend()
                    if legend:
                        legend.get_frame().set_facecolor('#2b2b2b')
                        for leg_text in legend.get_texts():
                            leg_text.set_color('white')
                self.current_fig.canvas.draw_idle()
                
            except Exception as e:
                logger.error(f"Σφάλμα αποθήκευσης γραφήματος: {e}")
                chart_path = None

        prices_dict = {
            "Yahoo Finance": self.l_yahoo.cget("text"),
            "Financial Times": self.l_ft.cget("text"),
            "Investing.com": self.l_inv.cget("text")
        }

        stats_dict = {
            "Market Cap": self.l_mcap.cget("text"),
            "P/E Ratio": self.l_pe.cget("text"),
            "Dividend Yield": self.l_div.cget("text"),
            "Beta": self.l_beta.cget("text"),
            "Revenue Growth": self.l_rev_growth.cget("text"),
            "Return on Equity (ROE)": self.l_roe.cget("text"),
            "Operating Margin": self.l_op_margin.cget("text"),
            "Debt/Equity": self.l_dte.cget("text"),
            "Free Cash Flow": self.l_fcf.cget("text")
        }
        return text, stock_name, chart_path, prices_dict, stats_dict

    def export_to_word(self):
        """Εξάγει το κείμενο της παραγόμενης ανάλυσης σε αρχείο μορφής MS Word (.docx)."""
        text, stock_name, chart_path, prices_dict, stats_dict = self._prepare_export_data()
        if not text:
            self.status_main.configure(text="❌ Δεν υπάρχει κείμενο για εξαγωγή!", text_color="red")
            return
            
        import re
        import os
        safe_stock_name = re.sub(r'[\\/*?:"<>|]', "", stock_name).replace(' ', '_')

        file_path = filedialog.asksaveasfilename(
            defaultextension=".docx",
            filetypes=[("Word Document", "*.docx")],
            title="Αποθήκευση Ανάλυσης",
            initialfile=f"Ανάλυση_{safe_stock_name}.docx"
        )

        if file_path:
            success, error = document_exporter.save_to_word(text, stock_name, file_path, chart_image=chart_path, prices=prices_dict, stats=stats_dict)
            if success:
                self.status_main.configure(text="✅ Εξήχθη επιτυχώς σε Word!", text_color="green")
            else:
                self.status_main.configure(text=f"❌ Σφάλμα κατά την εξαγωγή: {error}", text_color="red")
                
        if chart_path and os.path.exists(chart_path):
            try:
                os.remove(chart_path)
            except Exception:
                pass

    def export_to_pdf(self):
        """Εξάγει το κείμενο της παραγόμενης ανάλυσης σε αρχείο μορφής PDF (.pdf)."""
        text, stock_name, chart_path, prices_dict, stats_dict = self._prepare_export_data()
        if not text:
            self.status_main.configure(text="❌ Δεν υπάρχει κείμενο για εξαγωγή!", text_color="red")
            return
            
        import re
        import os
        safe_stock_name = re.sub(r'[\\/*?:"<>|]', "", stock_name).replace(' ', '_')
            
        file_path = filedialog.asksaveasfilename(
            defaultextension=".pdf",
            filetypes=[("PDF Document", "*.pdf")],
            title="Αποθήκευση Ανάλυσης",
            initialfile=f"Ανάλυση_{safe_stock_name}.pdf"
        )

        if file_path:
            self.status_main.configure(text="⏳ Δημιουργία PDF... Παρακαλώ περιμένετε.", text_color="orange")
            self.update()
            
            success, error = document_exporter.save_to_pdf(text, stock_name, file_path, chart_image=chart_path, prices=prices_dict, stats=stats_dict)
            if success:
                self.status_main.configure(text="✅ Εξήχθη επιτυχώς σε PDF!", text_color="green")
            else:
                self.status_main.configure(text=f"❌ Σφάλμα PDF: Ελέγξτε αν έχετε εγκαταστήσει το 'docx2pdf'. Λεπτομέρειες: {error}", text_color="red")

        if chart_path and os.path.exists(chart_path):
            try:
                os.remove(chart_path)
            except Exception:
                pass

    def print_analysis(self):
        """Στέλνει το κείμενο της ανάλυσης στον προεπιλεγμένο εκτυπωτή του συστήματος."""
        text = self.result_textbox.get("1.0", "end-1c").strip()
        if not text:
            self.status_main.configure(text="❌ Δεν υπάρχει κείμενο για εκτύπωση!", text_color="red")
            return

        try:
            fd, path = tempfile.mkstemp(suffix=".txt", prefix="Ανάλυση_")
            with os.fdopen(fd, 'w', encoding='utf-8') as f:
                f.write(text)
            
            if os.name == 'nt':
                os.startfile(path, "print")
            else:
                # macOS/Linux
                subprocess.run(["lpr", path])
                
            self.status_main.configure(text="✅ Το κείμενο εστάλη στον εκτυπωτή!", text_color="green")
        except Exception as e:
            self.status_main.configure(text=f"❌ Σφάλμα εκτύπωσης: {e}", text_color="red")

    def save_keys(self):
        self.user_data["api_key"] = self.api_key_entry.get()
        self.user_data["av_api_key"] = self.av_key_entry.get()
        self.user_data["finnhub_api_key"] = self.finnhub_key_entry.get()
        self.user_data["newsapi_key"] = self.newsapi_key_entry.get()
        self.user_data["ollama_cloud_key"] = self.ollama_cloud_key_entry.get()
        save_data(self.user_data)
        self.status_label.configure(text="✅ Αποθηκεύτηκε!", text_color="green")
        if self.ai_provider_menu.get() in ["Gemini (Cloud)", "Ollama (Cloud)"]:
            self.update_models()

    def update_ai_info_label(self, *args):
        if hasattr(self, 'ai_info_label') and self.ai_info_label.winfo_exists():
            provider = self.ai_provider_menu.get()
            model = self.ai_model_var.get()
            if model and model not in ["Φόρτωση...", "Απαιτείται API Key", "Κανένα διαθέσιμο μοντέλο", "Σφάλμα φόρτωσης"]:
                self.ai_info_label.configure(text=f"🤖 AI: {provider} ({model})")
            else:
                self.ai_info_label.configure(text="")

    def update_temp_label(self, value):
        self.temp_val_label.configure(text=f"{value:.1f}")

    def save_stock(self):
        name = self.stock_name_entry.get().strip()
        yahoo = self.stock_yahoo_entry.get().strip().upper()
        ft = self.stock_ft_entry.get().strip()
        inv = self.stock_inv_entry.get().strip()
        notes = self.stock_notes_entry.get("1.0", "end-1c").strip()
        
        if not name or not yahoo:
            self.status_label.configure(text="❌ Συμπληρώστε Όνομα & Yahoo!", text_color="red")
            return
            
        watchlist = self.user_data.get("watchlist", [])
        
        if hasattr(self, "editing_stock_index") and self.editing_stock_index is not None:
            watchlist[self.editing_stock_index] = {"Ονομασία": name, "Yahoo": yahoo, "FT": ft, "Investing": inv, "Notes": notes}
            self.editing_stock_index = None
            self.status_label.configure(text=f"✅ Τροποποιήθηκε: {name}", text_color="green")
        else:
            if any(s.get("Ονομασία") == name for s in watchlist):
                self.status_label.configure(text="❌ Η μετοχή υπάρχει ήδη!", text_color="red")
                return
            watchlist.append({"Ονομασία": name, "Yahoo": yahoo, "FT": ft, "Investing": inv, "Notes": notes})
            self.status_label.configure(text=f"✅ Προστέθηκε: {name}", text_color="green")
            self.stock_var.set(name)
            
        self.user_data["watchlist"] = watchlist
        save_data(self.user_data)
        self.update_dropdown()
        self.update_watchlist_table()
        
        self.stock_name_entry.delete(0, 'end')
        self.stock_yahoo_entry.delete(0, 'end')
        self.stock_ft_entry.delete(0, 'end')
        self.stock_inv_entry.delete(0, 'end')
        self.stock_notes_entry.delete("1.0", 'end')
        self.save_stock_btn.configure(text="💾 Αποθήκευση Μετοχής")

    def move_stock_up(self, index):
        if index > 0:
            watchlist = self.user_data.get("watchlist", [])
            watchlist[index - 1], watchlist[index] = watchlist[index], watchlist[index - 1]
            self.user_data["watchlist"] = watchlist
            save_data(self.user_data)
            self.update_dropdown()
            self.update_watchlist_table()

    def move_stock_down(self, index):
        watchlist = self.user_data.get("watchlist", [])
        if index < len(watchlist) - 1:
            watchlist[index + 1], watchlist[index] = watchlist[index], watchlist[index + 1]
            self.user_data["watchlist"] = watchlist
            save_data(self.user_data)
            self.update_dropdown()
            self.update_watchlist_table()

    def edit_stock(self, index):
        watchlist = self.user_data.get("watchlist", [])
        if index < len(watchlist):
            item = watchlist[index]
           
            if hasattr(self, 'stock_mng_header_btn') and "▶" in self.stock_mng_header_btn.cget("text"):
                self._toggle_collapsible(self.stock_mng_frame, self.stock_mng_header_btn, self.tr("stock_management"))
                
            self.stock_name_entry.delete(0, 'end')
            self.stock_name_entry.insert(0, item.get("Ονομασία", ""))
            self.stock_yahoo_entry.delete(0, 'end')
            self.stock_yahoo_entry.insert(0, item.get("Yahoo", ""))
            self.stock_ft_entry.delete(0, 'end')
            self.stock_ft_entry.insert(0, item.get("FT", ""))
            self.stock_inv_entry.delete(0, 'end')
            self.stock_inv_entry.insert(0, item.get("Investing", ""))
            self.stock_notes_entry.delete("1.0", 'end')
            self.stock_notes_entry.insert("1.0", item.get("Notes", ""))
            self.editing_stock_index = index
            self.save_stock_btn.configure(text="💾 Ενημέρωση Μετοχής")

    def delete_stock(self, selected_name=None):
        if not selected_name:
            selected_name = self.stock_var.get()
            
        if selected_name in [self.tr("choose_stock_default"), self.tr("no_stocks_found"), "Επίλεξε Μετοχή...", "Δεν υπάρχουν μετοχές"]:
            return
            
        self.user_data["watchlist"] = [item for item in self.user_data.get("watchlist", []) if item.get("Ονομασία") != selected_name]
        save_data(self.user_data)
        self.update_dropdown()
        self.update_watchlist_table()
        
        if self.stock_var.get() == selected_name:
            self.stock_var.set(self.tr("choose_stock_default"))
            
        self.status_label.configure(text=f"✅ Διεγράφη: {selected_name[:15]}", text_color="green")

    def insert_selected_metatag(self, choice):
        if choice == self.tr("insert_meta"):
            return

        metatag = next((m for m in self.user_data.get("metatags", []) if m.get("name") == choice), None)
        if metatag:
            content_to_insert = metatag.get("content", "")
            current_text = self.extra_prompt_box.get("1.0", "end-1c").strip()
            
            if current_text:
                self.extra_prompt_box.insert("end", f"\n\n{content_to_insert}")
            else:
                self.extra_prompt_box.insert("1.0", content_to_insert)
        
        self.metatag_insert_var.set(self.tr("insert_meta"))

    def save_metatag(self):
        name = self.meta_name_entry.get().strip()
        info = self.meta_info_entry.get("1.0", "end-1c").strip()
        content = self.meta_content_box.get("1.0", "end-1c").strip()
        
        if not name or not content:
            self.status_label.configure(text="❌ Συμπληρώστε Όνομα & Περιεχόμενο!", text_color="red")
            return
            
        metatags = self.user_data.setdefault("metatags", [])
        
        if hasattr(self, "editing_meta_index") and self.editing_meta_index is not None:
            metatags[self.editing_meta_index] = {"name": name, "info": info, "content": content}
            self.editing_meta_index = None
            self.status_label.configure(text=f"✅ Τροποποιήθηκε: {name}", text_color="green")
        else:
            if any(m.get("name") == name for m in metatags):
                self.status_label.configure(text="❌ Το Metatag υπάρχει ήδη!", text_color="red")
                return
            metatags.append({"name": name, "info": info, "content": content})
            self.status_label.configure(text=f"✅ Προστέθηκε: {name}", text_color="green")
            
        self.user_data["metatags"] = metatags
        save_data(self.user_data)
        self.update_metatags_table()
        
        self.meta_name_entry.delete(0, 'end')
        self.meta_info_entry.delete("1.0", 'end')
        self.meta_content_box.delete("1.0", 'end')
        self.save_meta_btn.configure(text=self.tr("save_meta"))

    def edit_metatag(self, index):
        metatags = self.user_data.get("metatags", [])
        if index < len(metatags):
            item = metatags[index]
           
            if hasattr(self, 'meta_header_btn') and "▶" in self.meta_header_btn.cget("text"):
                self._toggle_collapsible(self.meta_frame, self.meta_header_btn, self.tr("metatags_title"))
                
            self.meta_name_entry.delete(0, 'end')
            self.meta_name_entry.insert(0, item.get("name", ""))
            self.meta_info_entry.delete("1.0", 'end')
            self.meta_info_entry.insert("1.0", item.get("info", ""))
            self.meta_content_box.delete("1.0", 'end')
            self.meta_content_box.insert("1.0", item.get("content", ""))
            self.editing_meta_index = index
            self.save_meta_btn.configure(text="💾 Ενημέρωση Metatag")

    def delete_metatag(self, name):
        self.user_data["metatags"] = [m for m in self.user_data.get("metatags", []) if m.get("name") != name]
        save_data(self.user_data)
        self.update_metatags_table()
        self.status_label.configure(text=f"✅ Διεγράφη: {name[:15]}", text_color="green")

    def update_metatags_table(self):
        for widget in self.meta_list_frame.winfo_children():
            widget.destroy()

        for idx, item in enumerate(self.user_data.get("metatags", [])):
            name = item.get("name", "N/A")
            bg_color = "transparent" if idx % 2 == 0 else "#2b2b2b"
            
            display_name = name if len(name) <= 22 else name[:20] + ".."
            
            row_frame = ctk.CTkFrame(self.meta_list_frame, fg_color=bg_color, corner_radius=4)
            row_frame.pack(fill="x", pady=1)
            row_frame.grid_columnconfigure(0, weight=1)
            
            lbl_name = ctk.CTkLabel(row_frame, text=display_name, font=ctk.CTkFont(size=12), anchor="w")
            lbl_name.grid(row=0, column=0, padx=4, pady=2, sticky="we")
            
            info_text = item.get("info", "").strip()
            tt_text = f"{name}\n{info_text}" if info_text else name
            ToolTip(lbl_name, tt_text)

            edit_btn = ctk.CTkButton(row_frame, text="✏️", width=25, height=20, fg_color="#f0ad4e", text_color="black", hover_color="#ec971f", command=lambda i=idx: self.edit_metatag(i))
            edit_btn.grid(row=0, column=1, padx=2, pady=2, sticky="e")

            del_btn = ctk.CTkButton(row_frame, text="❌", width=25, height=20, fg_color="#d9534f", hover_color="#c9302c", command=lambda n=name: self.delete_metatag(n))
            del_btn.grid(row=0, column=2, padx=2, pady=2, sticky="e")
        
        self.update_metatags_dropdown()

    def update_metatags_dropdown(self):
        metatag_names = [m.get("name") for m in self.user_data.get("metatags", [])]
        self.metatag_insert_menu.configure(values=[self.tr("insert_meta")] + metatag_names)

    def clear_cache(self):
        """Επαναφέρει το περιβάλλον (κρατώντας το ιστορικό ανέπαφο)."""
        self.result_textbox.delete("1.0", "end")
        
        for widget in self.chart_inner_frame.winfo_children():
            widget.destroy()
        self.chart_lbl = ctk.CTkLabel(self.chart_inner_frame, text="[Χώρος Γραφήματος Matplotlib]\nΤο γράφημα θα εμφανιστεί εδώ.", text_color="gray")
        self.chart_lbl.pack(fill="both", expand=True, pady=40)
        self.current_df = None
        
        for widget in self.news_frame.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.news_frame, text="Οι ειδήσεις θα εμφανιστούν εδώ.", text_color="gray").pack(pady=20)
        self.news_checkboxes = []
        self.news_article_frames = []
        if hasattr(self, 'news_search_var'):
            self.news_search_var.set("")

        for widget in self.newsapi_frame.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.newsapi_frame, text="Ενεργοποιήστε το NewsAPI αριστερά για προβολή.", text_color="gray").pack(pady=20)
        self.newsapi_checkboxes = []
        self.newsapi_article_frames = []
        if hasattr(self, 'newsapi_search_var'):
            self.newsapi_search_var.set("")
        
        for widget in self.pages_frame.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.pages_frame, text="Επιλέξτε μια μετοχή για να δείτε τους συνδέσμους.", text_color="gray").pack(pady=20)
        self.page_checkboxes = []
        
        for widget in self.rss_frame.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.rss_frame, text=self.tr("rss_empty_msg"), text_color="gray").pack(pady=20)
        self.rss_checkboxes = []
        self.rss_article_frames = []
        if hasattr(self, 'rss_search_var'):
            self.rss_search_var.set("")
        
        labels_to_reset = [
            self.l_yahoo, self.l_ft, self.l_inv, self.l_mcap, self.l_pe, self.l_div, self.l_beta,
            self.l_rsi, self.l_macd, self.l_sma20, self.l_sma50, self.l_av_pe, self.l_av_div, self.l_av_eps,
            self.l_fh_cur, self.l_fh_open, self.l_fh_high, self.l_fh_low,
            self.l_rev_growth, self.l_roe, self.l_op_margin, self.l_dte, self.l_fcf
        ]
        for lbl in labels_to_reset:
            lbl.configure(text="---")
        
        if hasattr(self, 'notes_display_box'):
            self.notes_display_box.configure(state="normal")
            self.notes_display_box.delete("1.0", "end")
            self.notes_display_box.configure(state="disabled")
            self.notes_frame.pack_forget()
            
        if hasattr(self, 'article_boxes'):
            for box in self.article_boxes:
                box.delete("1.0", "end")
                box.configure(height=28)
                
        self.attached_files = []
        if hasattr(self, 'files_list_label'):
            self.files_list_label.configure(text="")
            self.clear_files_btn.pack_forget()
            
        self.current_av_context = ""
        self.current_fh_context = ""
        
        self.overview_title.configure(text=self.tr("overview_title"))
        self.website_url = ""
        self.website_link_label.pack_forget()
        self.website_cb.pack_forget()
        if hasattr(self, 'ai_info_label'):
            self.update_ai_info_label()
        self.status_label.configure(text="✅ Τα προσωρινά δεδομένα διαγράφηκαν!", text_color="green")

    def _on_rss_chk_toggle(self):
        self._update_rss_selected_count()
        if self.rss_show_selected_only:
            self._filter_rss_ui()

    def _on_news_chk_toggle(self):
        self._update_news_selected_count()
        if self.news_show_selected_only:
            self._filter_news_ui()

    def _on_newsapi_chk_toggle(self):
        self._update_newsapi_selected_count()
        if self.newsapi_show_selected_only:
            self._filter_newsapi_ui()

    def select_all_rss(self):
        if hasattr(self, 'rss_checkboxes'):
            for chk_var, _ in self.rss_checkboxes:
                chk_var.set(1)
            self._update_rss_selected_count()
            self._filter_rss_ui()

    def deselect_all_rss(self):
        if hasattr(self, 'rss_checkboxes'):
            for chk_var, _ in self.rss_checkboxes:
                chk_var.set(0)
            self._update_rss_selected_count()
            self._filter_rss_ui()

    def toggle_show_selected_rss(self):
        self.rss_show_selected_only = not self.rss_show_selected_only
        self.rss_show_selected_btn.configure(fg_color="#f0ad4e" if self.rss_show_selected_only else "#5cb85c", hover_color="#ec971f" if self.rss_show_selected_only else "#4cae4c")
        self._filter_rss_ui()

    def _update_rss_selected_count(self):
        if hasattr(self, 'rss_checkboxes'):
            count = sum(1 for chk_var, _ in self.rss_checkboxes if chk_var.get() == 1)
            self.rss_selected_count_lbl.configure(text=f"{self.tr('selected_articles')} {count}")

    def select_all_news(self):
        if hasattr(self, 'news_checkboxes'):
            for chk_var, _ in self.news_checkboxes:
                chk_var.set(1)
            self._update_news_selected_count()
            self._filter_news_ui()

    def deselect_all_news(self):
        if hasattr(self, 'news_checkboxes'):
            for chk_var, _ in self.news_checkboxes:
                chk_var.set(0)
            self._update_news_selected_count()
            self._filter_news_ui()

    def toggle_show_selected_news(self):
        self.news_show_selected_only = not self.news_show_selected_only
        self.news_show_selected_btn.configure(fg_color="#f0ad4e" if self.news_show_selected_only else "#5cb85c", hover_color="#ec971f" if self.news_show_selected_only else "#4cae4c")
        self._filter_news_ui()

    def _update_news_selected_count(self):
        if hasattr(self, 'news_checkboxes'):
            count = sum(1 for chk_var, _ in self.news_checkboxes if chk_var.get() == 1)
            self.news_selected_count_lbl.configure(text=f"{self.tr('selected_articles')} {count}")

    def select_all_newsapi(self):
        if hasattr(self, 'newsapi_checkboxes'):
            for chk_var, _ in self.newsapi_checkboxes:
                chk_var.set(1)
            self._update_newsapi_selected_count()
            self._filter_newsapi_ui()

    def deselect_all_newsapi(self):
        if hasattr(self, 'newsapi_checkboxes'):
            for chk_var, _ in self.newsapi_checkboxes:
                chk_var.set(0)
            self._update_newsapi_selected_count()
            self._filter_newsapi_ui()

    def toggle_show_selected_newsapi(self):
        self.newsapi_show_selected_only = not self.newsapi_show_selected_only
        self.newsapi_show_selected_btn.configure(fg_color="#f0ad4e" if self.newsapi_show_selected_only else "#5cb85c", hover_color="#ec971f" if self.newsapi_show_selected_only else "#4cae4c")
        self._filter_newsapi_ui()

    def _update_newsapi_selected_count(self):
        if hasattr(self, 'newsapi_checkboxes'):
            count = sum(1 for chk_var, _ in self.newsapi_checkboxes if chk_var.get() == 1)
            self.newsapi_selected_count_lbl.configure(text=f"{self.tr('selected_articles')} {count}")

    def clear_cache(self):
        """Επαναφέρει το περιβάλλον (κρατώντας το ιστορικό ανέπαφο)."""
        self.result_textbox.delete("1.0", "end")
        
        for widget in self.chart_inner_frame.winfo_children():
            widget.destroy()
        self.chart_lbl = ctk.CTkLabel(self.chart_inner_frame, text="[Χώρος Γραφήματος Matplotlib]\nΤο γράφημα θα εμφανιστεί εδώ.", text_color="gray")
        self.chart_lbl.pack(fill="both", expand=True, pady=40)
        self.current_df = None
        self.current_fig = None
        self.current_analysis_stock = ""
        
        # Clear News tab
        for widget in self.news_frame.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.news_frame, text="Οι ειδήσεις θα εμφανιστούν εδώ.", text_color="gray").pack(pady=20)
        self.news_checkboxes = []
        self.news_article_frames = []
        if hasattr(self, 'news_search_var'):
            self.news_search_var.set("")
        self.news_show_selected_only = False
        self.news_show_selected_btn.configure(fg_color="#5cb85c", hover_color="#4cae4c")
        self._update_news_selected_count()

        # Clear NewsAPI tab
        for widget in self.newsapi_frame.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.newsapi_frame, text="Ενεργοποιήστε το NewsAPI αριστερά για προβολή.", text_color="gray").pack(pady=20)
        self.newsapi_checkboxes = []
        self.newsapi_article_frames = []
        if hasattr(self, 'newsapi_search_var'):
            self.newsapi_search_var.set("")
        self.newsapi_show_selected_only = False
        self.newsapi_show_selected_btn.configure(fg_color="#5cb85c", hover_color="#4cae4c")
        self._update_newsapi_selected_count()
        
        for widget in self.pages_frame.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.pages_frame, text="Επιλέξτε μια μετοχή για να δείτε τους συνδέσμους.", text_color="gray").pack(pady=20)
        self.page_checkboxes = []
        
        # Clear RSS tab
        for widget in self.rss_frame.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.rss_frame, text=self.tr("rss_empty_msg"), text_color="gray").pack(pady=20)
        self.rss_checkboxes = []
        self.rss_article_frames = []
        if hasattr(self, 'rss_search_var'):
            self.rss_search_var.set("")
        self.rss_show_selected_only = False
        self.rss_show_selected_btn.configure(fg_color="#5cb85c", hover_color="#4cae4c")
        self._update_rss_selected_count()
        
        labels_to_reset = [
            self.l_yahoo, self.l_ft, self.l_inv, self.l_mcap, self.l_pe, self.l_div, self.l_beta,
            self.l_rsi, self.l_macd, self.l_sma20, self.l_sma50, self.l_av_pe, self.l_av_div, self.l_av_eps,
            self.l_fh_cur, self.l_fh_open, self.l_fh_high, self.l_fh_low,
            self.l_rev_growth, self.l_roe, self.l_op_margin, self.l_dte, self.l_fcf
        ]
        for lbl in labels_to_reset:
            lbl.configure(text="---")
        
        if hasattr(self, 'notes_display_box'):
            self.notes_display_box.configure(state="normal")
            self.notes_display_box.delete("1.0", "end")
            self.notes_display_box.configure(state="disabled")
            self.notes_frame.pack_forget()
            
        if hasattr(self, 'article_boxes'):
            for box in self.article_boxes:
                box.delete("1.0", "end")
                
        self.attached_files = []
        if hasattr(self, 'files_list_label'):
            self.files_list_label.configure(text="")
            self.clear_files_btn.pack_forget()
            
        self.current_av_context = ""
        self.current_fh_context = ""
        
        self.overview_title.configure(text=self.tr("overview_title"))
        self.website_url = ""
        self.website_link_label.pack_forget()
        self.website_cb.pack_forget()
        if hasattr(self, 'ai_info_label'):
            self.update_ai_info_label()
        self.status_label.configure(text="✅ Τα προσωρινά δεδομένα διαγράφηκαν!", text_color="green")

    def backup_data(self):
        """Εξάγει τα τρέχοντα δεδομένα χρήστη σε ένα αρχείο JSON."""
        file_path = filedialog.asksaveasfilename(
            defaultextension=".json",
            filetypes=[("JSON Files", "*.json")],
            title=self.tr("backup_data"),
            initialfile=f"AI_Stock_Analyzer_Backup_{datetime.date.today().isoformat()}.json"
        )
        if file_path:
            try:
                import json
                with open(file_path, "w", encoding="utf-8") as f:
                    json.dump(self.user_data, f, ensure_ascii=False, indent=4)
                self.status_label.configure(text=self.tr("backup_success"), text_color="green")
            except Exception as e:
                logger.error(f"Σφάλμα κατά τη δημιουργία backup: {e}")
                self.status_label.configure(text=self.tr("backup_error"), text_color="red")

    def restore_data(self):
        """Φορτώνει δεδομένα χρήστη από ένα αρχείο backup JSON."""
        if not messagebox.askyesno(self.tr("restore_confirm_title"), self.tr("restore_confirm_msg")):
            return

        file_path = filedialog.askopenfilename(
            title=self.tr("restore_data"),
            filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
        )
        if file_path:
            try:
                import json
                with open(file_path, "r", encoding="utf-8") as f:
                    restored_data = json.load(f)
                
                if "watchlist" in restored_data and "api_key" in restored_data:
                    save_data(restored_data)
                    self.status_label.configure(text=self.tr("restore_success"), text_color="green")
                    messagebox.showinfo("Επανεκκίνηση / Restart", "Τα δεδομένα επαναφέρθηκαν. Παρακαλώ κάντε επανεκκίνηση της εφαρμογής για να εφαρμοστούν πλήρως οι αλλαγές.\n\nData has been restored. Please restart the application for the changes to take full effect.")
                else:
                    raise ValueError("Το αρχείο δεν φαίνεται να είναι έγκυρο backup.")
            except Exception as e:
                logger.error(f"Σφάλμα κατά την επαναφορά από backup: {e}")
                self.status_label.configure(text=self.tr("restore_error"), text_color="red")
                messagebox.showerror("Σφάλμα Επαναφοράς", f"Δεν ήταν δυνατή η επαναφορά των δεδομένων από το αρχείο.\n\nΣφάλμα: {e}")

    def clear_all_data(self):
        confirm = messagebox.askyesno("Επιβεβαίωση", "Είστε σίγουροι ότι θέλετε να διαγράψετε ΟΛΑ τα δεδομένα της εφαρμογής;\n\nΑυτή η ενέργεια θα διαγράψει το Ιστορικό, την Watchlist, τα API Keys και τα αποθηκευμένα URLs και δεν μπορεί να αναιρεθεί.")
        if confirm:
            current_lang = self.user_data.get("language", "el")
            self.user_data = {
                "language": current_lang,
                "api_key": "", "av_api_key": "", "finnhub_api_key": "", "newsapi_key": "", "ollama_cloud_key": "",
                "watchlist": [], "urls": [], "history": [],
                "api_usage": {"date": datetime.date.today().isoformat(), "av": 0, "fh": 0, "newsapi": 0}
            }
            save_data(self.user_data)
            
            self.api_key_entry.delete(0, 'end')
            self.av_key_entry.delete(0, 'end')
            self.finnhub_key_entry.delete(0, 'end')
            self.newsapi_key_entry.delete(0, 'end')
            self.ollama_cloud_key_entry.delete(0, 'end')

            self.stock_name_entry.delete(0, 'end')
            self.stock_yahoo_entry.delete(0, 'end')
            self.stock_ft_entry.delete(0, 'end')
            self.stock_inv_entry.delete(0, 'end')
            self.stock_notes_entry.delete("1.0", 'end')
            self.save_stock_btn.configure(text=self.tr("save_stock"))
            self.editing_stock_index = None
            
            for row in self.url_rows:
                row["frame"].destroy()
            self.url_rows = []
            
            self.update_history_ui()
            self.update_dropdown()
            self.update_watchlist_table()
            
            self.clear_cache()
            self._sync_api_usage()
            
            self.status_label.configure(text="✅ Όλα τα δεδομένα διαγράφηκαν!", text_color="green")

    def _select_and_fetch(self, name):
        self.stock_var.set(name)
        self.on_stock_select(name)

    def update_watchlist_table(self):
        for widget in self.watchlist_frame.winfo_children():
            widget.destroy()

        self.watchlist_frame.grid_columnconfigure(0, weight=1)
        self.watchlist_frame.grid_columnconfigure((1, 2, 3), weight=0)

        headers = [self.tr("wl_name"), self.tr("wl_order"), self.tr("wl_edit"), self.tr("wl_delete")]
        for col, text in enumerate(headers):
            align = "w" if col == 0 else "e"
            ctk.CTkLabel(self.watchlist_frame, text=text, font=ctk.CTkFont(weight="bold", size=11)).grid(row=0, column=col, padx=2, pady=2, sticky=align)

        search_term = getattr(self, 'wl_search_var', ctk.StringVar()).get().lower()
        
        display_idx = 0
        for idx, item in enumerate(self.user_data.get("watchlist", [])):
            name = item.get("Ονομασία", "N/A")
            
            if search_term and search_term not in name.lower() and search_term not in item.get("Yahoo", "").lower():
                continue
                
            bg_color = "transparent" if display_idx % 2 == 0 else "#2b2b2b"
            
            # Αφού τώρα υπάρχει χώρος, επιτρέπουμε μεγαλύτερα ονόματα
            display_name = name if len(name) <= 22 else name[:20] + ".."
            
            row_frame = ctk.CTkFrame(self.watchlist_frame, fg_color=bg_color, corner_radius=4)
            row_frame.grid(row=display_idx+1, column=0, columnspan=4, sticky="ew", pady=1)
            row_frame.grid_columnconfigure(0, weight=1)
            
            lbl_name = ctk.CTkLabel(row_frame, text=display_name, font=ctk.CTkFont(size=12), anchor="w")
            lbl_name.grid(row=0, column=0, padx=4, pady=2, sticky="we")
            lbl_name.bind("<Double-Button-1>", lambda e, n=name: self._select_and_fetch(n))
            ToolTip(lbl_name, name)

            order_frame = ctk.CTkFrame(row_frame, fg_color="transparent")
            order_frame.grid(row=0, column=1, padx=2, pady=2, sticky="e")
            
            up_btn = ctk.CTkButton(order_frame, text="▲", width=20, height=20, fg_color="#444", hover_color="#555", command=lambda i=idx: self.move_stock_up(i))
            up_btn.pack(side="left", padx=1)
            if idx == 0 or search_term: up_btn.configure(state="disabled")
                
            down_btn = ctk.CTkButton(order_frame, text="▼", width=20, height=20, fg_color="#444", hover_color="#555", command=lambda i=idx: self.move_stock_down(i))
            down_btn.pack(side="left", padx=1)
            if idx == len(self.user_data.get("watchlist", [])) - 1 or search_term: down_btn.configure(state="disabled")

            edit_btn = ctk.CTkButton(row_frame, text="✏️", width=25, height=20, fg_color="#f0ad4e", text_color="black", hover_color="#ec971f", command=lambda i=idx: self.edit_stock(i))
            edit_btn.grid(row=0, column=2, padx=2, pady=2, sticky="e")

            del_btn = ctk.CTkButton(row_frame, text="❌", width=25, height=20, fg_color="#d9534f", hover_color="#c9302c", command=lambda s=name: self.delete_stock(s))
            del_btn.grid(row=0, column=3, padx=2, pady=2, sticky="e")
            
            display_idx += 1

    def update_models(self, selected_provider=None):
        """Ανανεώνει τη λίστα των διαθέσιμων μοντέλων AI ανάλογα με τον επιλεγμένο πάροχο."""
        provider = selected_provider or self.ai_provider_menu.get()
        self.ai_model_var.set("Φόρτωση...")
        self.ai_model_menu.configure(values=["Φόρτωση..."])
        threading.Thread(target=self._fetch_models_thread, args=(provider,), daemon=True).start()

    def _fetch_models_thread(self, provider):
        if provider == "Gemini (Cloud)":
            api_key = self.user_data.get("api_key")
        elif provider == "Ollama (Cloud)":
            api_key = self.user_data.get("ollama_cloud_key")
        else:
            api_key = None
            
        models = ai_service.fetch_models(provider, api_key)
        self.after(0, self._update_model_menu, models)
            
    def _update_model_menu(self, models):
        self.ai_model_menu.configure(values=models)
        self.ai_model_var.set(models[0] if models else "")

    def update_dropdown(self):
        names = [item.get("Ονομασία", "Άγνωστο") for item in self.user_data.get("watchlist", [])]
        if not names: names = [self.tr("no_stocks_found")]
        self.stock_menu.configure(values=names, command=self.on_stock_select)

if __name__ == "__main__":
    app = App()
    app.mainloop()