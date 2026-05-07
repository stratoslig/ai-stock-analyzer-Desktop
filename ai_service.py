import logging
from translations import tr

logger = logging.getLogger(__name__)

def fetch_models(provider, api_key=None, lang="el"):
    """Αντλεί τα διαθέσιμα μοντέλα ανάλογα με τον πάροχο."""
    try:
        if provider == "Gemini (Cloud)":
            import google.genai as genai
            if not api_key:
                return [tr("err_req_api_key", lang)]
            client = genai.Client(api_key=api_key)
            models = [m.name for m in client.models.list() if "gemini" in m.name.lower()]
            return models if models else [tr("err_no_models", lang)]
        elif provider == "Ollama (Cloud)":
            import ollama
            if not api_key:
                return [tr("err_req_api_key_url", lang)]
            try:
                if api_key.startswith("http"):
                    client = ollama.Client(host=api_key)
                else:
                    client = ollama.Client(
                        host="https://ollama.com",
                        headers={'Authorization': f'Bearer {api_key}'}
                    )
                resp = client.list()
                if isinstance(resp, dict):
                    models = [m.get("name", m.get("model")) for m in resp.get("models", [])]
                else:
                    models = [m.model for m in resp.models]
                return models if models else [tr("err_no_models", lang)]
            except Exception as e:
                logger.error(f"Σφάλμα φόρτωσης μοντέλων Ollama Cloud: {e}")
                return [tr("err_load_models", lang)]
        else:
            import ollama
            resp = ollama.list()
            if isinstance(resp, dict):
                models = [m.get("name", m.get("model")) for m in resp.get("models", [])]
            else:
                models = [m.model for m in resp.models]
            return models if models else [tr("err_no_models", lang)]
    except Exception as e:
        logger.error(f"Σφάλμα φόρτωσης μοντέλων ({provider}): {e}", exc_info=True)
        return [tr("err_load_models", lang)]

def generate_analysis(provider, model, name, context, api_key=None, temperature=0.7, extra_prompt="", lang="el"):
    """Εκτελεί την ανάλυση στο επιλεγμένο AI."""
    if lang == "en":
        prompt = f"You are a professional financial analyst. Analyze the stock {name} based on the following data:\n{context}"
    else:
        prompt = f"Είσαι επαγγελματίας οικονομικός αναλυτής. Ανέλυσε τη μετοχή {name} με βάση τα παρακάτω δεδομένα:\n{context}"
        
    if extra_prompt:
        if lang == "en":
            prompt += f"\n\nAdditional Instructions (System Prompt):\n{extra_prompt}"
        else:
            prompt += f"\n\nΕπιπλέον Οδηγίες (System Prompt):\n{extra_prompt}"
    try:
        if provider == "Gemini (Cloud)":
            import google.genai as genai
            if not api_key:
                return None, tr("err_miss_gemini", lang)
            
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=model, 
                contents=prompt,
                config=genai.types.GenerateContentConfig(temperature=temperature)
            )
            return response.text, None
        elif provider == "Ollama (Cloud)":
            import ollama
            if not api_key:
                return None, tr("err_miss_ollama", lang)
            try:
                if api_key.startswith("http"):
                    client = ollama.Client(host=api_key)
                else:
                    client = ollama.Client(
                        host="https://ollama.com",
                        headers={'Authorization': f'Bearer {api_key}'}
                    )
                    
                response = client.chat(
                    model=model, 
                    messages=[{'role': 'user', 'content': prompt}],
                    options={'temperature': temperature}
                )
                return response['message']['content'], None
            except Exception as e:
                logger.error(f"Σφάλμα Ollama Cloud: {e}")
                return None, tr("err_ai", lang, e=str(e))
        else:
            import ollama
            response = ollama.chat(
                model=model, 
                messages=[{'role': 'user', 'content': prompt}],
                options={'temperature': temperature}
            )
            return response['message']['content'], None
    except Exception as e:
        logger.error(f"Σφάλμα AI κατά την ανάλυση ({provider} - {model}): {e}", exc_info=True)
        return None, tr("err_ai", lang, e=str(e))