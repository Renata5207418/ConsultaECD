import logging
from datetime import datetime
from typing import Dict, List, Optional

import database
from services.downloads_receitanetbx import localizar_download

logger = logging.getLogger(__name__)

MENSAGEM_AGUARDANDO = (
    "Arquivo ainda não localizado na pasta/logs do ReceitanetBX. "
    "O sistema continuará verificando automaticamente."
)


def verificar_downloads_lote(lote_id: Optional[str], limit: int = 1000) -> Dict:
    """Verifica downloads pendentes de um lote e atualiza o MongoDB.

    Essa função é usada tanto pelo endpoint quanto pelo worker automático.
    """
    consultas = database.listar_consultas_para_verificar_download(lote_id=lote_id, limit=limit)

    encontrados = 0
    aguardando = 0
    erros = 0
    detalhes: List[Dict] = []

    logger.info("[DownloadsLote] Verificação iniciada | lote_id=%s | total=%s", lote_id, len(consultas))

    for consulta in consultas:
        consulta_id = consulta["_id"]
        numero_pedido = consulta.get("numero_pedido")
        ids_arquivos = consulta.get("ids_arquivos") or []
        cnpj = consulta.get("cnpj")

        try:
            info_download = localizar_download(numero_pedido=numero_pedido, ids_arquivos=ids_arquivos, cnpj=cnpj)

            if info_download:
                database.marcar_download_encontrado(consulta_id, info_download)
                encontrados += 1
                detalhes.append({
                    "consulta_id": str(consulta_id),
                    "cnpj": cnpj,
                    "numero_pedido": numero_pedido,
                    "status": "BAIXADO",
                    "arquivo": info_download.get("nome_arquivo_baixado"),
                })
            else:
                database.marcar_download_nao_localizado(consulta_id, MENSAGEM_AGUARDANDO)
                aguardando += 1
                detalhes.append({
                    "consulta_id": str(consulta_id),
                    "cnpj": cnpj,
                    "numero_pedido": numero_pedido,
                    "status": "AGUARDANDO_DOWNLOAD",
                    "mensagem": MENSAGEM_AGUARDANDO,
                })

        except Exception as e:
            logger.exception(
                "[DownloadsLote] Erro ao verificar download | consulta_id=%s | pedido=%s",
                consulta_id,
                numero_pedido,
            )
            database.marcar_erro_download(consulta_id, str(e))
            erros += 1
            detalhes.append({
                "consulta_id": str(consulta_id),
                "cnpj": cnpj,
                "numero_pedido": numero_pedido,
                "status": "ERRO_DOWNLOAD",
                "mensagem": str(e),
            })

    resumo = database.resumo_status(lote_id=lote_id)

    if lote_id:
        database.atualizar_lote(lote_id, {
            "ultima_verificacao_download": datetime.now(),
            "downloads_encontrados_ultima_verificacao": encontrados,
            "downloads_aguardando_ultima_verificacao": aguardando,
            "downloads_erros_ultima_verificacao": erros,
            "resumo_status": resumo,
        })

    logger.info(
        "[DownloadsLote] Verificação concluída | lote_id=%s | encontrados=%s | aguardando=%s | erros=%s",
        lote_id,
        encontrados,
        aguardando,
        erros,
    )

    return {
        "ok": True,
        "lote_id": lote_id,
        "total_verificados": len(consultas),
        "encontrados": encontrados,
        "aguardando": aguardando,
        "erros": erros,
        "resumo": resumo,
        "detalhes": detalhes[:100],
    }
