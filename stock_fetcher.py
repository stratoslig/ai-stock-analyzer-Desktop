import yfinance as yf
import pandas as pd
import pandas_ta as ta
import logging
import cloudscraper
from bs4 import BeautifulSoup
from ddgs import DDGS
import requests
import trafilatura

logger = logging.getLogger(__name__)

def get_stock_info(symbol):
    """Αντλεί βασικές πληροφορίες για την προσθήκη νέας μετοχής."""
    try:
        info = yf.Ticker(symbol).info
        return info.get("shortName") or info.get("longName") or symbol
    except Exception as e:
        logger.error(f"Σφάλμα ανάκτησης πληροφοριών για {symbol}: {e}", exc_info=True)
        return None

def get_stock_data(symbol, period="6mo"):
    """Αντλεί ιστορικά δεδομένα και υπολογίζει τους τεχνικούς δείκτες."""
    try:
        ticker = yf.Ticker(symbol)
        hist = ticker.history(period=period)
        info = ticker.info

        if len(hist) == 0:
            return {"error": "Δεν βρέθηκαν ιστορικά δεδομένα."}

        cp = hist['Close'].iloc[-1]
        pp = hist['Close'].iloc[-2] if len(hist) >= 2 else cp
        pct_change = ((cp - pp) / pp) * 100 if pp != 0 else 0.0

        hist.ta.rsi(length=14, append=True)
        hist.ta.macd(append=True)
        hist.ta.sma(length=20, append=True)
        hist.ta.sma(length=50, append=True)
        hist.ta.ema(length=20, append=True)
        hist.ta.ema(length=50, append=True)
        
        latest = hist.iloc[-1]
        mcap = info.get("marketCap", 0)
        pe = info.get('trailingPE', 'N/A')
        div = info.get("dividendYield")
        if div is None:
            div = info.get("trailingAnnualDividendYield")
        beta = info.get('beta', 'N/A')
        website = info.get("website", "")
        domain = website.replace("https://", "").replace("http://", "").replace("www.", "").split('/')[0] if website else ""
        
        rev_growth = info.get("revenueGrowth")
        roe = info.get("returnOnEquity")
        dte = info.get("debtToEquity")
        fcf = info.get("freeCashflow")
        op_margin = info.get("operatingMargins")

        forward_pe = info.get("forwardPE", "N/A")
        ev_ebitda = info.get("enterpriseToEbitda", "N/A")
        pb_ratio = info.get("priceToBook", "N/A")
        
        # Υπολογισμός Debt / EBITDA (αν υπάρχουν)
        total_debt = info.get("totalDebt")
        ebitda = info.get("ebitda")
        debt_ebitda = (total_debt / ebitda) if isinstance(total_debt, (int, float)) and isinstance(ebitda, (int, float)) and ebitda != 0 else "N/A"

        fmt_rev_growth = f"{rev_growth * 100:.2f}%" if isinstance(rev_growth, (int, float)) else "N/A"
        fmt_roe = f"{roe * 100:.2f}%" if isinstance(roe, (int, float)) else "N/A"
        fmt_op_margin = f"{op_margin * 100:.2f}%" if isinstance(op_margin, (int, float)) else "N/A"
        fmt_dte = f"{dte:.2f}" if isinstance(dte, (int, float)) else "N/A"
        
        fmt_fwd_pe = f"{forward_pe:.2f}" if isinstance(forward_pe, (int, float)) else "N/A"
        fmt_ev_ebitda = f"{ev_ebitda:.2f}" if isinstance(ev_ebitda, (int, float)) else "N/A"
        fmt_pb = f"{pb_ratio:.2f}" if isinstance(pb_ratio, (int, float)) else "N/A"
        fmt_debt_ebitda = f"{debt_ebitda:.2f}" if isinstance(debt_ebitda, (int, float)) else "N/A"

        if isinstance(fcf, (int, float)):
            fmt_fcf = f"${fcf/1e9:.2f}B" if abs(fcf) >= 1e9 else f"${fcf/1e6:.2f}M"
        else:
            fmt_fcf = "N/A"

        res = {
            "price": f"${cp:.2f} ({pct_change:.2f}%)",
            "mcap": f"${mcap/1e9:.2f}B" if mcap >= 1e9 else f"${mcap/1e6:.2f}M",
            "pe": f"{pe:.2f}" if isinstance(pe, (int, float)) else "N/A",
            "div": (f"{div:.2f}%" if div >= 1 else f"{div * 100:.2f}%") if isinstance(div, (int, float)) else "N/A",
            "beta": f"{beta:.2f}" if isinstance(beta, (int, float)) else "N/A",
            "rsi": f"{latest.get('RSI_14'):.2f}" if pd.notna(latest.get('RSI_14')) else "N/A",
            "macd": f"{latest.get('MACD_12_26_9'):.2f}" if pd.notna(latest.get('MACD_12_26_9')) else "N/A",
            "sma20": f"{latest.get('SMA_20'):.2f}" if pd.notna(latest.get('SMA_20')) else "N/A",
            "sma50": f"{latest.get('SMA_50'):.2f}" if pd.notna(latest.get('SMA_50')) else "N/A",
            "rev_growth": fmt_rev_growth,
            "roe": fmt_roe,
            "op_margin": fmt_op_margin,
            "dte": fmt_dte,
            "fcf": fmt_fcf,
            "forward_pe": fmt_fwd_pe,
            "ev_ebitda": fmt_ev_ebitda,
            "pb_ratio": fmt_pb,
            "debt_ebitda": fmt_debt_ebitda,
        }
        res["domain"] = domain
        res["website"] = website
        res["context"] = f"[ΒΑΣΙΚΑ ΔΕΔΟΜΕΝΑ & ΤΕΧΝΙΚΟΙ ΔΕΙΚΤΕΣ]\nΤιμή Κλεισίματος: {cp:.2f} | P/E: {pe}\nRSI(14): {res['rsi']} | MACD: {res['macd']} | SMA20: {res['sma20']} | SMA50: {res['sma50']}\n\n[ΟΙΚΟΝΟΜΙΚΗ ΥΓΕΙΑ & ΑΠΟΔΟΣΗ]\nRevenue Growth: {fmt_rev_growth} | ROE: {fmt_roe} | Operating Margin: {fmt_op_margin}\nDebt to Equity: {fmt_dte} | Free Cash Flow: {fmt_fcf}\n\n[ΑΠΟΤΙΜΗΣΗ & ΕΠΙΠΛΕΟΝ ΔΕΙΚΤΕΣ]\nForward P/E: {fmt_fwd_pe} | EV/EBITDA: {fmt_ev_ebitda} | Price/Book: {fmt_pb} | Debt/EBITDA: {fmt_debt_ebitda}"
        res["df"] = hist
        return res
    except Exception as e:
        logger.error(f"Σφάλμα λήψης ιστορικών δεδομένων {symbol}: {e}", exc_info=True)
        return {"error": f"Σφάλμα δεδομένων: {e}"}

def get_ft_price(symbol):
    """Αντλεί την τρέχουσα τιμή από το Financial Times."""
    if not symbol:
        return "N/A"
    try:
        scraper = cloudscraper.create_scraper()
        if symbol.startswith("http"):
            url = symbol
        else:
            url = f"https://markets.ft.com/data/equities/tearsheet/summary?s={symbol}"
        response = scraper.get(url, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        el = soup.select_one('.mod-ui-data-list__value')
        return el.text.strip() if el else "N/A"
    except Exception as e:
        logger.error(f"Σφάλμα ανάκτησης FT για {symbol}: {e}")
        return "Σφάλμα"

def get_investing_price(symbol):
    """Αντλεί την τρέχουσα τιμή από το Investing.com."""
    if not symbol:
        return "N/A"
    try:
        # Προσθήκη προφίλ browser για αποφυγή μπλοκαρίσματος από το Cloudflare
        scraper = cloudscraper.create_scraper(browser={'browser': 'chrome', 'platform': 'windows', 'mobile': False})
        
        if symbol.startswith("http"):
            url = symbol
        elif "/" in symbol:
            url = f"https://gr.investing.com/{symbol}"
        else:
            url = f"https://gr.investing.com/equities/{symbol}"
        
        response = scraper.get(url, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        
        # Πολλαπλοί selectors επειδή το Investing αλλάζει συχνά το DOM του
        el = soup.select_one('[data-test="instrument-price-last"]') or soup.select_one('#last_last') or soup.select_one('.instrument-price_instrument-price__3uw25') or soup.select_one('.text-5xl')
        
        return el.text.strip() if el else "N/A"
    except Exception as e:
        logger.error(f"Σφάλμα ανάκτησης Investing για {symbol}: {e}")
        return "Σφάλμα"

def get_stock_news(query, symbols=None, max_results=10):
    """Αντλεί πρόσφατες ειδήσεις μέσω DuckDuckGo (Ελληνικά και Αγγλικά)."""
    if not query:
        return []
    try:
        ddgs = DDGS()
        unique_results = []
        seen_urls = set()
        symbols = symbols or []
        
        # Καθαρισμός του ονόματος της εταιρείας για καλύτερο φιλτράρισμα
        q_clean = query.lower().replace(" inc.", "").replace(" inc", "").replace(" corp.", "").replace(" corp", "").replace(" ltd.", "").replace(" ltd", "").strip()
        main_word = q_clean.split()[0] if q_clean else query.lower()
        
        # Λέξεις-κλειδιά για φιλτράρισμα (Όνομα και Σύμβολα)
        target_keywords = {main_word, q_clean}
        for s in symbols:
            if s and isinstance(s, str) and s != "N/A":
                s_clean = s.lower().strip()
                target_keywords.add(s_clean)
                if '.' in s_clean: # π.χ. EUROB.AT -> eurob
                    target_keywords.add(s_clean.split('.')[0])
        
        # Αφαίρεση πολύ μικρών λέξεων (αποφυγή false-positives), εκτός αν είναι σύμβολα
        target_keywords = {k for k in target_keywords if len(k) > 1}

        def add_if_relevant(res_list):
            if not res_list: return
            for r in res_list:
                url = r.get("url")
                title_body = (r.get("title", "") + " " + r.get("body", "")).lower()
                
                # Το όνομα της εταιρείας ή κάποιο σύμβολό της πρέπει να υπάρχει στον τίτλο ή στο σώμα
                is_relevant = any(kw in title_body for kw in target_keywords)
                
                if url not in seen_urls and is_relevant:
                    seen_urls.add(url)
                    unique_results.append(r)

        # 1. Αναζήτηση στα Ελληνικά (Μεγαλύτερο χρονικό εύρος 'y' λόγω μικρότερου όγκου ειδήσεων)
        try:
            gr_results = ddgs.news(f"{q_clean} μετοχή", region="gr-el", timelimit="y", max_results=max_results)
            add_if_relevant(gr_results)
            
            # Αν δεν βρέθηκαν αρκετά ελληνικά άρθρα, κάνουμε ευρύτερη αναζήτηση
            if len(unique_results) < 2:
                gr_fallback = ddgs.news(q_clean, region="gr-el", timelimit="y", max_results=max_results)
                add_if_relevant(gr_fallback)
                
            # Αναζήτηση με το σύμβολο (αν υπάρχει)
            if len(unique_results) < 5 and symbols:
                first_sym = symbols[0] if symbols[0] and symbols[0] != "N/A" else (symbols[1] if len(symbols)>1 and symbols[1] else "")
                if first_sym:
                    clean_sym = first_sym.split('.')[0] if '.' in first_sym else first_sym
                    gr_sym_results = ddgs.news(f"{clean_sym} μετοχή", region="gr-el", timelimit="y", max_results=max_results)
                    add_if_relevant(gr_sym_results)
        except Exception:
            pass
            
        # 2. Αναζήτηση στα Αγγλικά (Επέκταση χρονικού περιθωρίου σε 'y' αντί για 'm')
        try:
            en_results = ddgs.news(f'"{q_clean}" stock OR earnings', region="wt-wt", timelimit="y", max_results=max_results)
            add_if_relevant(en_results)
            
            # Αν βρήκαμε πολύ λίγα, κάνουμε μια ευρύτερη αναζήτηση (fallback)
            if len(unique_results) < 6:
                en_results_fallback = ddgs.news(f"{main_word} stock", region="wt-wt", timelimit="y", max_results=max_results)
                add_if_relevant(en_results_fallback)
                
            # Αναζήτηση με το σύμβολο
            if len(unique_results) < 10 and symbols:
                first_sym = symbols[0] if symbols[0] and symbols[0] != "N/A" else ""
                if first_sym:
                    clean_sym = first_sym.split('.')[0] if '.' in first_sym else first_sym
                    en_sym_results = ddgs.news(f"{clean_sym} stock", region="wt-wt", timelimit="y", max_results=max_results)
                    add_if_relevant(en_sym_results)
        except Exception:
            pass
            
        # Ταξινόμηση ανά ημερομηνία (από το πιο πρόσφατο στο παλαιότερο)
        unique_results.sort(key=lambda x: x.get("date", ""), reverse=True)
        
        return unique_results[:max_results]
    except Exception as e:
        logger.error(f"Σφάλμα ανάκτησης ειδήσεων για {query}: {e}", exc_info=True)
        return []

def get_alpha_vantage_data(symbol, api_key):
    """Αντλεί θεμελιώδη δεδομένα από το Alpha Vantage."""
    if not api_key:
        return {"error": "Missing API Key"}
    try:
        url = f"https://www.alphavantage.co/query?function=OVERVIEW&symbol={symbol}&apikey={api_key}"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        if "Symbol" not in data:
            return {"error": "Δεν βρέθηκαν δεδομένα ή εξαντλήθηκε το όριο κλήσεων."}
        return {
            "pe": data.get("PERatio", "N/A"),
            "eps": data.get("EPS", "N/A"),
            "div": data.get("DividendYield", "N/A"),
            "target": data.get("AnalystTargetPrice", "N/A"),
            "52high": data.get("52WeekHigh", "N/A"),
            "52low": data.get("52WeekLow", "N/A")
        }
    except Exception as e:
        logger.error(f"Σφάλμα Alpha Vantage: {e}")
        return {"error": str(e)}

def get_finnhub_data(symbol, api_key):
    """Αντλεί δεδομένα πραγματικού χρόνου από το Finnhub."""
    if not api_key:
        return {"error": "Missing API Key"}
    try:
        url = f"https://finnhub.io/api/v1/quote?symbol={symbol}&token={api_key}"
        resp = requests.get(url, timeout=10)
        data = resp.json()
        # Το Finnhub επιστρέφει 'c' για Current Price. Αν δεν υπάρχει, απέτυχε.
        if "c" not in data or data["c"] == 0:
            return {"error": "Σφάλμα ανάκτησης Finnhub"}
        return {
            "current": data.get("c", "N/A"),
            "high": data.get("h", "N/A"),
            "low": data.get("l", "N/A"),
            "open": data.get("o", "N/A"),
            "prev_close": data.get("pc", "N/A")
        }
    except Exception as e:
        logger.error(f"Σφάλμα Finnhub: {e}")
        return {"error": str(e)}

def get_newsapi_data(query, api_key, extra_query="", language="", from_date=""):
    """Αντλεί ειδήσεις από το NewsAPI.org."""
    if not api_key:
        return {"error": "Missing API Key"}
    try:
        q = query
        if extra_query:
            q = f"{query} AND {extra_query}"
            
        url = f"https://newsapi.org/v2/everything?q={q}&apiKey={api_key}&pageSize=10&sortBy=relevancy"
        if language:
            url += f"&language={language}"
        if from_date:
            url += f"&from={from_date}"
            
        resp = requests.get(url, timeout=15)
        data = resp.json()
        if data.get("status") == "error":
            return {"error": data.get("message", "Σφάλμα NewsAPI")}
        
        news_list = []
        for article in data.get("articles", []):
            news_list.append({
                "title": article.get("title", "Χωρίς Τίτλο"),
                "description": article.get("description", ""),
                "url": article.get("url", ""),
                "source": article.get("source", {}).get("name", "Άγνωστη Πηγή"),
                "date": article.get("publishedAt", "")[:10]
            })
        return {"news": news_list}
    except requests.exceptions.Timeout:
        logger.error(f"Timeout NewsAPI για {query}")
        return {"error": "Το NewsAPI άργησε να απαντήσει (Timeout). Δοκιμάστε ξανά."}
    except Exception as e:
        logger.error(f"Σφάλμα NewsAPI: {e}")
        return {"error": str(e)}

def scrape_url_text(url):
    """Αντλεί το περιεχόμενο από ένα custom URL."""
    try:
        downloaded = trafilatura.fetch_url(url)
        if downloaded is None:
            return ""
        text = trafilatura.extract(downloaded, include_comments=False, include_tables=False)
        if text:
            # Περιορισμός μεγέθους για εξοικονόμηση tokens
            return text[:8000] 
        return ""
    except Exception as e:
        logger.error(f"Σφάλμα ανάγνωσης από το URL {url}: {e}")
        return ""