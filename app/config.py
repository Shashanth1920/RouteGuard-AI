"""File 3: settings in one place. Nothing here reads .env directly anywhere else."""
import os

from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
JEV_MODEL = os.getenv("JEV_MODEL", "typesafe/jev-1.13")  # pinned, not ~typesafe/jev-latest
JEV_TIMEOUT = float(os.getenv("JEV_TIMEOUT", "10"))

# Router cutoffs. Chosen from real Decision data on our 25 test sentences
# (see results/part2_router.md), not guessed.

# "Update the price column..." (routine DB write) scored risk=0.22.
# "Email all 50,000 users a password reset link" (genuinely dangerous -
# mass unsolicited email) scored risk=0.66. A cutoff of 0.7 would let the
# email sentence through to a cheap model; 0.5 sits comfortably between
# the two and still leaves a wide margin below the truly destructive
# sentences (drop table / wipe DB / delete all users, all 0.93-0.98).
RISK_CUTOFF = 0.5

# Clean unrelated sentences all scored intent_confidence >= 0.87. Only the
# two genuinely double-barreled/ambiguous sentences ("what's 2+2, and
# also what's the capital of France?" and "change the timeout in the
# config file", which straddles coding vs. action) dropped to 0.58 and
# 0.41. 0.7 sits in the gap between 0.58 and 0.87, so it catches both
# ambiguous cases without flagging anything Jev was actually sure about.
INTENT_CONFIDENCE_CUTOFF = 0.7

# Every sentence that genuinely needs a tool and isn't already caught by
# an earlier rule scored needs_tool >= 0.42 (the 3 math sentences that
# reach this rule: 0.42-0.53). Every sentence that reaches this rule and
# doesn't need a tool scored <= 0.11. 0.4 sits in that gap. Known miss:
# "Who won the 2024 Super Bowl?" scores needs_tool=0.24 even though a
# search tool would be more reliable than the model's own memory - that's
# a weakness in Jev's own scoring for search-flavored questions, not
# something this cutoff can fix.
NEEDS_TOOL_CUTOFF = 0.4
