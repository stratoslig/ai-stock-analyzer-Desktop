import logging
import cloudscraper
from bs4 import BeautifulSoup
from ddgs import DDGS
import requests
import feedparser
from dateutil import parser as date_parser
from datetime import datetime, timedelta, timezone
import concurrent.futures
import threading
import urllib.parse

logger = logging.getLogger(__name__)

def get_stock_info(symbol):
    """Αντλεί βασικές πληροφορίες για την προσθήκη νέας μετοχής."""
    try:
        import yfinance as yf
        info = yf.Ticker(symbol).info
        return info.get("shortName") or info.get("longName") or symbol
    except Exception as e:
        logger.error(f"Σφάλμα ανάκτησης πληροφοριών για {symbol}: {e}", exc_info=True)
        return None

def get_stock_data(symbol, period="6mo"):
    """Αντλεί ιστορικά δεδομένα και υπολογίζει τους τεχνικούς δείκτες."""
    try:
        import yfinance as yf
        import pandas as pd
        import pandas_ta as ta
        ticker = yf.Ticker(symbol)
        info = ticker.info
        hist = ticker.history(period=period)

        if len(hist) == 0:
            return {"error": "Δεν βρέθηκαν ιστορικά δεδομένα."}

        quote_type = info.get("quoteType")

        cp = hist['Close'].iloc[-1]
        pp = hist['Close'].iloc[-2] if len(hist) >= 2 else cp
        pct_change = ((cp - pp) / pp) * 100 if pp != 0 else 0.0

        # Υπολογισμός τεχνικών δεικτών για όλους τους τύπους
        hist.ta.rsi(length=14, append=True)
        hist.ta.macd(append=True)
        hist.ta.sma(length=20, append=True)
        hist.ta.sma(length=50, append=True)
        hist.ta.ema(length=20, append=True)
        hist.ta.ema(length=50, append=True)
        latest = hist.iloc[-1]

        res = {
            "price": f"${cp:,.2f} ({pct_change:.2f}%)" if quote_type != 'INDEX' else f"{cp:,.2f} ({pct_change:.2f}%)",
            "rsi": f"{latest.get('RSI_14'):.2f}" if pd.notna(latest.get('RSI_14')) else "N/A",
            "macd": f"{latest.get('MACD_12_26_9'):.2f}" if pd.notna(latest.get('MACD_12_26_9')) else "N/A",
            "sma20": f"{latest.get('SMA_20'):.2f}" if pd.notna(latest.get('SMA_20')) else "N/A",
            "sma50": f"{latest.get('SMA_50'):.2f}" if pd.notna(latest.get('SMA_50')) else "N/A",
            "df": hist,
            "quote_type": quote_type
        }
        
        context_parts = [f"[ΒΑΣΙΚΑ ΔΕΔΟΜΕΝΑ & ΤΕΧΝΙΚΟΙ ΔΕΙΚΤΕΣ]\nΤιμή: {res['price']}\nRSI(14): {res['rsi']} | MACD: {res['macd']} | SMA20: {res['sma20']} | SMA50: {res['sma50']}"]

        # Διαφορετική διαχείριση ανάλογα με τον τύπο (Μετοχή, ETF, Δείκτης)
        if quote_type == 'EQUITY':
            mcap = info.get("marketCap", 0)
            pe = info.get('trailingPE', 'N/A')
            div = info.get("dividendYield") or info.get("trailingAnnualDividendYield")
            beta = info.get('beta', 'N/A')
            website = info.get("website", "")
            domain = website.replace("https://", "").replace("http://", "").replace("www.", "").split('/')[0] if website else ""
            
            rev_growth, roe, dte, fcf, op_margin = info.get("revenueGrowth"), info.get("returnOnEquity"), info.get("debtToEquity"), info.get("freeCashflow"), info.get("operatingMargins")
            forward_pe, ev_ebitda, pb_ratio = info.get("forwardPE", "N/A"), info.get("enterpriseToEbitda", "N/A"), info.get("priceToBook", "N/A")
            total_debt, ebitda = info.get("totalDebt"), info.get("ebitda")
            debt_ebitda = (total_debt / ebitda) if isinstance(total_debt, (int, float)) and isinstance(ebitda, (int, float)) and ebitda != 0 else "N/A"

            # Έξυπνη μετατροπή ποσοστών: Αν η απόλυτη τιμή είναι εξωπραγματική (>10 δηλ. >1000%), 
            # θεωρούμε ότι το API την επέστρεψε ήδη μορφοποιημένη ως ποσοστό (π.χ. 15.7 αντί για 0.157)
            def safe_pct(val, threshold=10):
                if not isinstance(val, (int, float)): return "N/A"
                return f"{val:.2f}%" if abs(val) > threshold else f"{val * 100:.2f}%"

            fmt_rev_growth = safe_pct(rev_growth)
            fmt_roe = safe_pct(roe)
            fmt_op_margin = safe_pct(op_margin)
            fmt_dte = f"{dte:.2f}" if isinstance(dte, (int, float)) else "N/A"
            fmt_fwd_pe = f"{forward_pe:.2f}" if isinstance(forward_pe, (int, float)) else "N/A"
            fmt_ev_ebitda = f"{ev_ebitda:.2f}" if isinstance(ev_ebitda, (int, float)) else "N/A"
            fmt_pb = f"{pb_ratio:.2f}" if isinstance(pb_ratio, (int, float)) else "N/A"
            fmt_debt_ebitda = f"{debt_ebitda:.2f}" if isinstance(debt_ebitda, (int, float)) else "N/A"
            fmt_fcf = f"${fcf/1e9:.2f}B" if isinstance(fcf, (int, float)) and abs(fcf) >= 1e9 else (f"${fcf/1e6:.2f}M" if isinstance(fcf, (int, float)) else "N/A")

            if isinstance(div, (int, float)):
                fmt_div = f"{div:.2f}%" if div > 1 else f"{div * 100:.2f}%"
            else:
                fmt_div = "N/A"

            res.update({
                "mcap": f"${mcap/1e9:.2f}B" if mcap >= 1e9 else f"${mcap/1e6:.2f}M",
                "pe": f"{pe:.2f}" if isinstance(pe, (int, float)) else "N/A",
                "div": fmt_div,
                "beta": f"{beta:.2f}" if isinstance(beta, (int, float)) else "N/A",
                "rev_growth": fmt_rev_growth, "roe": fmt_roe, "op_margin": fmt_op_margin, "dte": fmt_dte, "fcf": fmt_fcf,
                "forward_pe": fmt_fwd_pe, "ev_ebitda": fmt_ev_ebitda, "pb_ratio": fmt_pb, "debt_ebitda": fmt_debt_ebitda,
                "domain": domain, "website": website,
            })
            context_parts[0] += f" | P/E: {res['pe']}"
            context_parts.append(f"[ΟΙΚΟΝΟΜΙΚΗ ΥΓΕΙΑ & ΑΠΟΔΟΣΗ]\nRevenue Growth: {fmt_rev_growth} | ROE: {fmt_roe} | Operating Margin: {fmt_op_margin}\nDebt to Equity: {fmt_dte} | Free Cash Flow: {fmt_fcf}")
            context_parts.append(f"[ΑΠΟΤΙΜΗΣΗ & ΕΠΙΠΛΕΟΝ ΔΕΙΚΤΕΣ]\nForward P/E: {fmt_fwd_pe} | EV/EBITDA: {fmt_ev_ebitda} | Price/Book: {fmt_pb} | Debt/EBITDA: {fmt_debt_ebitda}")

        elif quote_type == 'ETF':
            mcap = info.get("totalAssets", 0)
            pe = info.get('trailingPE', 'N/A')
            
            div_raw = info.get("yield")
            if isinstance(div_raw, (int, float)):
                fmt_div = f"{div_raw:.2f}%" if div_raw > 1 else f"{div_raw * 100:.2f}%"
            else:
                fmt_div = "N/A"
                
            beta = info.get('beta3Year', 'N/A')
            domain = info.get("fundFamily", "")
            
            res.update({
                "mcap": f"${mcap/1e9:.2f}B" if mcap >= 1e9 else f"${mcap/1e6:.2f}M",
                "pe": f"{pe:.2f}" if isinstance(pe, (int, float)) else "N/A",
                "div": fmt_div,
                "beta": f"{beta:.2f}" if isinstance(beta, (int, float)) else "N/A",
                "domain": domain, "website": "",
                "rev_growth": "N/A", "roe": "N/A", "op_margin": "N/A", "dte": "N/A", "fcf": "N/A",
                "forward_pe": "N/A", "ev_ebitda": "N/A", "pb_ratio": "N/A", "debt_ebitda": "N/A",
            })
            context_parts[0] += f" | P/E: {res['pe']}"
            context_parts.append(f"[ΔΕΔΟΜΕΝΑ ETF]\nΜερισμ. Απόδοση: {res['div']} | Beta (3Y): {res['beta']} | Σύνολο Ενεργητικού: {res['mcap']}")

        elif quote_type == 'INDEX':
            res.update({
                "mcap": "N/A", "pe": "N/A", "div": "N/A", "beta": "N/A", "domain": "", "website": "",
                "rev_growth": "N/A", "roe": "N/A", "op_margin": "N/A", "dte": "N/A", "fcf": "N/A",
                "forward_pe": "N/A", "ev_ebitda": "N/A", "pb_ratio": "N/A", "debt_ebitda": "N/A",
            })
            context_parts.append("[ΑΝΑΛΥΣΗ ΔΕΙΚΤΗ]\nΑυτό είναι ένας χρηματιστηριακός δείκτης. Η ανάλυση πρέπει να εστιάσει στην τεχνική του πορεία (βάσει γραφήματος και δεικτών RSI/MACD/SMA) και στις γενικότερες ειδήσεις που τον επηρεάζουν.")
        
        # Fallback για περιπτώσεις που το yfinance δεν δίνει quoteType
        else:
            res.update({
                "mcap": "N/A", "pe": "N/A", "div": "N/A", "beta": "N/A", "domain": "", "website": "",
                "rev_growth": "N/A", "roe": "N/A", "op_margin": "N/A", "dte": "N/A", "fcf": "N/A",
                "forward_pe": "N/A", "ev_ebitda": "N/A", "pb_ratio": "N/A", "debt_ebitda": "N/A",
            })
            context_parts.append("[ΓΕΝΙΚΗ ΑΝΑΛΥΣΗ]\nΔεν ήταν δυνατός ο εντοπισμός του τύπου (Μετοχή/ETF/Δείκτης). Εστίασε στην τεχνική ανάλυση και τις ειδήσεις.")

        res["context"] = "\n\n".join(context_parts)
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

        lock = threading.Lock()

        def add_if_relevant(res_list):
            if not res_list: return
            for r in res_list:
                url = r.get("url")
                title_body = (r.get("title", "") + " " + r.get("body", "")).lower()
                
                # Το όνομα της εταιρείας ή κάποιο σύμβολό της πρέπει να υπάρχει στον τίτλο ή στο σώμα
                is_relevant = any(kw in title_body for kw in target_keywords)
                
                if is_relevant:
                    with lock:
                        if url not in seen_urls:
                            seen_urls.add(url)
                            unique_results.append(r)

        # 1. Αναζήτηση στα Ελληνικά (Μεγαλύτερο χρονικό εύρος 'y' λόγω μικρότερου όγκου ειδήσεων)
        def search_gr():
            try:
                with DDGS() as ddgs:
                    gr_results = ddgs.news(f"{q_clean} μετοχή", region="gr-el", timelimit="y", max_results=max_results)
                    add_if_relevant(gr_results)
                    
                    if len(unique_results) < 2:
                        gr_fallback = ddgs.news(q_clean, region="gr-el", timelimit="y", max_results=max_results)
                        add_if_relevant(gr_fallback)
                        
                    if len(unique_results) < 5 and symbols:
                        first_sym = symbols[0] if symbols[0] and symbols[0] != "N/A" else (symbols[1] if len(symbols)>1 and symbols[1] else "")
                        if first_sym:
                            clean_sym = first_sym.split('.')[0] if '.' in first_sym else first_sym
                            gr_sym_results = ddgs.news(f"{clean_sym} μετοχή", region="gr-el", timelimit="y", max_results=max_results)
                            add_if_relevant(gr_sym_results)
            except Exception:
                pass
            
        # 2. Αναζήτηση στα Αγγλικά (Επέκταση χρονικού περιθωρίου σε 'y' αντί για 'm')
        def search_en():
            try:
                with DDGS() as ddgs:
                    en_results = ddgs.news(f'"{q_clean}" stock OR earnings', region="wt-wt", timelimit="y", max_results=max_results)
                    add_if_relevant(en_results)
                    
                    if len(unique_results) < 6:
                        en_results_fallback = ddgs.news(f"{main_word} stock", region="wt-wt", timelimit="y", max_results=max_results)
                        add_if_relevant(en_results_fallback)
                        
                    if len(unique_results) < 10 and symbols:
                        first_sym = symbols[0] if symbols[0] and symbols[0] != "N/A" else ""
                        if first_sym:
                            clean_sym = first_sym.split('.')[0] if '.' in first_sym else first_sym
                            en_sym_results = ddgs.news(f"{clean_sym} stock", region="wt-wt", timelimit="y", max_results=max_results)
                            add_if_relevant(en_sym_results)
            except Exception:
                pass
                
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            executor.submit(search_gr)
            executor.submit(search_en)
            
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
            
        av_div_raw = data.get("DividendYield", "N/A")
        try:
            if av_div_raw not in ["N/A", "None", None]:
                av_div_val = float(av_div_raw)
                av_div = f"{av_div_val:.2f}%" if av_div_val > 1 else f"{av_div_val * 100:.2f}%"
            else:
                av_div = "N/A"
        except Exception:
            av_div = str(av_div_raw)
            
        return {
            "pe": data.get("PERatio", "N/A"),
            "eps": data.get("EPS", "N/A"),
            "div": av_div,
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
        # Το βασικό query (όνομα μετοχής) πρέπει πάντα να υπάρχει. Το βάζουμε σε uquotes για να είναι phrase.
        q_parts = [f'"{query}"']

        if extra_query:
            # Δημιουργία του σύνθετου query από την είσοδο του χρήστη
            or_groups = []
            for group in extra_query.split(','):
                group = group.strip()
                if not group: continue
                and_terms = [f'"{t.strip()}"' for t in group.split('+') if t.strip()]
                if and_terms:
                    or_groups.append(f"({' AND '.join(and_terms)})")
            if or_groups:
                q_parts.append(f"({' OR '.join(or_groups)})")
            
        final_q = " AND ".join(q_parts)
        url = f"https://newsapi.org/v2/everything?q={final_q}&apiKey={api_key}&pageSize=10&sortBy=relevancy"
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
        import trafilatura
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

def validate_rss(url):
    """Ελέγχει αν ένα URL είναι έγκυρο RSS Feed."""
    try:
        feed = feedparser.parse(url)
        return feed.bozo == 0 and len(feed.entries) > 0
    except:
        return False

def get_rss_news(feed_urls, keyword="", days_limit=None):
    """Αντλεί ειδήσεις από λίστα RSS feeds και εφαρμόζει φίλτρα."""
    articles = []
    now = datetime.now(timezone.utc)
    
    def fetch_feed(url):
        local_articles = []
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries:
                title = entry.get("title", "")
                link = entry.get("link", "")
                summary = entry.get("summary", "")
                
                # Έλεγχος Λέξης-Κλειδιού
                if keyword:
                    text_to_search = (title + " " + summary).lower()
                    or_groups = [g.strip() for g in keyword.split(',')]
                    match_found = False
                    for group in or_groups:
                        and_terms = [t.strip().lower() for t in group.split('+')]
                        if all(term in text_to_search for term in and_terms):
                            match_found = True
                            break
                    if not match_found:
                        continue
                    
                # Έλεγχος Ημερομηνίας
                pub_date_str = entry.get("published", entry.get("updated", ""))
                if days_limit and pub_date_str:
                    try:
                        pub_date = date_parser.parse(pub_date_str)
                        if pub_date.tzinfo is None:
                            pub_date = pub_date.replace(tzinfo=timezone.utc)
                        if (now - pub_date).days > int(days_limit):
                            continue
                    except:
                        pass # Αν δεν μπορεί να διαβάσει την ημερομηνία, το κρατάμε
                        
                local_articles.append({
                    "title": title,
                    "url": link,
                    "source": feed.feed.get("title", "RSS Feed"),
                    "date": pub_date_str[:16] if pub_date_str else "",
                    "description": BeautifulSoup(summary, "html.parser").get_text()[:200] + "..." if summary else ""
                })
        except Exception as e:
            logger.error(f"Σφάλμα ανάγνωσης RSS {url}: {e}")
        return local_articles
            
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(fetch_feed, feed_urls)
        for res in results:
            articles.extend(res)
            
    # Ταξινόμηση ανά ημερομηνία (από το πιο πρόσφατο στο παλαιότερο)
    articles.sort(key=lambda x: x.get("date", ""), reverse=True)
    return articles

def get_scraped_articles(urls, keyword="", limit=10, char_limit=250):
    """Αντλεί άρθρα (τίτλους και links) από γενικές ιστοσελίδες (Web Scraping)."""
    articles = []
    
    def fetch_site(url):
        local_articles = []
        try:
            scraper = cloudscraper.create_scraper()
            resp = scraper.get(url, timeout=15)
            soup = BeautifulSoup(resp.text, 'html.parser')
            base_url = "{0.scheme}://{0.netloc}".format(urllib.parse.urlsplit(url))
            
            seen_urls = set()
            
            # Εύρεση <a> tags που μοιάζουν με άρθρα (ικανοποιητικό μέγεθος τίτλου)
            for a in soup.find_all('a', href=True):
                title = a.get_text(separator=" ", strip=True)
                link = a['href']
                
                if len(title) < 40:  # Αγνοούμε πολύ μικρούς τίτλους (π.χ. "Home", "Read more")
                    continue
                    
                if not link.startswith('http'):
                    link = urllib.parse.urljoin(base_url, link)
                    
                if link in seen_urls:
                    continue
                seen_urls.add(link)
                
                # Αναζήτηση περιγραφής (κοντινό <p> tag)
                desc = ""
                parent = a.find_parent(['div', 'article', 'li', 'section'])
                if parent:
                    p = parent.find('p')
                    if p:
                        p_text = p.get_text(separator=" ", strip=True)
                        if p_text and p_text != title:
                            desc = p_text[:char_limit] + "..." if len(p_text) > char_limit else p_text
                            
                # Φίλτρο λέξης-κλειδιού (όπως στο RSS)
                if keyword:
                    text_to_search = (title + " " + desc).lower()
                    or_groups = [g.strip() for g in keyword.split(',')]
                    match_found = False
                    for group in or_groups:
                        and_terms = [t.strip().lower() for t in group.split('+')]
                        if all(term in text_to_search for term in and_terms):
                            match_found = True
                            break
                    if not match_found:
                        continue
                        
                local_articles.append({
                    "title": title,
                    "url": link,
                    "source": base_url,
                    "date": "", 
                    "description": desc
                })
                
                if len(local_articles) >= limit:
                    break
        except Exception as e:
            logger.error(f"Σφάλμα scraping στο {url}: {e}")
        return local_articles

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        results = executor.map(fetch_site, urls)
        for res in results:
            articles.extend(res)
            
    return articles