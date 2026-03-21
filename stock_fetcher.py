import yfinance as yf
import pandas as pd
import pandas_ta as ta
import logging
import cloudscraper
from bs4 import BeautifulSoup
from ddgs import DDGS
import requests

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
        }
        res["domain"] = domain
        res["website"] = website
        res["context"] = f"[ΒΑΣΙΚΑ ΔΕΔΟΜΕΝΑ & ΤΕΧΝΙΚΟΙ ΔΕΙΚΤΕΣ]\nΤιμή Κλεισίματος: {cp:.2f} | P/E: {pe}\nRSI(14): {res['rsi']} | MACD: {res['macd']} | SMA20: {res['sma20']} | SMA50: {res['sma50']}"
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

def get_marketaux_data(symbol, api_key, industry="", country=""):
    """Αντλεί ειδήσεις, sentiment και highlights από το MarketAux."""
    if not api_key:
        return {"error": "Missing API Key"}
    try:
        # 1. Συγκεντρωτικό Sentiment (Μόνο όταν ψάχνουμε συγκεκριμένη μετοχή)
        agg_sentiment = "N/A"
        if symbol and not industry:
            try:
                agg_url = f"https://api.marketaux.com/v1/entity/stats/aggregation?symbols={symbol}&api_token={api_key}"
                agg_resp = requests.get(agg_url, timeout=10).json()
                if "data" in agg_resp and len(agg_resp["data"]) > 0:
                    agg_sentiment = str(agg_resp["data"][0].get("sentiment_avg", "N/A"))
            except Exception:
                pass

        # 2. Ειδήσεις & Highlights
        url = f"https://api.marketaux.com/v1/news/all?api_token={api_key}"
        if industry: url += f"&industries={industry}"
        if country: url += f"&countries={country}"
        if symbol and not industry: # Αν δεν δοθεί κλάδος, στοχεύουμε τη μετοχή
            url += f"&symbols={symbol}&filter_entities=true"
            
        resp = requests.get(url, timeout=25)
        data = resp.json()
        if "error" in data:
            return {"error": data["error"].get("message", "Σφάλμα MarketAux")}
        
        news_list = []
        for article in data.get("data", [])[:10]:
            sentiment = "N/A"
            highlights = []
            for entity in article.get("entities", []):
                api_sym = entity.get("symbol", "").upper()
                # Αναγνώριση του συμβόλου ακόμα κι αν έχει κατάληξη χρηματιστηρίου (π.χ. CATX.US)
                if symbol and (api_sym == symbol.upper() or api_sym.startswith(f"{symbol.upper()}.")):
                    sentiment = entity.get("sentiment_score")
                    highlights = [h.get("highlight") for h in entity.get("highlights", []) if h.get("highlight")]
                    break
                    
            news_list.append({
                "title": article.get("title", "Χωρίς Τίτλο"),
                "description": article.get("description", ""),
                "highlights": highlights,
                "url": article.get("url", ""),
                "source": article.get("source", ""),
                "date": article.get("published_at", "")[:10],
                "sentiment": sentiment
            })
        return {"news": news_list, "agg_sentiment": agg_sentiment}
    except requests.exceptions.Timeout:
        logger.error(f"Timeout MarketAux για {symbol}")
        return {"error": "Το MarketAux άργησε να απαντήσει (Timeout). Δοκιμάστε ξανά."}
    except Exception as e:
        logger.error(f"Σφάλμα MarketAux: {e}")
        return {"error": str(e)}

def scrape_url_text(url):
    """Αντλεί το περιεχόμενο από ένα custom URL."""
    try:
        scraper = cloudscraper.create_scraper()
        resp = scraper.get(url, timeout=15)
        soup = BeautifulSoup(resp.text, 'html.parser')
        
        # Αφαιρούμε άχρηστα στοιχεία (scripts, styles, μενού, υποσέλιδα, διαφημίσεις)
        for element in soup(["script", "style", "nav", "header", "footer", "aside", "form", "noscript", "iframe", "button", "meta", "svg"]):
            element.extract()
            
        # Αφαίρεση στοιχείων βάσει κλάσης (class) ή ID που συχνά περιέχουν "θόρυβο"
        bad_keywords = ['ad', 'ads', 'advert', 'promo', 'sidebar', 'menu', 'cookie', 'popup', 'newsletter', 'social', 'share', 'comment']
        for element in soup.find_all(class_=lambda x: x and any(kw in str(x).lower() for kw in bad_keywords)):
            element.extract()
        for element in soup.find_all(id=lambda x: x and any(kw in str(x).lower() for kw in bad_keywords)):
            element.extract()
            
        paragraphs = soup.find_all('p')
        
        # Κρατάμε μόνο παραγράφους με ουσιαστικό κείμενο (π.χ. > 40 χαρακτήρες)
        valid_texts = [p.get_text(strip=True) for p in paragraphs if len(p.get_text(strip=True)) > 40]
        
        # Αφαίρεση περιττών κενών και νέων γραμμών για μέγιστη συμπύκνωση (εξοικονόμηση tokens)
        raw_text = " ".join(valid_texts)
        text = " ".join(raw_text.split())
        
        return text[:8000] # Αυξημένο όριο χαρακτήρων για εξαγωγή περισσότερων στοιχείων (περίπου 2-3k tokens)
    except Exception as e:
        logger.error(f"Σφάλμα ανάγνωσης από το URL {url}: {e}")
        return ""