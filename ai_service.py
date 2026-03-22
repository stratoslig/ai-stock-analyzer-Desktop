import google.genai as genai
import ollama
import logging

logger = logging.getLogger(__name__)

def fetch_models(provider, api_key=None):
    """Αντλεί τα διαθέσιμα μοντέλα ανάλογα με τον πάροχο."""
    try:
        if provider == "Gemini (Cloud)":
            if not api_key:
                return ["Απαιτείται API Key"]
            client = genai.Client(api_key=api_key)
            models = [m.name for m in client.models.list() if "gemini" in m.name.lower()]
            return models if models else ["Κανένα διαθέσιμο μοντέλο"]
        else:
            resp = ollama.list()
            if isinstance(resp, dict):
                models = [m.get("name", m.get("model")) for m in resp.get("models", [])]
            else:
                models = [m.model for m in resp.models]
            return models if models else ["Κανένα διαθέσιμο μοντέλο"]
    except Exception as e:
        logger.error(f"Σφάλμα φόρτωσης μοντέλων ({provider}): {e}", exc_info=True)
        return ["Σφάλμα φόρτωσης"]

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
            if not api_key:
                return None, "❌ Το Gemini API Key απουσιάζει. Πρόσθεσέ το στις ρυθμίσεις."
            
            client = genai.Client(api_key=api_key)
            response = client.models.generate_content(
                model=model, 
                contents=prompt,
                config=genai.types.GenerateContentConfig(temperature=temperature)
            )
            return response.text, None
        else:
            response = ollama.chat(
                model=model, 
                messages=[{'role': 'user', 'content': prompt}],
                options={'temperature': temperature}
            )
            return response['message']['content'], None
    except Exception as e:
        logger.error(f"Σφάλμα AI κατά την ανάλυση ({provider} - {model}): {e}", exc_info=True)
        return None, f"❌ Σφάλμα AI: {e}"