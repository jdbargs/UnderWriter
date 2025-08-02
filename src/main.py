from .analyzer import analyze_text
from .tone_classifier import classify_tone
from .storage import update_profile, load_profile

def detect_outliers(metrics, profile):
    """
    Compare new metrics with stored averages and highlight differences.
    """
    suggestions = []

    if not profile or profile.get("count", 0) < 3:
        return ["Building baseline profile; few comparisons available yet."]

    avg_len = metrics["sentence_length_avg"]
    baseline = profile["avg_sentence_length"]
    if abs(avg_len - baseline) > 5:
        if avg_len > baseline:
            suggestions.append(f"Your sentences are longer than usual ({avg_len:.1f} vs {baseline:.1f}) — feels reflective.")
        else:
            suggestions.append(f"Your sentences are shorter than usual ({avg_len:.1f} vs {baseline:.1f}) — feels more direct.")

    richness = metrics["vocab_richness"]
    base_rich = profile["vocab_richness"]
    if richness > base_rich + 0.05:
        suggestions.append("More diverse vocabulary than usual — feels exploratory.")
    elif richness < base_rich - 0.05:
        suggestions.append("Simpler vocabulary than usual — reads cleaner but less nuanced.")

    return suggestions

def chat_loop():
    print("Style Profiler Chat Mode")
    print("Type or paste text. Type 'quit' to exit.\n")

    while True:
        user_input = input("> ")
        if user_input.lower() in ["quit", "exit"]:
            print("Goodbye!")
            break

        metrics = analyze_text(user_input)
        metrics["tone"] = classify_tone(user_input)

        profile = update_profile(metrics)
        suggestions = detect_outliers(metrics, profile)

        print("\n=== Feedback ===")
        for s in suggestions:
            print(f"- {s}")

        # Compliment mode: trigger when stable
        if profile["count"] >= 5:
            print("You've developed a consistent style. Future feedback will focus on tone recognition.")

        print()

if __name__ == "__main__":
    chat_loop()
