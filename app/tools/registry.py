"""One list of every tool + its label. The Safety Gate (Part 5) reads risk
and destructive from here the same way a hospital locks drawers based on
what's inside them - it doesn't need to know how any tool works internally.
`params` is a JSON-schema of each tool's arguments, used by the Part 4
agent to build OpenAI-style tool-calling schemas."""
from app.tools import calculator, database, search

TOOLS = [
    {
        "name": "calculator",
        "description": "Evaluate a basic math expression (+ - * / % **).",
        "risk": "low",
        "destructive": False,
        "func": calculator.calculate,
        "params": {
            "type": "object",
            "properties": {"expression": {"type": "string", "description": "e.g. '847 * 23'"}},
            "required": ["expression"],
        },
    },
    {
        "name": "search",
        "description": "Search the web and return the top 3 results.",
        "risk": "medium",
        "destructive": False,
        "func": search.search,
        "params": {
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    },
    {
        "name": "list_users",
        "description": "List all users in the fake database.",
        "risk": "low",
        "destructive": False,
        "func": database.list_users,
        "params": {"type": "object", "properties": {}, "required": []},
    },
    {
        "name": "read_user",
        "description": "Read one user by id from the fake database.",
        "risk": "low",
        "destructive": False,
        "func": database.read_user,
        "params": {
            "type": "object",
            "properties": {"user_id": {"type": "integer"}},
            "required": ["user_id"],
        },
    },
    {
        "name": "delete_user",
        "description": "Delete a user by id from the fake database. Irreversible.",
        "risk": "high",
        "destructive": True,
        "func": database.delete_user,
        "params": {
            "type": "object",
            "properties": {"user_id": {"type": "integer"}},
            "required": ["user_id"],
        },
    },
]
