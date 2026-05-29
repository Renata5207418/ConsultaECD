import hashlib
import logging
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional

from config import RECEITANETBX_DOWNLOAD_DIR, RECEITANETBX_LOG_DIR, ZIP_DIR

logger = logging.getLogger(__name__)

EXTENSOES_LOG = {".log", ".txt", ".csv", ".xml"}
EXTENSOES_IGNORADAS_DOWNLOAD = {".log", ".tmp", ".part", ".crdownload"}


def _somente_digitos(valor) -> str:
    return re.sub(r"\D", "", str(valor or ""))


def _limpar_texto(valor) -> str:
    return str(valor or "").strip().strip('"').strip("'").strip()


def _nome_seguro(valor: str) -> str:
    valor = _limpar_texto(valor)
    valor = re.sub(r"[^A-Za-z0-9_. -]", "_", valor)
    valor = re.sub(r"_+", "_", valor).strip(" ._")
    return valor or "arquivo"


def _ler_arquivo_texto(caminho: Path) -> str:
    for encoding in ("utf-8", "latin-1", "cp1252"):
        try:
            return caminho.read_text(encoding=encoding, errors="ignore")
        except Exception:
            continue
    return ""


def _iterar_logs() -> Iterable[Path]:
    if not RECEITANETBX_LOG_DIR.exists():
        return []

    arquivos = []
    for caminho in RECEITANETBX_LOG_DIR.rglob("*"):
        if caminho.is_file() and caminho.suffix.lower() in EXTENSOES_LOG:
            arquivos.append(caminho)

    return sorted(arquivos, key=lambda p: p.stat().st_mtime, reverse=True)


def _iterar_downloads() -> Iterable[Path]:
    if not RECEITANETBX_DOWNLOAD_DIR.exists():
        return []

    arquivos = []
    for caminho in RECEITANETBX_DOWNLOAD_DIR.rglob("*"):
        if not caminho.is_file():
            continue
        if caminho.suffix.lower() in EXTENSOES_IGNORADAS_DOWNLOAD:
            continue
        arquivos.append(caminho)

    return sorted(arquivos, key=lambda p: p.stat().st_mtime, reverse=True)


def _extrair_valores_por_chave(texto: str, chaves: List[str]) -> List[str]:
    valores = []
    for chave in chaves:
        padroes = [
            rf"{re.escape(chave)}\s*[:=]\s*\"([^\"]+)\"",
            rf"{re.escape(chave)}\s*[:=]\s*'([^']+)'",
            rf"{re.escape(chave)}\s*[:=]\s*([^;,\n\r]+)",
        ]
        for padrao in padroes:
            for match in re.finditer(padrao, texto, flags=re.IGNORECASE):
                valor = _limpar_texto(match.group(1))
                if valor:
                    valores.append(valor)
    return valores


def _extrair_caminhos_do_texto(texto: str) -> List[str]:
    candidatos = []

    candidatos.extend(_extrair_valores_por_chave(
        texto,
        [
            "caminhodownload",
            "caminho_download",
            "caminhoDownload",
            "caminho",
            "path",
            "arquivo",
            "nomearquivo",
            "nome_arquivo",
            "filename",
            "nome",
        ],
    ))

    # Caminhos Windows, inclusive com espaços.
    for match in re.finditer(r"[A-Za-z]:\\[^\"'<>|\r\n;]+", texto):
        candidatos.append(match.group(0).strip())

    # Caminhos Linux/Unix.
    for match in re.finditer(r"/(?:[^\s\"'<>|;]+/)+[^\s\"'<>|;]+", texto):
        candidatos.append(match.group(0).strip())

    vistos = set()
    unicos = []
    for item in candidatos:
        item = _limpar_texto(item)
        if not item:
            continue
        chave = item.lower()
        if chave in vistos:
            continue
        vistos.add(chave)
        unicos.append(item)
    return unicos


def _resolver_candidato(candidato: str) -> Optional[Path]:
    if not candidato:
        return None

    candidato = _limpar_texto(candidato)
    candidato = candidato.replace("\\\\", "\\")

    caminho = Path(candidato)
    if caminho.exists() and caminho.is_file():
        return caminho

    # Se veio só o nome do arquivo no log, procura dentro da pasta de downloads.
    nome = Path(candidato).name
    if nome and nome != candidato:
        possivel = RECEITANETBX_DOWNLOAD_DIR / nome
        if possivel.exists() and possivel.is_file():
            return possivel

    if nome:
        nome_lower = nome.lower()
        for arquivo in _iterar_downloads():
            if arquivo.name.lower() == nome_lower:
                return arquivo

    return None


def _arquivo_tem_alvo_no_nome(arquivo: Path, alvos: List[str]) -> bool:
    nome = arquivo.name.lower()
    for alvo in alvos:
        alvo = str(alvo or "").lower().strip()
        if alvo and alvo in nome:
            return True
    return False


def _calcular_md5(caminho: Path) -> str:
    hash_md5 = hashlib.md5()
    with caminho.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            hash_md5.update(chunk)
    return hash_md5.hexdigest()


def _montar_info_download(caminho: Path, origem: str, log_origem: Optional[Path] = None) -> Dict:
    stat = caminho.stat()
    info = {
        "nome_arquivo_baixado": caminho.name,
        "caminho_arquivo_baixado": str(caminho),
        "tamanho_arquivo_baixado": stat.st_size,
        "hash_arquivo_baixado": _calcular_md5(caminho),
        "tipo_hash_arquivo_baixado": "md5",
        "origem_localizacao_download": origem,
        "data_modificacao_arquivo_baixado": datetime.fromtimestamp(stat.st_mtime),
    }
    if log_origem:
        info["log_origem_download"] = str(log_origem)
    return info


def localizar_download(numero_pedido: str, ids_arquivos: List[str], cnpj: Optional[str] = None) -> Optional[Dict]:
    numero_pedido = str(numero_pedido or "").strip()
    ids_arquivos = [str(item).strip() for item in (ids_arquivos or []) if str(item or "").strip()]
    cnpj_limpo = _somente_digitos(cnpj)

    alvos_fortes = [numero_pedido, *ids_arquivos]
    alvos_fortes = [alvo for alvo in alvos_fortes if alvo]

    if not alvos_fortes:
        return None

    logger.info(
        "[DownloadsReceitanetBX] Localizando download | pedido=%s | ids=%s | download_dir=%s | log_dir=%s",
        numero_pedido,
        len(ids_arquivos),
        RECEITANETBX_DOWNLOAD_DIR,
        RECEITANETBX_LOG_DIR,
    )

    # 1) Melhor caminho: logs do ReceitanetBX contendo pedido/id do arquivo.
    for log_path in _iterar_logs():
        texto = _ler_arquivo_texto(log_path)
        if not texto:
            continue

        linhas = texto.splitlines()
        for linha in linhas:
            linha_lower = linha.lower()
            contem_pedido = numero_pedido and numero_pedido.lower() in linha_lower
            contem_id = any(id_arquivo.lower() in linha_lower for id_arquivo in ids_arquivos)

            if not (contem_pedido or contem_id):
                continue

            candidatos = _extrair_caminhos_do_texto(linha)
            for candidato in candidatos:
                caminho = _resolver_candidato(candidato)
                if caminho:
                    logger.info(
                        "[DownloadsReceitanetBX] Arquivo localizado via log | pedido=%s | arquivo=%s | log=%s",
                        numero_pedido,
                        caminho,
                        log_path,
                    )
                    return _montar_info_download(caminho, origem="log_receitanetbx", log_origem=log_path)

    # 2) Fallback: procurar arquivo pelo número do pedido ou idarquivo no nome.
    for arquivo in _iterar_downloads():
        if _arquivo_tem_alvo_no_nome(arquivo, alvos_fortes):
            logger.info(
                "[DownloadsReceitanetBX] Arquivo localizado pelo nome | pedido=%s | arquivo=%s",
                numero_pedido,
                arquivo,
            )
            return _montar_info_download(arquivo, origem="nome_arquivo")

    # 3) Fallback mais fraco: CNPJ no nome, somente se houver exatamente 1 candidato.
    if cnpj_limpo:
        candidatos_cnpj = [arquivo for arquivo in _iterar_downloads() if cnpj_limpo in arquivo.name]
        if len(candidatos_cnpj) == 1:
            arquivo = candidatos_cnpj[0]
            logger.info(
                "[DownloadsReceitanetBX] Arquivo localizado pelo CNPJ no nome | pedido=%s | arquivo=%s",
                numero_pedido,
                arquivo,
            )
            return _montar_info_download(arquivo, origem="cnpj_nome_arquivo")

    logger.info("[DownloadsReceitanetBX] Arquivo ainda não localizado | pedido=%s", numero_pedido)
    return None


def criar_zip_lote(consultas_baixadas: List[Dict], lote_id: str) -> Dict:
    if not consultas_baixadas:
        raise ValueError("Nenhum arquivo baixado encontrado para gerar ZIP.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    lote_limpo = _nome_seguro(str(lote_id or "atual"))[:24]
    caminho_zip = ZIP_DIR / f"ecd_lote_{lote_limpo}_{timestamp}.zip"
    caminho_zip.parent.mkdir(parents=True, exist_ok=True)

    adicionados = 0
    nomes_usados = set()

    with zipfile.ZipFile(caminho_zip, "w", compression=zipfile.ZIP_DEFLATED) as zipf:
        for consulta in consultas_baixadas:
            caminho = Path(str(consulta.get("caminho_arquivo_baixado") or ""))
            if not caminho.exists() or not caminho.is_file():
                logger.warning("[DownloadsReceitanetBX] Ignorando arquivo inexistente no ZIP: %s", caminho)
                continue

            codigo = _nome_seguro(str(consulta.get("codigo") or "sem_codigo"))
            cnpj = _somente_digitos(consulta.get("cnpj")) or "sem_cnpj"
            pedido = _nome_seguro(str(consulta.get("numero_pedido") or "sem_pedido"))
            pasta = f"{codigo}_{cnpj}_{pedido}"
            arcname = f"{pasta}/{caminho.name}"

            if arcname in nomes_usados:
                base = caminho.stem
                ext = caminho.suffix
                contador = 2
                while f"{pasta}/{base}_{contador}{ext}" in nomes_usados:
                    contador += 1
                arcname = f"{pasta}/{base}_{contador}{ext}"

            nomes_usados.add(arcname)
            zipf.write(caminho, arcname=arcname)
            adicionados += 1

    if adicionados == 0:
        try:
            caminho_zip.unlink(missing_ok=True)
        except Exception:
            pass
        raise ValueError("Nenhum arquivo físico válido foi encontrado para adicionar ao ZIP.")

    return {
        "caminho_zip": caminho_zip,
        "nome_zip": caminho_zip.name,
        "quantidade_arquivos": adicionados,
        "tamanho_zip": caminho_zip.stat().st_size,
    }
