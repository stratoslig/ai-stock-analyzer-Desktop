import customtkinter as ctk
import threading
from tkinter import filedialog
import webbrowser
import logging
import tkinter as tk
from tkinter import messagebox
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg, NavigationToolbar2Tk
from matplotlib.figure import Figure
import matplotlib.dates as mdates
from matplotlib.widgets import MultiCursor
import requests
import datetime
import os
import sys
import tempfile
import subprocess
import PyPDF2

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

def resource_path(relative_path):
    """Επιστρέφει την απόλυτη διαδρομή για το αρχείο, συμβατό με το PyInstaller."""
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

class ToolTip:
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
    def __init__(self):
        super().__init__()
        self.user_data = load_data()
        if "language" not in self.user_data:
            self.user_data["language"] = "el"
        self.current_av_context = ""
        self.current_fh_context = ""
        self.page_checkboxes = []

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
        
        try:
            self.iconbitmap(resource_path("icon.ico"))
            # Ενημέρωση των Windows για εμφάνιση του σωστού εικονιδίου στη γραμμή εργασιών (Taskbar)
            import ctypes
            myappid = 'aistockanalyzer.pro.desktop.1.2'
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(myappid)
        except Exception:
            pass
            
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, minsize=380)

        # --- ΠΛΕΥΡΙΚΗ ΜΠΑΡΑ ---
        self.sidebar_frame = ctk.CTkScrollableFrame(self, width=380, corner_radius=0)
        self.sidebar_frame.grid(row=0, column=0, sticky="nsew")
        self.sidebar_frame.grid_rowconfigure(21, weight=1)
        self.sidebar_frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(self.sidebar_frame, text=self.tr("language"), font=ctk.CTkFont(size=12, weight="bold")).grid(row=0, column=0, padx=20, pady=(15, 0), sticky="w")
        self.lang_var = ctk.StringVar(value="Ελληνικά" if self.user_data.get("language", "el") == "el" else "English")
        self.lang_menu = ctk.CTkOptionMenu(self.sidebar_frame, variable=self.lang_var, values=["Ελληνικά", "English"], command=self.change_language)
        self.lang_menu.grid(row=1, column=0, padx=20, pady=5, sticky="ew")

        ctk.CTkLabel(self.sidebar_frame, text=self.tr("ai_provider"), font=ctk.CTkFont(size=12, weight="bold")).grid(row=2, column=0, padx=20, pady=(10, 0), sticky="w")
        self.ai_provider_menu = ctk.CTkOptionMenu(self.sidebar_frame, values=["Gemini (Cloud)", "Ollama (Τοπικά)"], command=self.update_models)
        self.ai_provider_menu.grid(row=3, column=0, padx=20, pady=5, sticky="ew")

        temp_frame = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        temp_frame.grid(row=4, column=0, padx=20, pady=(5, 0), sticky="ew")
        ctk.CTkLabel(temp_frame, text=self.tr("temperature"), font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        self.temp_val_label = ctk.CTkLabel(temp_frame, text="0.7", font=ctk.CTkFont(size=12))
        self.temp_val_label.pack(side="right")
        
        self.temperature_slider = ctk.CTkSlider(self.sidebar_frame, from_=0.0, to=1.0, number_of_steps=10, command=self.update_temp_label)
        self.temperature_slider.set(0.7)
        self.temperature_slider.grid(row=5, column=0, padx=20, pady=5, sticky="ew")
        ToolTip(self.temperature_slider, self.tr("tt_temp"))

        ctk.CTkLabel(self.sidebar_frame, text=self.tr("installed_models"), font=ctk.CTkFont(size=12, weight="bold")).grid(row=6, column=0, padx=20, pady=(5, 0), sticky="w")
        self.ai_model_var = ctk.StringVar(value="Φόρτωση...")
        self.ai_model_menu = ctk.CTkOptionMenu(self.sidebar_frame, variable=self.ai_model_var, values=["Φόρτωση..."])
        self.ai_model_menu.grid(row=7, column=0, padx=20, pady=5, sticky="ew")

        ctk.CTkLabel(self.sidebar_frame, text=self.tr("api_keys"), font=ctk.CTkFont(size=14, weight="bold")).grid(row=8, column=0, padx=20, pady=(10, 0), sticky="w")
        
        f_api1 = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        f_api1.grid(row=9, column=0, padx=20, pady=2, sticky="ew")
        ctk.CTkLabel(f_api1, text="Gemini API Key:", font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w")
        row_api1 = ctk.CTkFrame(f_api1, fg_color="transparent")
        row_api1.pack(fill="x")
        self.api_key_entry = ctk.CTkEntry(row_api1, placeholder_text="Επικόλληση κλειδιού...", show="*")
        self.api_key_entry.pack(side="left", fill="x", expand=True)
        self.api_key_entry.insert(0, self.user_data.get("api_key", ""))
        ctk.CTkButton(row_api1, text="📋", width=25, fg_color="#444", hover_color="#555", command=lambda: self.paste_to_entry(self.api_key_entry)).pack(side="right", padx=(5, 0))
        ToolTip(self.api_key_entry, self.tr("tt_api_gemini"))

        f_api2 = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        f_api2.grid(row=10, column=0, padx=20, pady=2, sticky="ew")
        ctk.CTkLabel(f_api2, text="Alpha Vantage Key:", font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w")
        row_api2 = ctk.CTkFrame(f_api2, fg_color="transparent")
        row_api2.pack(fill="x")
        self.av_key_entry = ctk.CTkEntry(row_api2, placeholder_text="Επικόλληση κλειδιού...", show="*")
        self.av_key_entry.pack(side="left", fill="x", expand=True)
        self.av_key_entry.insert(0, self.user_data.get("av_api_key", ""))
        ctk.CTkButton(row_api2, text="📋", width=25, fg_color="#444", hover_color="#555", command=lambda: self.paste_to_entry(self.av_key_entry)).pack(side="right", padx=(5, 0))
        ToolTip(self.av_key_entry, self.tr("tt_api_av"))

        f_api3 = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        f_api3.grid(row=11, column=0, padx=20, pady=2, sticky="ew")
        ctk.CTkLabel(f_api3, text="Finnhub Key:", font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w")
        row_api3 = ctk.CTkFrame(f_api3, fg_color="transparent")
        row_api3.pack(fill="x")
        self.finnhub_key_entry = ctk.CTkEntry(row_api3, placeholder_text="Επικόλληση κλειδιού...", show="*")
        self.finnhub_key_entry.pack(side="left", fill="x", expand=True)
        self.finnhub_key_entry.insert(0, self.user_data.get("finnhub_api_key", ""))
        ctk.CTkButton(row_api3, text="📋", width=25, fg_color="#444", hover_color="#555", command=lambda: self.paste_to_entry(self.finnhub_key_entry)).pack(side="right", padx=(5, 0))
        ToolTip(self.finnhub_key_entry, self.tr("tt_api_fh"))

        f_api4 = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        f_api4.grid(row=12, column=0, padx=20, pady=2, sticky="ew")
        ctk.CTkLabel(f_api4, text="NewsAPI Key:", font=ctk.CTkFont(size=11), text_color="gray").pack(anchor="w")
        row_api4 = ctk.CTkFrame(f_api4, fg_color="transparent")
        row_api4.pack(fill="x")
        self.newsapi_key_entry = ctk.CTkEntry(row_api4, placeholder_text="Επικόλληση κλειδιού...", show="*")
        self.newsapi_key_entry.pack(side="left", fill="x", expand=True)
        self.newsapi_key_entry.insert(0, self.user_data.get("newsapi_key", ""))
        ctk.CTkButton(row_api4, text="📋", width=25, fg_color="#444", hover_color="#555", command=lambda: self.paste_to_entry(self.newsapi_key_entry)).pack(side="right", padx=(5, 0))
        ToolTip(self.newsapi_key_entry, self.tr("tt_api_news"))

        self.save_settings_btn = ctk.CTkButton(self.sidebar_frame, text=self.tr("save_keys"), command=self.save_keys, fg_color="#2b2b2b", hover_color="#3b3b3b")
        self.save_settings_btn.grid(row=13, column=0, padx=20, pady=(5, 10), sticky="ew")

        ctk.CTkLabel(self.sidebar_frame, text=self.tr("stock_management"), font=ctk.CTkFont(size=14, weight="bold")).grid(row=14, column=0, padx=20, pady=(10, 0), sticky="w")

        f_stk1 = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        f_stk1.grid(row=15, column=0, padx=20, pady=2, sticky="ew")
        self.stock_name_entry = ctk.CTkEntry(f_stk1, placeholder_text=self.tr("stock_name"))
        self.stock_name_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(f_stk1, text="📋", width=25, fg_color="#444", hover_color="#555", command=lambda: self.paste_to_entry(self.stock_name_entry)).pack(side="right", padx=(5, 0))
        
        f_stk2 = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        f_stk2.grid(row=16, column=0, padx=20, pady=2, sticky="ew")
        self.stock_yahoo_entry = ctk.CTkEntry(f_stk2, placeholder_text="Yahoo Symbol")
        self.stock_yahoo_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(f_stk2, text="📋", width=25, fg_color="#444", hover_color="#555", command=lambda: self.paste_to_entry(self.stock_yahoo_entry)).pack(side="right", padx=(5, 0))
        
        f_stk3 = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        f_stk3.grid(row=17, column=0, padx=20, pady=2, sticky="ew")
        self.stock_ft_entry = ctk.CTkEntry(f_stk3, placeholder_text="Financial Times Symbol")
        self.stock_ft_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(f_stk3, text="📋", width=25, fg_color="#444", hover_color="#555", command=lambda: self.paste_to_entry(self.stock_ft_entry)).pack(side="right", padx=(5, 0))
        
        f_stk4 = ctk.CTkFrame(self.sidebar_frame, fg_color="transparent")
        f_stk4.grid(row=18, column=0, padx=20, pady=2, sticky="ew")
        self.stock_inv_entry = ctk.CTkEntry(f_stk4, placeholder_text="Investing.com Symbol")
        self.stock_inv_entry.pack(side="left", fill="x", expand=True)
        ctk.CTkButton(f_stk4, text="📋", width=25, fg_color="#444", hover_color="#555", command=lambda: self.paste_to_entry(self.stock_inv_entry)).pack(side="right", padx=(5, 0))
        
        self.save_stock_btn = ctk.CTkButton(self.sidebar_frame, text=self.tr("save_stock"), command=self.save_stock, fg_color="#2b2b2b", hover_color="#3b3b3b")
        self.save_stock_btn.grid(row=19, column=0, padx=20, pady=(5, 10), sticky="ew")

        ctk.CTkLabel(self.sidebar_frame, text=self.tr("watchlist"), font=ctk.CTkFont(size=14, weight="bold")).grid(row=20, column=0, padx=20, pady=(10, 5), sticky="w")

        self.watchlist_frame = ctk.CTkScrollableFrame(self.sidebar_frame, height=320)
        self.watchlist_frame.grid(row=21, column=0, padx=10, pady=(0, 10), sticky="nsew")
        
        self.clear_cache_btn = ctk.CTkButton(self.sidebar_frame, text=self.tr("clear_cache"), fg_color="transparent", border_width=1, text_color="gray", command=self.clear_cache)
        self.clear_cache_btn.grid(row=22, column=0, padx=20, pady=10, sticky="ew")
        ToolTip(self.clear_cache_btn, self.tr("tt_clear_cache"))

        self.clear_all_data_btn = ctk.CTkButton(self.sidebar_frame, text=self.tr("clear_all"), fg_color="transparent", border_width=1, text_color="#d9534f", hover_color="#3b1a1a", command=self.clear_all_data)
        self.clear_all_data_btn.grid(row=23, column=0, padx=20, pady=(0, 10), sticky="ew")
        ToolTip(self.clear_all_data_btn, self.tr("tt_clear_all"))

        self.status_label = ctk.CTkLabel(self.sidebar_frame, text="", text_color="green")
        self.status_label.grid(row=24, column=0, pady=(0, 10))

        self.update_watchlist_table()

        # --- ΚΥΡΙΩΣ ΧΩΡΟΣ ---
        self.main_container = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        self.main_container.grid(row=0, column=1, sticky="nsew")
        self.main_container.grid_columnconfigure(0, weight=1, minsize=430)
        self.main_container.grid_columnconfigure(1, weight=3)
        self.main_container.grid_rowconfigure(1, weight=1)

        header_frame = ctk.CTkFrame(self.main_container, fg_color="transparent")
        header_frame.grid(row=0, column=0, columnspan=2, sticky="ew", padx=20, pady=(20, 10))
        
        self.toggle_sidebar_btn = ctk.CTkButton(header_frame, text="☰", width=40, font=ctk.CTkFont(size=20), command=self.toggle_sidebar)
        self.toggle_sidebar_btn.pack(side="left", padx=(0, 10))
        title_lbl = ctk.CTkLabel(header_frame, text="📈 AI Stock Analyzer Desktop", font=ctk.CTkFont(size=24, weight="bold"))
        title_lbl.pack(side="left")

        self.about_btn = ctk.CTkButton(header_frame, text=self.tr("about_btn"), width=80, fg_color="transparent", border_width=1, text_color="gray", hover_color="#333", command=self.show_about_window)
        self.about_btn.pack(side="right", padx=10)

        self.left_scroll_frame = ctk.CTkScrollableFrame(self.main_container, fg_color="transparent")
        self.left_scroll_frame.grid(row=1, column=0, sticky="nsew", padx=(10, 5), pady=(0, 10))
        self.left_scroll_frame.grid_columnconfigure(0, weight=1)

        self.right_scroll_frame = ctk.CTkScrollableFrame(self.main_container, fg_color="transparent")
        self.right_scroll_frame.grid(row=1, column=1, sticky="nsew", padx=(5, 10), pady=(0, 10))
        self.right_scroll_frame.grid_columnconfigure(0, weight=1)

        self._build_data_pane(row=0, col=0)
        self._build_history_pane(row=1, col=0)
        self._build_overview_pane(row=0, col=0)

        self.update_dropdown()
        self.update_models()

    def show_about_window(self):
        about_win = ctk.CTkToplevel(self)
        about_win.title(self.tr("about_title"))
        about_win.geometry("450x320")
        about_win.resizable(False, False)
        about_win.transient(self) # Το κρατάει μπροστά από το κεντρικό παράθυρο
        about_win.grab_set()      # "Κλειδώνει" το κεντρικό παράθυρο μέχρι να κλείσει το About

        ctk.CTkLabel(about_win, text="📈 AI Stock Analyzer Desktop", font=ctk.CTkFont(size=20, weight="bold")).pack(pady=(20, 5))
        ctk.CTkLabel(about_win, text=self.tr("about_version"), font=ctk.CTkFont(size=12), text_color="gray").pack(pady=(0, 5))
        ctk.CTkLabel(about_win, text=self.tr("about_creator"), font=ctk.CTkFont(size=13, slant="italic", weight="bold"), text_color="#1f77b4").pack(pady=(0, 10))

        desc = self.tr("about_desc")
        ctk.CTkLabel(about_win, text=desc, wraplength=400, justify="center").pack(pady=10, padx=20)

        disclaimer = self.tr("about_disclaimer")
        ctk.CTkLabel(about_win, text=disclaimer, wraplength=400, justify="center", font=ctk.CTkFont(size=11, slant="italic"), text_color="#d9534f").pack(pady=(10, 20))

        ctk.CTkButton(about_win, text=self.tr("close_btn"), command=about_win.destroy, width=100, fg_color="#444", hover_color="#555").pack(pady=(10, 20))

    def tr(self, key):
        lang = self.user_data.get("language", "el")
        return TRANSLATIONS.get(lang, TRANSLATIONS["el"]).get(key, key)
        
    def change_language(self, choice):
        new_lang = "en" if choice == "English" else "el"
        if self.user_data.get("language") != new_lang:
            self.user_data["language"] = new_lang
            save_data(self.user_data)
            messagebox.showinfo("Επανεκκίνηση / Restart", "Παρακαλώ κάντε επανεκκίνηση της εφαρμογής (κλείσιμο και άνοιγμα) για να εφαρμοστεί πλήρως η αλλαγή γλώσσας.\n\nPlease restart the application to fully apply the language change.")

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

    def toggle_sidebar(self):
        if self.sidebar_frame.winfo_viewable():
            self.sidebar_frame.grid_remove()
            self.grid_columnconfigure(0, minsize=0)
        else:
            self.sidebar_frame.grid()
            self.grid_columnconfigure(0, minsize=380)

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

    def _build_data_pane(self, row, col):
        pane = ctk.CTkFrame(self.left_scroll_frame)
        pane.grid(row=row, column=col, padx=(20, 10), pady=10, sticky="nsew")
        
        ctk.CTkLabel(pane, text=self.tr("data_title"), font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", padx=15, pady=(15, 5))
        
        ctk.CTkLabel(pane, text=self.tr("select_stock"), font=ctk.CTkFont(size=12)).pack(anchor="w", padx=15)
        
        stock_ctrl_frame = ctk.CTkFrame(pane, fg_color="transparent")
        stock_ctrl_frame.pack(fill="x", padx=15, pady=(0, 15))
        self.stock_var = ctk.StringVar(value=self.tr("choose_stock_default"))
        self.stock_menu = ctk.CTkOptionMenu(stock_ctrl_frame, variable=self.stock_var, values=[self.tr("choose_stock_default")], command=self.on_stock_select)
        self.stock_menu.pack(side="left", fill="x", expand=True)
        
        ctk.CTkLabel(pane, text=self.tr("saved_urls"), font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=15, pady=(10, 5))
        self.urls_frame = ctk.CTkScrollableFrame(pane, height=150)
        self.urls_frame.pack(fill="x", padx=15, pady=5)
        
        self.url_rows = []
        for url_item in self.user_data.get("urls", []):
            self.add_url_row(url_item.get("title", ""), url_item.get("url", ""))
            
        url_btns_frame = ctk.CTkFrame(pane, fg_color="transparent")
        url_btns_frame.pack(anchor="w", padx=15, pady=2)
        
        self.add_url_btn = ctk.CTkButton(url_btns_frame, text=self.tr("add_url"), width=120, command=lambda: self.add_url_row("", ""))
        self.add_url_btn.pack(side="left", padx=(0, 5))
        
        self.save_urls_btn = ctk.CTkButton(url_btns_frame, text=self.tr("save_urls"), width=140, fg_color="#2b2b2b", hover_color="#3b3b3b", command=self.save_urls)
        self.save_urls_btn.pack(side="left")
            
        usage = self.user_data.get("api_usage", {})
        av_rem = max(0, 25 - usage.get("av", 0))
        fh_rem = max(0, 60 - usage.get("fh", 0))
        newsapi_rem = max(0, 100 - usage.get("newsapi", 0))
            
        self.av_var = ctk.IntVar(value=0)
        self.cb_av = ctk.CTkCheckBox(pane, text=f"{self.tr('include_av')}{av_rem}/25)", variable=self.av_var, command=self.on_av_toggle)
        self.cb_av.pack(anchor="w", padx=15, pady=8)
        ToolTip(self.cb_av, self.tr("tt_cb_av"))
        
        self.fh_var = ctk.IntVar(value=0)
        self.cb_fh = ctk.CTkCheckBox(pane, text=f"{self.tr('include_fh')}{fh_rem}/60)", variable=self.fh_var, command=self.on_fh_toggle)
        self.cb_fh.pack(anchor="w", padx=15, pady=8)
        ToolTip(self.cb_fh, self.tr("tt_cb_fh"))

        self.newsapi_var = ctk.IntVar(value=0)
        self.cb_newsapi = ctk.CTkCheckBox(pane, text=f"{self.tr('include_newsapi')}{newsapi_rem}/100)", variable=self.newsapi_var, command=self.on_newsapi_toggle)
        self.cb_newsapi.pack(anchor="w", padx=15, pady=(8, 2))
        ToolTip(self.cb_newsapi, self.tr("tt_cb_newsapi"))
        
        self.newsapi_filters_frame = ctk.CTkFrame(pane, fg_color="transparent")
        self.newsapi_filters_frame.pack(fill="x", padx=35, pady=(0, 8))
        self.newsapi_q_entry = ctk.CTkEntry(self.newsapi_filters_frame, placeholder_text=self.tr("newsapi_ph_q"), width=100, height=24, font=ctk.CTkFont(size=11))
        self.newsapi_q_entry.pack(side="left", padx=(0, 5))
        self.newsapi_lang_entry = ctk.CTkEntry(self.newsapi_filters_frame, placeholder_text=self.tr("newsapi_ph_lang"), width=70, height=24, font=ctk.CTkFont(size=11))
        self.newsapi_lang_entry.pack(side="left", padx=(0, 5))
        self.newsapi_date_entry = ctk.CTkEntry(self.newsapi_filters_frame, placeholder_text=self.tr("newsapi_ph_date"), width=110, height=24, font=ctk.CTkFont(size=11))
        self.newsapi_date_entry.pack(side="left")
        ToolTip(self.newsapi_q_entry, self.tr("tt_newsapi_q"))
        ToolTip(self.newsapi_lang_entry, self.tr("tt_newsapi_lang"))
        ToolTip(self.newsapi_date_entry, self.tr("tt_newsapi_date"))

        self.cb_news = ctk.CTkCheckBox(pane, text=self.tr("include_news"))
        self.cb_news.pack(anchor="w", padx=15, pady=8)
        ToolTip(self.cb_news, self.tr("tt_cb_news"))
        
        ctk.CTkLabel(pane, text=self.tr("analysis_format"), font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=15, pady=(15, 0))
        self.format_var = ctk.StringVar(value="Αναλυτικά")
        ctk.CTkRadioButton(pane, text=self.tr("format_detailed"), variable=self.format_var, value="Αναλυτικά").pack(anchor="w", padx=20, pady=5)
        ctk.CTkRadioButton(pane, text=self.tr("format_summary"), variable=self.format_var, value="Συνοπτικά").pack(anchor="w", padx=20, pady=5)
        
        prompt_header_frame = ctk.CTkFrame(pane, fg_color="transparent")
        prompt_header_frame.pack(fill="x", padx=15, pady=(15, 2))
        ctk.CTkLabel(prompt_header_frame, text=self.tr("extra_prompt"), font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")
        ctk.CTkButton(prompt_header_frame, text=self.tr("paste"), width=80, height=24, fg_color="#444", hover_color="#555", command=lambda: self.paste_to_textbox(self.extra_prompt_box)).pack(side="right")
        
        self.extra_prompt_box = ctk.CTkTextbox(pane, height=120, font=ctk.CTkFont(size=12))
        self.extra_prompt_box.pack(fill="x", padx=15, pady=(0, 15))
        ToolTip(self.extra_prompt_box, self.tr("tt_extra_prompt"))

        self.attached_files = []
        self.files_frame = ctk.CTkFrame(pane, fg_color="transparent")
        self.files_frame.pack(fill="x", padx=15, pady=(0, 15))
        
        attach_btn = ctk.CTkButton(self.files_frame, text=self.tr("add_file"), width=150, height=24, fg_color="#1f77b4", hover_color="#145c8f", command=self.attach_file)
        attach_btn.pack(side="left")
        
        self.clear_files_btn = ctk.CTkButton(self.files_frame, text="❌", width=24, height=24, fg_color="#d9534f", hover_color="#c9302c", command=self.clear_attached_files)
        
        self.files_list_label = ctk.CTkLabel(self.files_frame, text="", text_color="gray", font=ctk.CTkFont(size=11), wraplength=180)
        self.files_list_label.pack(side="left", padx=10)

        articles_header = ctk.CTkFrame(pane, fg_color="transparent")
        articles_header.pack(fill="x", padx=15, pady=(5, 2))
        ctk.CTkLabel(articles_header, text=self.tr("paste_articles"), font=ctk.CTkFont(size=12, weight="bold")).pack(side="left")

        self.article_boxes = []
        for i in range(3):
            art_frame = ctk.CTkFrame(pane, fg_color="transparent")
            art_frame.pack(fill="x", padx=15, pady=2)
            lbl_btn_frame = ctk.CTkFrame(art_frame, fg_color="transparent")
            lbl_btn_frame.pack(fill="x")
            ctk.CTkLabel(lbl_btn_frame, text=f"{self.tr('article_num')}{i+1}:", font=ctk.CTkFont(size=11)).pack(side="left")
            box = ctk.CTkTextbox(art_frame, height=60, font=ctk.CTkFont(size=11))
            paste_btn = ctk.CTkButton(lbl_btn_frame, text=self.tr("paste"), width=60, height=20, fg_color="#444", hover_color="#555", command=lambda b=box: self.paste_to_textbox(b))
            paste_btn.pack(side="right")
            box.pack(fill="x", pady=(2, 5))
            self.article_boxes.append(box)

        self.analyze_btn = ctk.CTkButton(pane, text=self.tr("start_analysis"), font=ctk.CTkFont(weight="bold"), fg_color="#d9534f", hover_color="#c9302c", command=self.fetch_data, height=40)
        self.analyze_btn.pack(fill="x", padx=15, pady=20)
        
        self.status_main = ctk.CTkLabel(pane, text="", text_color="orange")
        self.status_main.pack(pady=(0, 10))

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

    def add_url_row(self, title, url):
        f = ctk.CTkFrame(self.urls_frame, fg_color="transparent")
        f.pack(fill="x", pady=2)
        chk_var = ctk.IntVar(value=0)
        cb = ctk.CTkCheckBox(f, text="", variable=chk_var, width=20)
        cb.pack(side="left")
        t_entry = ctk.CTkEntry(f, placeholder_text="Τίτλος", width=80)
        t_entry.pack(side="left", padx=5)
        if title: t_entry.insert(0, title)
        ToolTip(t_entry, lambda: t_entry.get())
        u_entry = ctk.CTkEntry(f, placeholder_text="https://...", width=150)
        
        row_dict = {}
        def delete_row():
            if row_dict in self.url_rows: self.url_rows.remove(row_dict)
            f.destroy()
            
        del_btn = ctk.CTkButton(f, text="❌", width=25, fg_color="#d9534f", hover_color="#c9302c", command=delete_row)
        del_btn.pack(side="right", padx=(5, 0))
        
        paste_btn = ctk.CTkButton(f, text="📋", width=25, fg_color="#444", hover_color="#555", command=lambda: self.paste_to_entry(u_entry))
        paste_btn.pack(side="right", padx=(5, 0))
        ToolTip(paste_btn, self.tr("tt_paste_url"))
        
        u_entry.pack(side="left", fill="x", expand=True)
        if url: u_entry.insert(0, url)
        ToolTip(u_entry, lambda: u_entry.get())
        
        row_dict.update({"frame": f, "chk": chk_var, "title": t_entry, "url": u_entry})
        self.url_rows.append(row_dict)

    def save_urls(self):
        urls = []
        for row in self.url_rows:
            t = row["title"].get().strip()
            u = row["url"].get().strip()
            if u:
                urls.append({"title": t, "url": u})
        self.user_data["urls"] = urls
        save_data(self.user_data)
        self.status_main.configure(text="✅ Τα URLs αποθηκεύτηκαν!", text_color="green")

    def _build_overview_pane(self, row, col):
        pane = ctk.CTkFrame(self.right_scroll_frame, fg_color="transparent")
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
        
        time_frame = ctk.CTkFrame(pane, fg_color="transparent")
        time_frame.pack(fill="x", pady=5)
        ctk.CTkLabel(time_frame, text=self.tr("chart_timeframe"), font=ctk.CTkFont(size=12)).pack(side="left")
        self.time_var = ctk.StringVar(value="6mo")
        self.time_menu = ctk.CTkOptionMenu(time_frame, variable=self.time_var, values=["1mo", "3mo", "6mo", "1y", "5y"], command=self.on_time_period_change)
        self.time_menu.pack(side="left", padx=10)
        
        prices_frame = ctk.CTkFrame(pane, fg_color="transparent")
        prices_frame.pack(fill="x", pady=5)
        prices_frame.grid_columnconfigure((0,1,2), weight=1)
        self.l_yahoo = self.create_metric(prices_frame, "Yahoo Finance ⏱", "---", 0, 0, self.tr("tt_yahoo_price"))
        self.l_ft = self.create_metric(prices_frame, "Financial Times ⏱", "---", 0, 1, self.tr("tt_ft_price"))
        self.l_inv = self.create_metric(prices_frame, "Investing.com ⏱", "---", 0, 2, self.tr("tt_inv_price"))
        
        self.overview_tabs = ctk.CTkTabview(pane, height=650)
        self.overview_tabs.pack(fill="x", pady=2)
        
        self.tab_chart_name = self.tr("tab_chart")
        self.tab_news_name = self.tr("tab_news")
        self.tab_newsapi_name = self.tr("tab_newsapi")
        self.tab_pages_name = self.tr("tab_pages")
        
        self.overview_tabs.add(self.tab_chart_name)
        self.overview_tabs.add(self.tab_news_name)
        self.overview_tabs.add(self.tab_newsapi_name)
        self.overview_tabs.add(self.tab_pages_name)
        
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
        
        self.news_frame = ctk.CTkScrollableFrame(self.overview_tabs.tab(self.tab_news_name))
        self.news_frame.pack(fill="both", expand=True, padx=5, pady=5)
        ctk.CTkLabel(self.news_frame, text="Οι ειδήσεις θα εμφανιστούν εδώ.", text_color="gray").pack(pady=20)
        
        self.newsapi_frame = ctk.CTkScrollableFrame(self.overview_tabs.tab(self.tab_newsapi_name))
        self.newsapi_frame.pack(fill="both", expand=True, padx=5, pady=5)
        ctk.CTkLabel(self.newsapi_frame, text="Ενεργοποιήστε το NewsAPI αριστερά για προβολή.", text_color="gray").pack(pady=20)
        self.newsapi_checkboxes = []
        
        self.pages_frame = ctk.CTkFrame(self.overview_tabs.tab(self.tab_pages_name), fg_color="transparent")
        self.pages_frame.pack(fill="both", expand=True, padx=20, pady=20)
        ctk.CTkLabel(self.pages_frame, text="Επιλέξτε μια μετοχή για να δείτε τους συνδέσμους.", text_color="gray").pack(pady=20)
        
        ctk.CTkLabel(pane, text=self.tr("stats_title"), font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(10, 2))
        stats_frame = ctk.CTkFrame(pane, fg_color="transparent")
        stats_frame.pack(fill="x", pady=2)
        stats_frame.grid_columnconfigure((0,1,2,3), weight=1)
        self.l_mcap = self.create_metric(stats_frame, "Market Cap", "---", 0, 0, self.tr("tt_mcap"))
        self.l_pe = self.create_metric(stats_frame, "P/E Ratio", "---", 0, 1, self.tr("tt_pe"))
        self.l_div = self.create_metric(stats_frame, "Div Yield", "---", 0, 2, self.tr("tt_div"))
        self.l_beta = self.create_metric(stats_frame, "Beta", "---", 0, 3, self.tr("tt_beta"))
        
        ctk.CTkLabel(pane, text=self.tr("health_title"), font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(10, 2))
        health_frame = ctk.CTkFrame(pane, fg_color="transparent")
        health_frame.pack(fill="x", pady=2)
        health_frame.grid_columnconfigure((0,1,2,3), weight=1)
        self.l_rev_growth = self.create_metric(health_frame, "Rev Growth", "---", 0, 0, self.tr("tt_rev_growth"))
        self.l_roe = self.create_metric(health_frame, "ROE", "---", 0, 1, self.tr("tt_roe"))
        self.l_op_margin = self.create_metric(health_frame, "Op Margin", "---", 0, 2, self.tr("tt_op_margin"))
        self.l_dte = self.create_metric(health_frame, "Debt/Eq", "---", 0, 3, self.tr("tt_dte"))
        self.l_fcf = self.create_metric(health_frame, "Free Cash Flow", "---", 1, 0, self.tr("tt_fcf"))
        
        ctk.CTkLabel(pane, text=self.tr("tech_title"), font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(10, 2))
        tech_frame = ctk.CTkFrame(pane, fg_color="transparent")
        tech_frame.pack(fill="x", pady=2)
        tech_frame.grid_columnconfigure((0,1,2,3), weight=1)
        self.l_rsi = self.create_metric(tech_frame, "RSI (14)", "---", 0, 0, self.tr("tt_rsi"))
        self.l_macd = self.create_metric(tech_frame, "MACD", "---", 0, 1, self.tr("tt_macd"))
        self.l_sma20 = self.create_metric(tech_frame, "SMA 20", "---", 0, 2, self.tr("tt_sma20"))
        self.l_sma50 = self.create_metric(tech_frame, "SMA 50", "---", 0, 3, self.tr("tt_sma50"))

        ctk.CTkLabel(pane, text=self.tr("av_title"), font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(10, 2))
        av_frame = ctk.CTkFrame(pane, fg_color="transparent")
        av_frame.pack(fill="x", pady=2)
        av_frame.grid_columnconfigure((0,1,2), weight=1)
        self.l_av_pe = self.create_metric(av_frame, "PE Ratio (AV)", "---", 0, 0, self.tr("tt_av_pe"))
        self.l_av_div = self.create_metric(av_frame, "Div Yield (AV)", "---", 0, 1, self.tr("tt_av_div"))
        self.l_av_eps = self.create_metric(av_frame, "EPS (AV)", "---", 0, 2, self.tr("tt_av_eps"))

        ctk.CTkLabel(pane, text=self.tr("fh_title"), font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(10, 2))
        fh_frame = ctk.CTkFrame(pane, fg_color="transparent")
        fh_frame.pack(fill="x", pady=2)
        fh_frame.grid_columnconfigure((0,1,2,3), weight=1)
        self.l_fh_cur = self.create_metric(fh_frame, self.tr("fh_lbl_cur"), "---", 0, 0, self.tr("tt_fh_cur"))
        self.l_fh_open = self.create_metric(fh_frame, self.tr("fh_lbl_open"), "---", 0, 1, self.tr("tt_fh_open"))
        self.l_fh_high = self.create_metric(fh_frame, self.tr("fh_lbl_high"), "---", 0, 2, self.tr("tt_fh_high"))
        self.l_fh_low = self.create_metric(fh_frame, self.tr("fh_lbl_low"), "---", 0, 3, self.tr("tt_fh_low"))

        ctk.CTkLabel(pane, text=self.tr("ai_analysis_title"), font=ctk.CTkFont(size=13, weight="bold")).pack(anchor="w", pady=(15, 2))
        self.result_textbox = ctk.CTkTextbox(pane, wrap="word", font=ctk.CTkFont(size=14), height=300)
        self.result_textbox.pack(fill="x", expand=False, pady=5)
        
        actions_frame = ctk.CTkFrame(pane, fg_color="transparent")
        actions_frame.pack(anchor="e", pady=5)
        
        print_btn = ctk.CTkButton(actions_frame, text=self.tr("print"), fg_color="#1f77b4", hover_color="#145c8f", command=self.print_analysis)
        print_btn.pack(side="left", padx=(0, 10))
        
        export_btn = ctk.CTkButton(actions_frame, text=self.tr("export_word"), fg_color="#28a745", hover_color="#218838", command=self.export_to_word)
        export_btn.pack(side="left")

    def redraw_current_chart(self):
        if hasattr(self, 'current_df') and self.current_df is not None:
            self.draw_chart(self.current_df)

    def _build_history_pane(self, row, col):
        pane = ctk.CTkFrame(self.left_scroll_frame, fg_color="transparent")
        pane.grid(row=row, column=col, padx=(20, 10), pady=(10, 40), sticky="nsew")
        
        ctk.CTkLabel(pane, text=self.tr("history_title"), font=ctk.CTkFont(size=16, weight="bold")).pack(anchor="w", pady=(0, 10))
        
        self.hist_frame = ctk.CTkFrame(pane)
        self.hist_frame.pack(fill="x")
        
        self.update_history_ui()

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
        self.result_textbox.delete("1.0", "end")
        self.result_textbox.insert("1.0", item.get("text", ""))
        self.overview_title.configure(text=f"{item.get('stock', '')} - Ανάγνωση από Ιστορικό")
        self.status_main.configure(text="✅ Φορτώθηκε από το ιστορικό", text_color="green")

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

    def on_av_toggle(self):
        if self.av_var.get() == 1:
            self._trigger_av_fetch()
        else:
            self.l_av_pe.configure(text="---")
            self.l_av_div.configure(text="---")
            self.l_av_eps.configure(text="---")
            self.current_av_context = ""

    def on_fh_toggle(self):
        if self.fh_var.get() == 1:
            self._trigger_fh_fetch()
        else:
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

    def on_newsapi_toggle(self):
        if self.newsapi_var.get() == 1:
            self._trigger_newsapi_fetch()
        else:
            for widget in self.newsapi_frame.winfo_children():
                widget.destroy()
            ctk.CTkLabel(self.newsapi_frame, text="Ενεργοποιήστε το NewsAPI αριστερά για προβολή.", text_color="gray").pack(pady=20)
            self.newsapi_checkboxes = []

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

        if news_data.get("error"):
            self.status_main.configure(text=f"⚠️ Σφάλμα NewsAPI: {news_data.get('error')}", text_color="orange")
            ctk.CTkLabel(self.newsapi_frame, text=f"Σφάλμα: {news_data.get('error')}", text_color="red").pack(pady=20)
            self.newsapi_var.set(0)
            return
            
        self.user_data["api_usage"]["newsapi"] = self.user_data.get("api_usage", {}).get("newsapi", 0) + 1
        save_data(self.user_data)
        self._sync_api_usage()

        news_list = news_data.get("news", [])
        if not news_list:
            ctk.CTkLabel(self.newsapi_frame, text="Δεν βρέθηκαν ειδήσεις στο NewsAPI.", text_color="gray").pack(pady=20)
            return

        for article in news_list:
            f = ctk.CTkFrame(self.newsapi_frame, fg_color="transparent")
            f.pack(fill="x", pady=2, padx=2)
            
            chk_var = ctk.IntVar(value=0)
            cb = ctk.CTkCheckBox(f, text="", variable=chk_var, width=20)
            cb.pack(side="left", anchor="n", pady=(2, 0), padx=(0, 5))
            self.newsapi_checkboxes.append((chk_var, article))
            
            text_f = ctk.CTkFrame(f, fg_color="transparent")
            text_f.pack(side="left", fill="x", expand=True)
            
            title = article.get("title", "Χωρίς Τίτλο")
            url = article.get("url", "")
            source = article.get("source", "")
            date = article.get("date", "")
            
            title_lbl = ctk.CTkLabel(text_f, text=f"📰 {title}", font=ctk.CTkFont(weight="bold", size=12), text_color="#1f77b4", cursor="hand2", anchor="w", justify="left", wraplength=550)
            title_lbl.pack(anchor="w")
            if url:
                title_lbl.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
                
            ctk.CTkLabel(text_f, text=f"Πηγή: {source} | Ημ/νία: {date}", font=ctk.CTkFont(size=10), text_color="gray", anchor="w").pack(anchor="w")
            
            desc = article.get("description", "")
            if desc:
                ctk.CTkLabel(text_f, text=desc, font=ctk.CTkFont(size=11), anchor="w", justify="left", wraplength=550).pack(anchor="w", pady=(0, 4))

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

    def _fetch_overview_data_thread(self, stock_data):
        yahoo_sym = stock_data.get("Yahoo")
        ft_sym = stock_data.get("FT")
        inv_sym = stock_data.get("Investing")
        period = self.time_var.get()
        
        res_yahoo = stock_fetcher.get_stock_data(yahoo_sym, period) if yahoo_sym else {"error": "No Yahoo Symbol"}
        ft_price = stock_fetcher.get_ft_price(ft_sym) if ft_sym else "N/A"
        inv_price = stock_fetcher.get_investing_price(inv_sym) if inv_sym else "N/A"
        
        # Ανάκτηση ειδήσεων
        symbols_list = [yahoo_sym, ft_sym, inv_sym]
        news_data = stock_fetcher.get_stock_news(stock_data.get("Ονομασία", yahoo_sym), symbols=symbols_list)
        
        self.after(0, self._update_overview_ui, res_yahoo, ft_price, inv_price, news_data)

    def _update_overview_ui(self, res_yahoo, ft_price, inv_price, news_data=None):
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
            self.l_rev_growth.configure(text=res_yahoo.get("rev_growth", "N/A"))
            self.l_roe.configure(text=res_yahoo.get("roe", "N/A"))
            self.l_op_margin.configure(text=res_yahoo.get("op_margin", "N/A"))
            self.l_dte.configure(text=res_yahoo.get("dte", "N/A"))
            self.l_fcf.configure(text=res_yahoo.get("fcf", "N/A"))
            if "df" in res_yahoo:
                self.draw_chart(res_yahoo["df"])
                
            self.website_url = res_yahoo.get("website", "")
            if self.website_url:
                self.website_link_label.configure(text=f"🔗 {res_yahoo.get('domain', 'Website')}")
                self.website_link_label.pack(side="left", padx=(20, 10))
                self.website_cb.pack(side="left")
            else:
                self.website_link_label.pack_forget()
                self.website_cb.pack_forget()
        else:
            self.l_yahoo.configure(text="Σφάλμα")
            self.website_link_label.pack_forget()
            self.website_cb.pack_forget()
            
        self.l_ft.configure(text=ft_price)
        self.l_inv.configure(text=inv_price)
        
        # Ενημέρωση Ειδήσεων
        for widget in self.news_frame.winfo_children():
            widget.destroy()

        self.news_checkboxes = []

        if not news_data:
            ctk.CTkLabel(self.news_frame, text="Δεν βρέθηκαν πρόσφατες ειδήσεις.", text_color="gray").pack(pady=20)
        else:
            for article in news_data:
                f = ctk.CTkFrame(self.news_frame, fg_color="transparent")
                f.pack(fill="x", pady=2, padx=2)
                
                chk_var = ctk.IntVar(value=0)
                cb = ctk.CTkCheckBox(f, text="", variable=chk_var, width=20)
                cb.pack(side="left", anchor="n", pady=(2, 0), padx=(0, 5))
                self.news_checkboxes.append((chk_var, article))
                
                text_f = ctk.CTkFrame(f, fg_color="transparent")
                text_f.pack(side="left", fill="x", expand=True)
                
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

    def fetch_data(self):
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
                if row["chk"].get() == 1:
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

        # Εκτέλεση του AI σε ξεχωριστό Thread
        threading.Thread(target=self.run_ai, args=(selected_name, context, used_sources, final_extra_prompt), daemon=True).start()

    def draw_chart(self, df):
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
        
        # Μετατροπή του δείκτη του ποντικιού σε "χεράκι" και σύνδεση του κλικ
        widget.configure(cursor="hand2")
        fig.canvas.mpl_connect('button_press_event', lambda event: self.show_large_chart(df))

    def show_large_chart(self, df):
        """Ανοίγει το γράφημα σε νέο μεγάλο παράθυρο με εργαλεία περιήγησης."""
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
        provider = self.ai_provider_menu.get()
        selected_model = self.ai_model_var.get()
        temperature = self.temperature_slider.get()

        if not selected_model or selected_model in ["Φόρτωση...", "Απαιτείται API Key", "Κανένα διαθέσιμο μοντέλο", "Σφάλμα φόρτωσης"]:
            self.after(0, self.update_ai_result, "❌ Παρακαλώ επιλέξτε ένα έγκυρο μοντέλο AI.", "red")
            return

        api_key = self.user_data.get("api_key")
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

    def export_to_word(self):
        text = self.result_textbox.get("1.0", "end-1c").strip()
        if not text:
            self.status_main.configure(text="❌ Δεν υπάρχει κείμενο για εξαγωγή!", text_color="red")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".docx",
            filetypes=[("Word Document", "*.docx")],
            title="Αποθήκευση Ανάλυσης",
            initialfile=f"Ανάλυση_{self.stock_var.get().replace(' ', '_')}.docx"
        )

        if file_path:
            success, error = document_exporter.save_to_word(text, self.stock_var.get(), file_path)
            if success:
                self.status_main.configure(text="✅ Εξήχθη επιτυχώς σε Word!", text_color="green")
            else:
                self.status_main.configure(text=f"❌ Σφάλμα κατά την εξαγωγή: {error}", text_color="red")

    def print_analysis(self):
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
        save_data(self.user_data)
        self.status_label.configure(text="✅ Αποθηκεύτηκε!", text_color="green")
        if self.ai_provider_menu.get() == "Gemini (Cloud)":
            self.update_models()

    def update_temp_label(self, value):
        self.temp_val_label.configure(text=f"{value:.1f}")

    def save_stock(self):
        name = self.stock_name_entry.get().strip()
        yahoo = self.stock_yahoo_entry.get().strip().upper()
        ft = self.stock_ft_entry.get().strip()
        inv = self.stock_inv_entry.get().strip()
        
        if not name or not yahoo:
            self.status_label.configure(text="❌ Συμπληρώστε Όνομα & Yahoo!", text_color="red")
            return
            
        watchlist = self.user_data.get("watchlist", [])
        
        if hasattr(self, "editing_stock_index") and self.editing_stock_index is not None:
            watchlist[self.editing_stock_index] = {"Ονομασία": name, "Yahoo": yahoo, "FT": ft, "Investing": inv}
            self.editing_stock_index = None
            self.status_label.configure(text=f"✅ Τροποποιήθηκε: {name}", text_color="green")
        else:
            if any(s.get("Ονομασία") == name for s in watchlist):
                self.status_label.configure(text="❌ Η μετοχή υπάρχει ήδη!", text_color="red")
                return
            watchlist.append({"Ονομασία": name, "Yahoo": yahoo, "FT": ft, "Investing": inv})
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
            self.stock_name_entry.delete(0, 'end')
            self.stock_name_entry.insert(0, item.get("Ονομασία", ""))
            self.stock_yahoo_entry.delete(0, 'end')
            self.stock_yahoo_entry.insert(0, item.get("Yahoo", ""))
            self.stock_ft_entry.delete(0, 'end')
            self.stock_ft_entry.insert(0, item.get("FT", ""))
            self.stock_inv_entry.delete(0, 'end')
            self.stock_inv_entry.insert(0, item.get("Investing", ""))
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

        for widget in self.newsapi_frame.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.newsapi_frame, text="Ενεργοποιήστε το NewsAPI αριστερά για προβολή.", text_color="gray").pack(pady=20)
        self.newsapi_checkboxes = []
        
        for widget in self.pages_frame.winfo_children():
            widget.destroy()
        ctk.CTkLabel(self.pages_frame, text="Επιλέξτε μια μετοχή για να δείτε τους συνδέσμους.", text_color="gray").pack(pady=20)
        self.page_checkboxes = []
        
        labels_to_reset = [
            self.l_yahoo, self.l_ft, self.l_inv, self.l_mcap, self.l_pe, self.l_div, self.l_beta,
            self.l_rsi, self.l_macd, self.l_sma20, self.l_sma50, self.l_av_pe, self.l_av_div, self.l_av_eps,
            self.l_fh_cur, self.l_fh_open, self.l_fh_high, self.l_fh_low,
            self.l_rev_growth, self.l_roe, self.l_op_margin, self.l_dte, self.l_fcf
        ]
        for lbl in labels_to_reset:
            lbl.configure(text="---")
            
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
        self.status_label.configure(text="✅ Τα προσωρινά δεδομένα διαγράφηκαν!", text_color="green")

    def clear_all_data(self):
        confirm = messagebox.askyesno("Επιβεβαίωση", "Είστε σίγουροι ότι θέλετε να διαγράψετε ΟΛΑ τα δεδομένα της εφαρμογής;\n\nΑυτή η ενέργεια θα διαγράψει το Ιστορικό, την Watchlist, τα API Keys και τα αποθηκευμένα URLs και δεν μπορεί να αναιρεθεί.")
        if confirm:
            self.user_data = {
                "api_key": "", "av_api_key": "", "finnhub_api_key": "", "newsapi_key": "",
                "watchlist": [], "urls": [], "history": [],
                "api_usage": {"date": datetime.date.today().isoformat(), "av": 0, "fh": 0, "newsapi": 0}
            }
            save_data(self.user_data)
            
            self.api_key_entry.delete(0, 'end')
            self.av_key_entry.delete(0, 'end')
            self.finnhub_key_entry.delete(0, 'end')
            self.newsapi_key_entry.delete(0, 'end')
            
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

        for idx, item in enumerate(self.user_data.get("watchlist", [])):
            name = item.get("Ονομασία", "N/A")
            
            # Αφού τώρα υπάρχει χώρος, επιτρέπουμε μεγαλύτερα ονόματα
            display_name = name if len(name) <= 22 else name[:20] + ".."
            lbl_name = ctk.CTkLabel(self.watchlist_frame, text=display_name, font=ctk.CTkFont(size=12), anchor="w")
            lbl_name.grid(row=idx+1, column=0, padx=2, pady=2, sticky="we")
            lbl_name.bind("<Double-Button-1>", lambda e, n=name: self._select_and_fetch(n))
            ToolTip(lbl_name, name)

            order_frame = ctk.CTkFrame(self.watchlist_frame, fg_color="transparent")
            order_frame.grid(row=idx+1, column=1, padx=2, pady=2, sticky="e")
            
            up_btn = ctk.CTkButton(order_frame, text="▲", width=20, height=20, fg_color="#444", hover_color="#555", command=lambda i=idx: self.move_stock_up(i))
            up_btn.pack(side="left", padx=1)
            if idx == 0: up_btn.configure(state="disabled")
                
            down_btn = ctk.CTkButton(order_frame, text="▼", width=20, height=20, fg_color="#444", hover_color="#555", command=lambda i=idx: self.move_stock_down(i))
            down_btn.pack(side="left", padx=1)
            if idx == len(self.user_data.get("watchlist", [])) - 1: down_btn.configure(state="disabled")

            edit_btn = ctk.CTkButton(self.watchlist_frame, text="✏️", width=25, height=20, fg_color="#f0ad4e", text_color="black", hover_color="#ec971f", command=lambda i=idx: self.edit_stock(i))
            edit_btn.grid(row=idx+1, column=2, padx=2, pady=2, sticky="e")

            del_btn = ctk.CTkButton(self.watchlist_frame, text="❌", width=25, height=20, fg_color="#d9534f", hover_color="#c9302c", command=lambda s=name: self.delete_stock(s))
            del_btn.grid(row=idx+1, column=3, padx=2, pady=2, sticky="e")

    def update_models(self, selected_provider=None):
        provider = selected_provider or self.ai_provider_menu.get()
        self.ai_model_var.set("Φόρτωση...")
        self.ai_model_menu.configure(values=["Φόρτωση..."])
        threading.Thread(target=self._fetch_models_thread, args=(provider,), daemon=True).start()

    def _fetch_models_thread(self, provider):
        api_key = self.user_data.get("api_key")
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