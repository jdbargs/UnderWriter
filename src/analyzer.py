# src/analyzer.py
import re
import string
from typing import Dict, Any, List
from collections import Counter

# spaCy is preferred but we'll fail gracefully if the model isn't available
try:
    import spacy
    _NLP = spacy.load("en_core_web_sm")
except Exception:
    _NLP = None

from .utils import clean_text, tokenize_words, filter_stopwords

# -----------------------------
# Existing general analyzer API
# -----------------------------
def analyze_text(text: str) -> Dict[str, Any]:
    """
    Analyze text for core style metrics (used by the non-generative companion).
    Keeps your original behavior, but now tolerates missing spaCy model.
    """
    text = clean_text(text)

    if _NLP is None:
        # Fallback if spaCy model isn't available
        sentences = re.split(r"[.!?]+", text)
        sentences = [s.strip() for s in sentences if s.strip()]
        sentence_lengths = [len(_fallback_tokens(s)) for s in sentences]
        avg_len = sum(sentence_lengths) / len(sentence_lengths) if sentences else 0.0
        var_len = (max(sentence_lengths) - min(sentence_lengths)) if sentences else 0

        words = _fallback_tokens(text)
        vocab_richness = len(set(w.lower() for w in words)) / len(words) if words else 0.0

        # Simple stopword set to approximate spaCy behavior
        stopwords = _BASIC_STOPWORDS
        non_stop_words = [w for w in words if w.lower() not in stopwords]
        freq_words = Counter(non_stop_words).most_common(5)
    else:
        doc = _NLP(text)
        # Sentence metrics
        sentences = list(doc.sents)
        sentence_lengths = [len([t for t in s if not t.is_punct]) for s in sentences]
        avg_len = sum(sentence_lengths) / len(sentence_lengths) if sentences else 0.0
        var_len = (max(sentence_lengths) - min(sentence_lengths)) if sentences else 0

        # Vocabulary richness
        words = tokenize_words(doc)  # uses your utils, expects a spaCy doc
        vocab_richness = len(set(words)) / len(words) if words else 0.0

        # Frequent words (non-stopword)
        stopwords = _NLP.Defaults.stop_words
        non_stop_words = filter_stopwords(words, stopwords)
        freq_words = Counter(non_stop_words).most_common(5)

    # Punctuation usage
    punct = Counter([c for c in text if c in string.punctuation])

    return {
        "sentence_length_avg": round(avg_len, 2),
        "sentence_length_var": var_len,
        "vocab_richness": round(vocab_richness, 2),
        "frequent_words": [w for w, _ in freq_words],
        "punctuation_use": dict(punct),
    }

# ==========================================================
# ================== FlowState (Practice) ==================
# ==========================================================

_WORD_RE = re.compile(r"[A-Za-z']+")

# A minimal stopword list for fallback mode
_BASIC_STOPWORDS = set(
    """
    the be to of and a in that have i it for not on with he as you do at this
    but his by from they we say her she or an will my one all would there their
    what so up out if about who get which go me
    """.split()
)

def _fallback_tokens(text: str) -> List[str]:
    """Regex tokenizer used when spaCy isn't available."""
    return _WORD_RE.findall(text)

def _tokenize_alpha(text: str) -> List[str]:
    """Tokenize using spaCy when available; fallback to regex otherwise."""
    if _NLP is None:
        return _fallback_tokens(text)
    doc = _NLP(text)
    return [t.text for t in doc if t.is_alpha or ("'" in t.text and t.text.replace("'", "").isalpha())]

def _unique_types(tokens: List[str]) -> int:
    return len(set(t.lower() for t in tokens))

def _clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))

def analyze_flow_text(text: str) -> Dict[str, Any]:
    """
    Fast lexical metrics + lightweight goal heuristics for FlowState bursts.
    Returns keys expected by the FlowState pipeline:
      - word_count, vocab_type_count, vocab_ttr, repetition_rate
      - playfulness_score, clarity_score, creativity_score
    """
    tokens = _tokenize_alpha(text)
    word_count = len(tokens)
    types = _unique_types(tokens)
    ttr = (types / word_count) if word_count else 0.0
    repetition_rate = 1.0 - (types / word_count) if word_count else 0.0

    txt_lower = text.lower()

    # --- Playfulness (0..1): punctuation variety + figurative markers + interjections + lexical variety ---
    punct_variety = len(set(ch for ch in text if ch in [",", ".", "—", "-", ":", ";", "!", "?", "(", ")"]))
    figurative_hits = len(re.findall(r"\b(like|as if|as though)\b", txt_lower))
    interjections = len(re.findall(r"\b(hey|wow|ah|oh|hmm|ugh|ha)\b", txt_lower))
    playfulness = _clamp(
        0.15 * min(punct_variety, 6)
        + 0.2 * figurative_hits
        + 0.1 * interjections
        + 0.6 * _clamp(ttr / 0.6)
    )

    # --- Clarity (0..1): shorter/cleaner sentences, fewer hedges, fewer passive cues ---
    hedges = len(re.findall(r"\b(maybe|kind of|sort of|perhaps|somewhat|a bit)\b", txt_lower))
    sentences = re.split(r"[.!?]+", text)
    sentences = [s.strip() for s in sentences if s.strip()]
    avg_sent_len = (sum(len(_tokenize_alpha(s)) for s in sentences) / len(sentences)) if sentences else 0.0
    passive_cues = len(re.findall(r"\b(be|been|being|is|was|were|are)\b\s+\b\w+ed\b", txt_lower))
    clarity = _clamp(
        0.6 * _clamp(1.0 - (max(0.0, avg_sent_len - 18.0) / 22.0))  # prefer around ~18 words/sentence
        + 0.25 * _clamp(1.0 - hedges / 4.0)
        + 0.15 * _clamp(1.0 - passive_cues / 3.0)
    )

    # --- Creativity (0..1): rare-ish words + lexical variety ---
    common_words = _BASIC_STOPWORDS
    rare_tokens = [t for t in (tok.lower() for tok in tokens) if t not in common_words and len(t) > 6]
    rare_rate = len(rare_tokens) / word_count if word_count else 0.0
    creativity = _clamp(0.7 * _clamp(rare_rate / 0.15) + 0.3 * _clamp(ttr / 0.6))

    return {
        "word_count": word_count,
        "vocab_type_count": types,
        "vocab_ttr": round(ttr, 4),
        "repetition_rate": round(_clamp(repetition_rate), 4),
        "playfulness_score": round(playfulness, 4),
        "clarity_score": round(clarity, 4),
        "creativity_score": round(creativity, 4),
    }

def compute_flow_composite(elapsed_seconds: float, metrics: Dict[str, Any], goal_focus: List[str]) -> float:
    """
    Explainable game-y score, ~100 baseline.
    Components:
      + WPM reward (up to ~40 wpm)
      + Lexical diversity (TTR)
      + Selected goals average (playfulness/clarity/creativity)
      - Repetition penalty
    """
    wc = metrics.get("word_count", 0)
    wpm = (60.0 * wc / elapsed_seconds) if elapsed_seconds and elapsed_seconds > 0 else 0.0
    ttr = float(metrics.get("vocab_ttr", 0.0))
    rep = float(metrics.get("repetition_rate", 0.0))

    goal_scores = [metrics.get(f"{g}_score", 0.0) for g in (goal_focus or [])]
    goal_avg = sum(goal_scores) / len(goal_scores) if goal_scores else 0.0

    score = (
        100.0
        + 10.0 * _clamp(wpm / 40.0)      # encourage spontaneity
        + 20.0 * _clamp(ttr / 0.6)       # lexical variety
        + 20.0 * _clamp(goal_avg)        # align to selected goals
        - 10.0 * _clamp(rep * 2.0)       # repetition penalty
    )
    return round(score, 2)
