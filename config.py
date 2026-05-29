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
RECEITANETBX_DOWNLOAD_DIR = Path(
    os.getenv("RECEITANETBX_DOWNLOAD_DIR", BASE_DIR / "downloads_receitanetbx")
)

# Pasta de logs do ReceitanetBX. Se não for informada, usa RECEITANETBX_DOWNLOAD_DIR/log.
RECEITANETBX_LOG_DIR = Path(
    os.getenv("RECEITANETBX_LOG_DIR", RECEITANETBX_DOWNLOAD_DIR / "log")
)

# Pasta onde este sistema gera os ZIPs para o usuário baixar em lote.
ZIP_DIR = Path(os.getenv("ZIP_DIR", RESULT_DIR / "zips"))

# Verificação automática dos downloads após solicitar arquivos.
DOWNLOAD_AUTO_CHECK_ENABLED = os.getenv("DOWNLOAD_AUTO_CHECK_ENABLED", "True").lower() in {"1", "true", "yes", "sim"}
DOWNLOAD_CHECK_INTERVAL_SECONDS = int(os.getenv("DOWNLOAD_CHECK_INTERVAL_SECONDS", "30"))
DOWNLOAD_CHECK_MAX_MINUTES = int(os.getenv("DOWNLOAD_CHECK_MAX_MINUTES", "20"))


def resolver_path(caminho: Path) -> Path:
    if caminho.is_absolute():
        return caminho
    return BASE_DIR / caminho


UPLOAD_DIR = resolver_path(UPLOAD_DIR)
RESULT_DIR = resolver_path(RESULT_DIR)
RECEITANETBX_DOWNLOAD_DIR = resolver_path(RECEITANETBX_DOWNLOAD_DIR)
RECEITANETBX_LOG_DIR = resolver_path(RECEITANETBX_LOG_DIR)
ZIP_DIR = resolver_path(ZIP_DIR)

# Pastas próprias do sistema: podem ser criadas automaticamente.
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
RESULT_DIR.mkdir(parents=True, exist_ok=True)
ZIP_DIR.mkdir(parents=True, exist_ok=True)
