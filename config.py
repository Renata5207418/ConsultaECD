import os
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

FLASK_HOST = os.getenv("FLASK_HOST", "0.0.0.0")
FLASK_PORT = int(os.getenv("FLASK_PORT", "6550"))
FLASK_DEBUG = os.getenv("FLASK_DEBUG", "False").lower() in {"1", "true", "yes", "sim"}

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "consulta_ecd")

RECEITANETBX_ENDPOINT = os.getenv(
    "RECEITANETBX_ENDPOINT",
    "http://127.0.0.1:2443/services/ReceitanetBX",
)

UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", BASE_DIR / "uploads"))
RESULT_DIR = Path(os.getenv("RESULT_DIR", BASE_DIR / "resultados"))

if not UPLOAD_DIR.is_absolute():
    UPLOAD_DIR = BASE_DIR / UPLOAD_DIR

if not RESULT_DIR.is_absolute():
    RESULT_DIR = BASE_DIR / RESULT_DIR

UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
RESULT_DIR.mkdir(parents=True, exist_ok=True)