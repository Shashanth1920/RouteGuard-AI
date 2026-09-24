"""One list of every tool + its label. The Safety Gate (Part 5) reads risk
and destructive from here the same way a hospital locks drawers based on
what's inside them - it doesn't need to know how any tool works internally."""
from app.tools import calculator, database, search

TOOLS = [
    {
        "name": "calculator",
        "description": "Evaluate a basic math expression (+ - * / % **).",
        "risk": "low",
        "destructive": False,
        "func": calculator.calculate,
    },
    {
        "name": "search",
        "description": "Search the web and return the top 3 results.",
        "risk": "medium",
        "destructive": False,
        "func": search.search,
    },
    {
        "name": "list_users",
        "description": "List all users in the fake database.",
        "risk": "low",
        "destructive": False,
        "func": database.list_users,
    },
    {
        "name": "read_user",
        "description": "Read one user by id from the fake database.",
        "risk": "low",
        "destructive": False,
        "func": database.read_user,
    },
    {
        "name": "delete_user",
        "description": "Delete a user by id from the fake database. Irreversible.",
        "risk": "high",
        "destructive": True,
        "func": database.delete_user,
    },
]
