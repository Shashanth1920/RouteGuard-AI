"""
Jev hello-world: intent classification via OpenRouter's Decisions API.

Loads OPENROUTER_API_KEY from .env (never hard-coded), sends 20 test
sentences to Jev (TypeSafe AI's decision model) on OpenRouter, and asks
it to decide the intent of each message from a fixed set of 5 categories.
Prints the chosen intent, confidence, and response time for each, and
saves one full raw API response to experiments/sample_raw_response.json.
"""
import json
import os
import time

import requests
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY")
if not API_KEY:
    raise SystemExit("OPENROUTER_API_KEY not found in .env")

API_URL = "https://openrouter.ai/api/alpha/decisions"
MODEL = os.getenv("JEV_MODEL", "typesafe/jev-1.13")
SESSION = requests.Session()

INTENT_CRITERIA = {
    "calculation": "The user wants a math computation or numeric result.",
    "coding": "The user wants code written, debugged, reviewed, or explained.",
    "search": "The user wants current facts, news, or information looked up.",
    "database action": "The user wants data inserted, updated, or deleted in a database.",
    "general": "General conversation, summaries, or anything that doesn't fit the others.",
}

TEST_SENTENCES = [
    # calculation
    "What is 847 times 23?",
    "Can you compute the square root of 2025?",
    "If I have $500 and spend 35% of it, how much is left?",
    # coding
    "Write a Python function to reverse a linked list.",
    "Why is my for loop throwing an IndexError?",
    "Refactor this SQL query to use a JOIN instead of a subquery.",
    # search
    "What's the weather in Tokyo right now?",
    "Who won the 2024 Super Bowl?",
    "Find me the latest news about SpaceX launches.",
    # database action
    "Delete all rows from the users table where status is inactive.",
    "Insert a new customer record with name and email.",
    "Update the price column for every product in the electronics category.",
    # general
    "Summarize the plot of Romeo and Juliet.",
    "Tell me a joke about programmers.",
    "How are you doing today?",
    # confusing / ambiguous
    "Can you look up how to write a for loop in Python?",
    "Add 5 and 7, then save the result to the database.",
    "What's 2+2, and also what's the capital of France?",
    "Change the timeout value in the config file to 30 seconds.",
    "Explain what a database index is.",
]


def classify(sentence: str) -> tuple[dict, float, dict]:
    """Ask Jev's decisions endpoint for the intent of one sentence.
    Returns (answer_dict, elapsed_seconds, raw_response_json)."""
    payload = {
        "model": MODEL,
        "state": {"message": sentence},
        "questions": {
            "intent": {
                "type": "choice",
                "instructions": "What is the intent of this message?",
                "criteria": INTENT_CRITERIA,
            }
        },
    }
    headers = {
        "Authorization": f"Bearer {API_KEY}",
        "Content-Type": "application/json",
    }

    start = time.time()
    response = SESSION.post(API_URL, headers=headers, json=payload, timeout=30)
    elapsed = time.time() - start
    response.raise_for_status()
    raw = response.json()

    return raw["answers"]["intent"], elapsed, raw


def main():
    os.makedirs("experiments", exist_ok=True)
    saved_raw = False
    print(f"Model: {MODEL}\n")

    for i, sentence in enumerate(TEST_SENTENCES, 1):
        answer, elapsed, raw = classify(sentence)
        intent = answer.get("choice", "UNKNOWN")
        confidence = answer.get("confidence", "?")
        print(f'{i:2}. "{sentence}"')
        print(f"    intent={intent}  confidence={confidence}  time={elapsed:.2f}s")

        if not saved_raw:
            out_path = os.path.join("experiments", "sample_raw_response.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(raw, f, indent=2)
            saved_raw = True

    print(f"\nSaved one full raw response to experiments/sample_raw_response.json")


if __name__ == "__main__":
    main()
