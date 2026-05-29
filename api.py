import logging
from datetime import datetime
from pathlib import Path

from bson import ObjectId
from flask import Blueprint, jsonify, request, send_file
from werkzeug.utils import secure_filename

import database
from config import RESULT_DIR, UPLOAD_DIR
from services.planilha import exportar_consultas_excel, ler_planilha_entrada
from worker import WorkerECD

logger = logging.getLogger(__name__)

api_bp = Blueprint("api", __name__)
worker_ecd = WorkerECD()


def doc_to_json(doc):
    if not doc:
        return None

    item = dict(doc)
    item["id"] = str(item.pop("_id"))

    for chave, valor in list(item.items()):
        if isinstance(valor, ObjectId):
            item[chave] = str(valor)
        elif isinstance(valor, datetime):
            item[chave] = valor.strftime("%d/%m/%Y %H:%M:%S")
        elif isinstance(valor, Path):
            item[chave] = str(valor)

    return item


def erro_json(mensagem: str, status: int = 400):
    return jsonify({"ok": False, "erro": mensagem}), status


def form_bool(nome: str, padrao: bool = False) -> bool:
    valor = request.form.get(nome)
    if valor is None:
        return padrao
    return str(valor).lower() in {"1", "true", "sim", "on", "yes"}


def lote_atual_id() -> str | None:
    lote = database.obter_lote_mais_recente()
    return str(lote["_id"]) if lote else None


@api_bp.get("/status")
def status():
    lote = database.obter_lote_mais_recente()
    lote_id = str(lote["_id"]) if lote else None

    return jsonify({
        "ok": True,
        "resumo": database.resumo_status(lote_id=lote_id),
        "worker": worker_ecd.status(),
        "lote_atual": doc_to_json(lote) if lote else None,
    })


@api_bp.get("/lotes")
def lotes():
    return jsonify({
        "ok": True,
        "lotes": [doc_to_json(lote) for lote in database.listar_lotes()],
    })


@api_bp.post("/importar")
def importar():
    arquivo = request.files.get("arquivo")
    if not arquivo:
        return erro_json("Nenhum arquivo enviado.")

    ano_calendario = request.form.get("ano_calendario", "2024")
    solicitar = form_bool("solicitar", False)
    iniciar_apos_importar = form_bool("iniciar", False)

    try:
        ano_calendario = int(ano_calendario)
    except ValueError:
        return erro_json("Ano-calendário inválido.")

    nome_seguro = secure_filename(arquivo.filename or "planilha.xlsx")
    if not nome_seguro.lower().endswith(".xlsx"):
        return erro_json("Por enquanto, envie apenas planilhas .xlsx.")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    caminho_arquivo = UPLOAD_DIR / f"{timestamp}_{nome_seguro}"
    arquivo.save(caminho_arquivo)

    lote_id = database.criar_lote(
        nome_original=arquivo.filename or nome_seguro,
        caminho_arquivo=str(caminho_arquivo),
        ano_calendario=ano_calendario,
        solicitar=solicitar,
    )

    logger.info(
        "[API] Planilha recebida | arquivo=%s | lote_id=%s | ano=%s | solicitar=%s | iniciar=%s",
        arquivo.filename,
        lote_id,
        ano_calendario,
        solicitar,
        iniciar_apos_importar,
    )

    try:
        leitura = ler_planilha_entrada(caminho_arquivo, ano_calendario, lote_id)
        inseridos, atualizados = database.salvar_consultas_importadas(leitura["registros"])

        database.atualizar_lote(lote_id, {
            "status": "IMPORTADO",
            "total_registros": leitura["total_registros"],
            "total_validos": leitura["total_validos_unicos"],
            "total_invalidos": leitura["invalidos"],
            "ignorados": leitura["ignorados"],
            "coluna_cnpj": leitura["coluna_cnpj"],
            "coluna_codigo": leitura["coluna_codigo"],
            "coluna_razao_social": leitura["coluna_razao_social"],
        })

        worker_iniciado = False
        worker_mensagem = None

        if iniciar_apos_importar and leitura["total_validos_unicos"] > 0:
            try:
                worker_ecd.iniciar(
                    tamanho_lote=100,
                    solicitar=solicitar,
                    pausa=1.0,
                    lote_id=lote_id,
                )
                worker_iniciado = True
                worker_mensagem = "Consultas iniciadas automaticamente."
                logger.info("[API] Worker iniciado automaticamente | lote_id=%s", lote_id)
            except Exception as e:
                worker_mensagem = str(e)
                logger.warning("[API] Não foi possível iniciar worker automaticamente | lote_id=%s | erro=%s", lote_id, e)

        return jsonify({
            "ok": True,
            "resultado": {
                "lote_id": lote_id,
                "coluna_cnpj": leitura["coluna_cnpj"],
                "coluna_codigo": leitura["coluna_codigo"],
                "coluna_razao_social": leitura["coluna_razao_social"],
                "inseridos": inseridos,
                "atualizados": atualizados,
                "ignorados": leitura["ignorados"],
                "invalidos": leitura["invalidos"],
                "total_validos_unicos": leitura["total_validos_unicos"],
                "total_registros": leitura["total_registros"],
            },
            "worker_iniciado": worker_iniciado,
            "worker_mensagem": worker_mensagem,
            "worker": worker_ecd.status(),
        })

    except Exception as e:
        logger.exception("[API] Erro ao importar planilha | lote_id=%s", lote_id)
        database.atualizar_lote(lote_id, {
            "status": "ERRO_IMPORTACAO",
            "erro": str(e),
        })
        return erro_json(str(e), 500)


@api_bp.get("/consultas")
def consultas():
    status_filtro = request.args.get("status") or None
    limit = int(request.args.get("limit", 500))
    lote_id = request.args.get("lote_id") or None

    if lote_id == "atual":
        lote_id = lote_atual_id()

    docs = database.listar_consultas(status=status_filtro, limit=limit, lote_id=lote_id)

    return jsonify({
        "ok": True,
        "consultas": [doc_to_json(doc) for doc in docs],
    })


@api_bp.post("/iniciar")
def iniciar():
    body = request.get_json(silent=True) or {}
    tamanho_lote = int(body.get("tamanho_lote", 100))
    solicitar = bool(body.get("solicitar", False))
    pausa = float(body.get("pausa", 1.0))
    lote_id = body.get("lote_id") or lote_atual_id()

    if not lote_id:
        return erro_json("Nenhum lote encontrado para iniciar.", 404)

    try:
        worker_ecd.iniciar(tamanho_lote=tamanho_lote, solicitar=solicitar, pausa=pausa, lote_id=lote_id)
        logger.info("[API] Worker iniciado manualmente | lote_id=%s", lote_id)
        return jsonify({"ok": True, "worker": worker_ecd.status(), "lote_id": lote_id})
    except Exception as e:
        return erro_json(str(e), 400)


@api_bp.post("/pausar")
def pausar():
    return jsonify({"ok": True, "worker": worker_ecd.pausar()})


@api_bp.post("/continuar")
def continuar():
    return jsonify({"ok": True, "worker": worker_ecd.continuar()})


@api_bp.post("/parar")
def parar():
    return jsonify({"ok": True, "worker": worker_ecd.parar()})


@api_bp.post("/reprocessar-erros")
def reprocessar_erros():
    body = request.get_json(silent=True) or {}
    lote_id = body.get("lote_id") or lote_atual_id()
    modificados = database.reprocessar_erros(lote_id=lote_id)
    logger.info("[API] Reprocessamento solicitado | lote_id=%s | modificados=%s", lote_id, modificados)
    return jsonify({"ok": True, "modificados": modificados, "lote_id": lote_id})


@api_bp.get("/exportar")
def exportar():
    lote_id = request.args.get("lote_id") or None
    if lote_id == "atual":
        lote_id = lote_atual_id()

    consultas_exportacao = database.listar_consultas_para_exportacao(lote_id=lote_id)

    if not consultas_exportacao:
        return erro_json("Nenhuma consulta encontrada para exportar.", 404)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    sufixo_lote = f"_{lote_id}" if lote_id else ""
    caminho_saida = RESULT_DIR / f"resultado_ecd{sufixo_lote}_{timestamp}.xlsx"

    exportar_consultas_excel(consultas_exportacao, caminho_saida)
    logger.info("[API] Excel exportado | lote_id=%s | arquivo=%s", lote_id, caminho_saida)

    return send_file(
        caminho_saida,
        as_attachment=True,
        download_name=caminho_saida.name,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )
