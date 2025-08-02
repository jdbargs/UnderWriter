import re

def clean_text(text: str) -> str:
    """Basic cleaning: strip extra spaces, normalize whitespace."""
    return re.sub(r'\s+', ' ', text).strip()

def tokenize_words(doc):
    """Return lowercase alpha tokens from spaCy doc."""
    return [t.text.lower() for t in doc if t.is_alpha]

def filter_stopwords(words, stopwords):
    """Remove stopwords from token list."""
    return [w for w in words if w not in stopwords]
