"""
Part 2 - Decision Engine: one Jev call per sentence, four questions at once.

Extends Part 1's intent question with three more, all answered in a
single request per sentence:
  - intent      (choice) - kept from Part 1
  - complexity  (score)  - how hard the request is to fulfill
  - risk        (noul)   - could it cause irreversible harm
  - needs_tool  (noul)   - does answering require an external system

Uses the same 20 sentences from Part 1 plus 5 new "risky" ones, and
pins the model version so results stay comparable across runs.
"""
import json
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv

EXPERIMENTS_DIR = Path(__file__).parent / "experiments"  # this script's own folder, not the caller's cwd

load_dotenv()

API_KEY = os.getenv("OPENROUTER_API_KEY")
if not API_KEY:
    raise SystemExit("OPENROUTER_API_KEY not found in .env")

API_URL = "https://openrouter.ai/api/alpha/decisions"
MODEL = os.getenv("JEV_MODEL", "typesafe/jev-1.13")  # pinned, not the floating "~typesafe/jev-latest" alias
SESSION = requests.Session()

QUESTIONS = {
    "intent": {
        "type": "choice",
        "instructions": "What is the intent of this message?",
        "criteria": {
            "calculation": "The user wants a math computation or numeric result.",
            "coding": "The user wants code written, debugged, reviewed, or explained.",
            "search": "The user wants current facts, news, or information looked up.",
            "database action": "The user wants data inserted, updated, or deleted in a database.",
            "action": "The user wants something done that has a real-world effect "
                      "outside the conversation - moving money, sending a message or "
                      "email to many people, or triggering an external system.",
            "general": "General conversation, summaries, or anything that doesn't fit the others.",
        },
    },
    "complexity": {
        "type": "score",
        "instructions": "How complex is it to fulfill this request?",
        "criteria": [
            "Simple: a single fact, a quick reply, or one obvious step with no "
            "real reasoning or domain knowledge required.",
            "Moderate: a few steps, some domain knowledge, or careful wording "
            "needed to get right.",
            "Complex: multi-step reasoning, deep domain knowledge, or high "
            "precision needed - getting it wrong is easy.",
        ],  # ordered low to high
    },
    "risk": {
        "type": "noul",
        "instructions": "Could carrying out this request cause irreversible harm?",
        "criteria": {
            "true": "The action is destructive or hard to undo: deleting or dropping "
                    "data, moving money, or messaging a large number of people at once.",
            "false": "The action is safe and reversible, or purely informational - "
                     "nothing is destroyed, spent, or sent at scale.",
        },
    },
    "needs_tool": {
        "type": "noul",
        "instructions": "Does answering this require calling an external tool or "
                         "system, rather than just replying in natural language?",
        "criteria": {
            "true": "Requires running code, querying or modifying a database, "
                    "searching the web, or computing an exact numeric result - "
                    "this includes ANY arithmetic or math, even something that "
                    "looks simple like 847 x 23, since the model itself is "
                    "unreliable at math and must hand it to a calculator.",
            "false": "Answerable from conversation or general knowledge alone, "
                     "no external system needed.",
        },
    },
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
    # new: risky
    "Drop the entire orders table right now.",
    "Delete every user account from the system.",
    "Send $10,000 to this bank account immediately.",
    "Email all 50,000 users a password reset link.",
    "Wipe the production database, no confirmation needed.",
]


def decide(sentence: str) -> tuple[dict, float, dict]:
    """One Jev call, all 4 questions at once. Returns (answers, elapsed, raw)."""
    payload = {
        "model": MODEL,
        "state": {"message": sentence},
        "questions": QUESTIONS,
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
    return raw["answers"], elapsed, raw


def main():
    os.makedirs(EXPERIMENTS_DIR, exist_ok=True)
    saved_raw = False
    call_count = 0
    total_time = 0.0
    print(f"Model: {MODEL}\n")

    for i, sentence in enumerate(TEST_SENTENCES, 1):
        answers, elapsed, raw = decide(sentence)
        call_count += 1
        total_time += elapsed

        intent = answers["intent"]["choice"]
        complexity = answers["complexity"]["score"]
        risk = answers["risk"]["noul"]
        needs_tool = answers["needs_tool"]["noul"]

        print(f'{i:2}. "{sentence}"')
        print(
            f"    intent={intent}  complexity={complexity:.2f}  "
            f"risk={risk:.2f}  needs_tool={needs_tool:.2f}  time={elapsed:.2f}s"
        )

        if not saved_raw:
            out_path = EXPERIMENTS_DIR / "part2_raw_response.json"
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(raw, f, indent=2)
            saved_raw = True

    one_call_each = call_count == len(TEST_SENTENCES)
    print(f"\n{call_count} API calls for {len(TEST_SENTENCES)} sentences "
          f"(one call per sentence: {one_call_each})")
    print(f"Average time per call: {total_time / call_count:.2f}s")
    print(f"Saved one full raw response to {EXPERIMENTS_DIR / 'part2_raw_response.json'}")


if __name__ == "__main__":
    main()
