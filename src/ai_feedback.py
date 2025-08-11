import openai
import os
from dotenv import load_dotenv

# Load the API key from .env
load_dotenv()
openai.api_key = os.getenv("OPENAI_API_KEY")

STYLE_SYSTEM_PROMPT = """
You are a reflective writing companion. You do not write text for the user — only interpret their writing.
- Speak conversationally, warmly, and interpretively.
- Focus on mood, energy, and emotional undercurrents.
- Be constructive and honest, if the users writing is weak or sloppy in some regards, point it out.
- Do not insert unecessary critisicm, if the writing is clear and flows, just analyze and interpret.
- Avoid technical or numerical details; imply patterns instead.
- Compare to the user’s usual style only if you have context.
- If they’re experimenting or shifting tone, mention it encouragingly.
"""

def get_ai_feedback(user_text: str, profile_summary: str = None) -> str:
    context = f"""
User's latest writing sample:
{user_text}

User's general style (if known):
{profile_summary or 'No prior profile — treat this as a first impression.'}
"""

    response = openai.ChatCompletion.create(
        model="gpt-4",  # or use "gpt-3.5-turbo" if you don’t have GPT-4 access
        messages=[
            {"role": "system", "content": STYLE_SYSTEM_PROMPT},
            {"role": "user", "content": context}
        ]
    )

    return response.choices[0].message["content"].strip()
