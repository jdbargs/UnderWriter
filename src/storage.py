import json
import os

PROFILE_PATH = "data/user_profile.json"

def load_profile():
    """Load user profile metrics from JSON (if exists)."""
    if os.path.exists(PROFILE_PATH):
        with open(PROFILE_PATH, "r") as f:
            return json.load(f)
    return {}

def save_profile(profile):
    """Save user profile metrics to JSON."""
    os.makedirs("data", exist_ok=True)
    with open(PROFILE_PATH, "w") as f:
        json.dump(profile, f, indent=2)

def update_profile(new_metrics):
    """
    Merge new metrics into profile:
    - Maintain running average for quantitative metrics.
    - Append frequent words for tracking evolution.
    """
    profile = load_profile()

    # Initialize if empty
    if not profile:
        profile = {
            "count": 0,
            "avg_sentence_length": 0,
            "vocab_richness": 0,
            "frequent_words": []
        }

    count = profile["count"] + 1
    profile["count"] = count

    # Running averages
    profile["avg_sentence_length"] = (
        (profile["avg_sentence_length"] * (count - 1) + new_metrics["sentence_length_avg"]) / count
    )
    profile["vocab_richness"] = (
        (profile["vocab_richness"] * (count - 1) + new_metrics["vocab_richness"]) / count
    )

    # Update frequent words (basic merge)
    profile["frequent_words"] = list(set(profile["frequent_words"] + new_metrics["frequent_words"]))

    save_profile(profile)
    return profile
