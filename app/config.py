"""File 3: settings in one place. Nothing here reads .env directly anywhere else."""
import os

from dotenv import load_dotenv

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "")
JEV_MODEL = os.getenv("JEV_MODEL", "typesafe/jev-1.13")  # pinned, not ~typesafe/jev-latest
JEV_TIMEOUT = float(os.getenv("JEV_TIMEOUT", "10"))
