"""GUI-free application logic: data, scoring and recommendation.

Importing this package must never require PyQt, so the modules here can be
exercised from a plain Python script.
"""

__all__ = [
    "db", "models", "repo", "seed_data", "recommender", "weather",
]
