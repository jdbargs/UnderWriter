import string
from collections import Counter
import spacy
from .utils import clean_text, tokenize_words, filter_stopwords

nlp = spacy.load("en_core_web_sm")

def analyze_text(text: str):
    """Analyze text for core style metrics."""
    text = clean_text(text)
    doc = nlp(text)

    # Sentence metrics
    sentences = list(doc.sents)
    sentence_lengths = [len([t for t in s if not t.is_punct]) for s in sentences]
    avg_len = sum(sentence_lengths) / len(sentence_lengths) if sentences else 0
    var_len = (max(sentence_lengths) - min(sentence_lengths)) if sentences else 0

    # Vocabulary richness
    words = tokenize_words(doc)
    vocab_richness = len(set(words)) / len(words) if words else 0

    # Frequent words (non-stopword)
    stopwords = nlp.Defaults.stop_words
    non_stop_words = filter_stopwords(words, stopwords)
    freq_words = Counter(non_stop_words).most_common(5)

    # Punctuation usage
    punct = Counter([c for c in text if c in string.punctuation])

    return {
        "sentence_length_avg": round(avg_len, 2),
        "sentence_length_var": var_len,
        "vocab_richness": round(vocab_richness, 2),
        "frequent_words": [w for w, _ in freq_words],
        "punctuation_use": dict(punct)
    }
