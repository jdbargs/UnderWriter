from src.analyzer import analyze_text

def test_analyze_text():
    text = "Hello world! This is a test."
    metrics = analyze_text(text)
    assert "sentence_length_avg" in metrics
    assert "vocab_richness" in metrics
    assert isinstance(metrics["frequent_words"], list)
