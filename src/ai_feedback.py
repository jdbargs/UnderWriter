import os
from dotenv import load_dotenv
import openai

# Clear any proxy variables that might interfere
for var in ["HTTP_PROXY", "HTTPS_PROXY", "http_proxy", "https_proxy"]:
    os.environ.pop(var, None)

# Load API key from .env
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

STYLE_SYSTEM_PROMPT = """
You are a reflective writing companion. You do not write text for the user — only interpret their writing.
- Speak conversationally, warmly, and interpretively.
- Focus on mood, energy, and emotional undercurrents.
- Avoid technical or numerical details; imply patterns instead.
- Compare to user’s usual style only if you have context.
- If they’re experimenting or shifting tone, mention it encouragingly.
"""

def get_ai_feedback(user_text: str, profile_summary: str = None) -> str:
    """
    Generate conversational feedback about the user's writing style,
    combining the immediate sample with any known profile context.
    """
    context = f"""
User's latest writing sample:
{user_text}

User's general style (if known):
{profile_summary or 'No prior profile — treat this as a first impression.'}
"""
    response = openai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": STYLE_SYSTEM_PROMPT},
            {"role": "user", "content": context}
        ]
    )
    return response.choices[0].message["content"].strip()
