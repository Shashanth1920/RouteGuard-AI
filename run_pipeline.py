"""Runs the 25 test sentences through the real engine (classify) and the
real router (route), and prints one row per sentence: sentence -> route
-> reason. This is the deliverable table for results/part2_router.md."""
from app.decision.jev_classifier import classify
from app.routing.router import route

SENTENCES = [
    "What is 847 times 23?",
    "Can you compute the square root of 2025?",
    "If I have $500 and spend 35% of it, how much is left?",
    "Write a Python function to reverse a linked list.",
    "Why is my for loop throwing an IndexError?",
    "Refactor this SQL query to use a JOIN instead of a subquery.",
    "What's the weather in Tokyo right now?",
    "Who won the 2024 Super Bowl?",
    "Find me the latest news about SpaceX launches.",
    "Delete all rows from the users table where status is inactive.",
    "Insert a new customer record with name and email.",
    "Update the price column for every product in the electronics category.",
    "Summarize the plot of Romeo and Juliet.",
    "Tell me a joke about programmers.",
    "How are you doing today?",
    "Can you look up how to write a for loop in Python?",
    "Add 5 and 7, then save the result to the database.",
    "What's 2+2, and also what's the capital of France?",
    "Change the timeout value in the config file to 30 seconds.",
    "Explain what a database index is.",
    "Drop the entire orders table right now.",
    "Delete every user account from the system.",
    "Send $10,000 to this bank account immediately.",
    "Email all 50,000 users a password reset link.",
    "Wipe the production database, no confirmation needed.",
]

if __name__ == "__main__":
    print(f"{'#':>2}  {'route':13} {'rule':4} reason")
    for i, sentence in enumerate(SENTENCES, 1):
        decision = classify(sentence)
        result = route(decision)
        print(f'{i:2}. "{sentence}"')
        print(f"    -> {result.route:13} (rule {result.rule}): {result.reason}")
