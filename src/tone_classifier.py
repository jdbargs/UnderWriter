import os
from dotenv import load_dotenv

# Optional: use OpenAI if key present
try:
    from openai import OpenAI
except ImportError:
    OpenAI = None

load_dotenv()
OPENAI_KEY = os.getenv("OPENAI_API_KEY")

def classify_tone(text: str) -> str:
    """
    Classify tone using OpenAI (if key provided) or fallback heuristic.
    """
    if OPENAI_KEY and OpenAI:
        try:
            client = OpenAI(api_key=OPENAI_KEY)
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Classify tone in one or two words (e.g., reflective, casual, formal)."},
                    {"role": "user", "content": text}
                ]
            )
            return response.choices[0].message["content"].strip().lower()
        except Exception:
            return _fallback_tone(text)
    else:
        return _fallback_tone(text)

def _fallback_tone(text: str) -> str:
    if "!" in text:
        return "energetic"
    elif "?" in text:
        return "inquisitive"
    elif text.lower().startswith(("dear", "to whom")):
        return "formal"
    else:
        return "neutral"
