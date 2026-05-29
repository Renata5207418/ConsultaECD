from datetime import datetime
from typing import Dict, List, Optional, Tuple

from bson import ObjectId
from pymongo import ASCENDING, DESCENDING, MongoClient, UpdateOne

from config import MONGO_DB, MONGO_URI

_client = MongoClient(MONGO_URI)
_db = _client[MONGO_DB]


def get_db():
    return _db


def init_db() -> None:
    consultas = _db.consultas
    lotes = _db.lotes

    consultas.create_index([("lote_id", ASCENDING), ("cnpj", ASCENDING), ("ano_calendario", ASCENDING)], unique=True)
    consultas.create_index([("status", ASCENDING), ("updated_at", DESCENDING)])
    consultas.create_index([("created_at", DESCENDING)])
    consultas.create_index([("lote_id", ASCENDING), ("status", ASCENDING)])

    lotes.create_index([("created_at", DESCENDING)])
    lotes.create_index([("status", ASCENDING)])

    resetar_processando_orfaos()


def agora() -> datetime:
    return datetime.now()


def criar_lote(nome_original: str, caminho_arquivo: str, ano_calendario: int, solicitar: bool = False) -> str:
    doc = {
        "nome_original": nome_original,
        "caminho_arquivo": caminho_arquivo,
        "ano_calendario": ano_calendario,
        "solicitar": solicitar,
        "status": "IMPORTADO",
        "total_registros": 0,
        "total_validos": 0,
        "total_invalidos": 0,
        "ignorados": 0,
        "created_at": agora(),
        "updated_at": agora(),
        "started_at": None,
        "finished_at": None,
    }
    result = _db.lotes.insert_one(doc)
    return str(result.inserted_id)


def atualizar_lote(lote_id: str, dados: Dict) -> None:
    if not lote_id:
        return
    dados["updated_at"] = agora()
    _db.lotes.update_one({"_id": ObjectId(lote_id)}, {"$set": dados})


def obter_lote(lote_id: str) -> Optional[Dict]:
    if not lote_id:
        return None
    return _db.lotes.find_one({"_id": ObjectId(lote_id)})


def obter_lote_mais_recente() -> Optional[Dict]:
    return _db.lotes.find_one(sort=[("created_at", DESCENDING)])


def listar_lotes(limit: int = 20) -> List[Dict]:
    return list(_db.lotes.find().sort("created_at", DESCENDING).limit(limit))


def salvar_consultas_importadas(registros: List[Dict]) -> Tuple[int, int]:
    if not registros:
        return 0, 0

    operacoes = []
    for registro in registros:
        filtro = {
            "lote_id": registro["lote_id"],
            "cnpj": registro["cnpj"],
            "ano_calendario": registro["ano_calendario"],
        }

        # MongoDB não permite atualizar o mesmo campo em $setOnInsert e $set
        # na mesma operação de upsert. Por isso, campos que podem ser atualizados
        # ficam apenas no $set; os demais entram somente quando o documento nasce.
        campos_atualizaveis = {
            "codigo": registro.get("codigo"),
            "razao_social": registro.get("razao_social"),
            "cnpj_original": registro.get("cnpj_original"),
            "linha_planilha": registro.get("linha_planilha"),
            "updated_at": agora(),
        }

        registro_insercao = dict(registro)
        for campo in campos_atualizaveis:
            registro_insercao.pop(campo, None)

        operacoes.append(
            UpdateOne(
                filtro,
                {
                    "$setOnInsert": registro_insercao,
                    "$set": campos_atualizaveis,
                },
                upsert=True,
            )
        )

    result = _db.consultas.bulk_write(operacoes, ordered=False)
    inseridos = len(result.upserted_ids or {})
    atualizados = result.modified_count
    return inseridos, atualizados


def resumo_status(lote_id: Optional[str] = None) -> Dict:
    match = {}
    if lote_id:
        match["lote_id"] = lote_id

    pipeline = []
    if match:
        pipeline.append({"$match": match})

    pipeline.extend([
        {"$group": {"_id": "$status", "total": {"$sum": 1}}},
    ])

    resumo = {item["_id"]: item["total"] for item in _db.consultas.aggregate(pipeline)}

    # Mantém chaves previsíveis para o front não depender de ifs espalhados.
    for chave in ["PENDENTE", "PROCESSANDO", "ENCONTRADO", "SOLICITADO", "NAO_ENCONTRADA", "CNPJ_INVALIDO", "ERRO"]:
        resumo.setdefault(chave, 0)

    resumo["TOTAL"] = sum(valor for chave, valor in resumo.items() if chave != "TOTAL")
    resumo["FINALIZADAS"] = resumo["ENCONTRADO"] + resumo["SOLICITADO"] + resumo["NAO_ENCONTRADA"] + resumo["CNPJ_INVALIDO"] + resumo["ERRO"]
    return resumo


def listar_consultas(status: Optional[str] = None, limit: int = 500, lote_id: Optional[str] = None) -> List[Dict]:
    filtro = {}
    if status:
        filtro["status"] = status
    if lote_id:
        filtro["lote_id"] = lote_id

    limit = min(max(int(limit or 500), 1), 2000)

    return list(
        _db.consultas
        .find(filtro)
        .sort([("updated_at", DESCENDING), ("created_at", DESCENDING)])
        .limit(limit)
    )


def listar_consultas_para_exportacao(lote_id: Optional[str] = None) -> List[Dict]:
    filtro = {}
    if lote_id:
        filtro["lote_id"] = lote_id

    return list(
        _db.consultas
        .find(filtro)
        .sort([("codigo", ASCENDING), ("razao_social", ASCENDING), ("cnpj", ASCENDING)])
    )


def buscar_pendentes(limit: int, lote_id: Optional[str] = None) -> List[Dict]:
    """Busca apenas pendentes do lote atual quando lote_id for informado.

    Esse detalhe evita o comportamento confuso de importar uma planilha nova e o
    worker sair processando pendências antigas de outros lotes.
    """
    limit = min(max(int(limit or 100), 1), 500)
    filtro = {"status": "PENDENTE"}
    if lote_id:
        filtro["lote_id"] = lote_id

    return list(
        _db.consultas
        .find(filtro)
        .sort([("created_at", ASCENDING)])
        .limit(limit)
    )


def marcar_processando(consulta_id: ObjectId) -> bool:
    result = _db.consultas.update_one(
        {"_id": consulta_id, "status": "PENDENTE"},
        {
            "$set": {
                "status": "PROCESSANDO",
                "updated_at": agora(),
                "inicio_processamento": agora(),
            },
            "$inc": {"tentativas": 1},
        },
    )
    return result.modified_count == 1


def atualizar_consulta(consulta_id: ObjectId, dados: Dict) -> None:
    dados["updated_at"] = agora()
    _db.consultas.update_one({"_id": consulta_id}, {"$set": dados})


def reprocessar_erros(lote_id: Optional[str] = None) -> int:
    filtro = {"status": {"$in": ["ERRO", "CNPJ_INVALIDO"]}}
    if lote_id:
        filtro["lote_id"] = lote_id

    result = _db.consultas.update_many(
        filtro,
        {
            "$set": {
                "status": "PENDENTE",
                "observacao": "Reprocessamento solicitado pelo usuário.",
                "updated_at": agora(),
            }
        },
    )
    return result.modified_count


def resetar_processando_orfaos() -> int:
    result = _db.consultas.update_many(
        {"status": "PROCESSANDO"},
        {
            "$set": {
                "status": "PENDENTE",
                "observacao": "Consulta voltou para pendente após reinício do sistema.",
                "updated_at": agora(),
            }
        },
    )
    return result.modified_count
