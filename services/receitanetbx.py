import html
import logging
import re
import time
import xml.etree.ElementTree as ET
from typing import Dict, List, Optional, Tuple

import requests

from config import RECEITANETBX_ENDPOINT

logger = logging.getLogger(__name__)

PERFIL = "proc"
SISTEMA = "SPED Contábil"
TIPO_ARQUIVO = "Escrituração Contábil Digital"
TIPO_PESQUISA = "Por Período da Escrituração"


def limpar_cnpj(cnpj: str) -> str:
    return re.sub(r"\D", "", str(cnpj or ""))


def periodo_ano(ano: int) -> Tuple[str, str]:
    return f"{ano}-01-01", f"{ano}-12-31"


def montar_envelope(operacao: str, xml_entrada: str) -> str:
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:axis2="http://ws.apache.org/axis2">
  <soapenv:Header/>
  <soapenv:Body>
    <axis2:{operacao}>
      <axis2:entrada><![CDATA[
{xml_entrada}
      ]]></axis2:entrada>
    </axis2:{operacao}>
  </soapenv:Body>
</soapenv:Envelope>
"""


def chamar_soap(operacao: str, xml_entrada: str, timeout: int = 120) -> Dict:
    envelope = montar_envelope(operacao, xml_entrada)

    headers = {
        "Content-Type": "text/xml; charset=utf-8",
        "SOAPAction": f"urn:{operacao}",
    }

    resultado = {
        "http_status": None,
        "operacao": operacao,
        "retorno": None,
        "saida_xml": None,
        "mensagem": None,
        "raw": None,
    }

    inicio = time.perf_counter()
    logger.info("[ReceitanetBX] Enviando SOAP | operacao=%s | endpoint=%s", operacao, RECEITANETBX_ENDPOINT)

    try:
        response = requests.post(
            RECEITANETBX_ENDPOINT,
            data=envelope.encode("utf-8"),
            headers=headers,
            timeout=timeout,
        )

        duracao = time.perf_counter() - inicio
        resultado["http_status"] = response.status_code
        resultado["raw"] = response.text

        if response.status_code != 200:
            resultado["mensagem"] = f"HTTP {response.status_code}"
            logger.warning(
                "[ReceitanetBX] Resposta SOAP com HTTP inesperado | operacao=%s | http=%s | duracao=%.2fs",
                operacao,
                response.status_code,
                duracao,
            )
            return resultado

        root = ET.fromstring(response.content)

        retorno_el = root.find(".//{http://ws.apache.org/axis2}retorno")
        saida_el = root.find(".//{http://ws.apache.org/axis2}saida")

        resultado["retorno"] = int(retorno_el.text) if retorno_el is not None and retorno_el.text else None

        saida_escapada = saida_el.text if saida_el is not None else ""
        saida_xml = html.unescape(saida_escapada or "").strip()

        resultado["saida_xml"] = saida_xml

        if saida_xml:
            saida_root = ET.fromstring(saida_xml.encode("utf-8"))
            msg_el = saida_root.find(".//mensagem")
            resultado["mensagem"] = msg_el.text if msg_el is not None else None

        logger.info(
            "[ReceitanetBX] Resposta SOAP recebida | operacao=%s | http=%s | retorno=%s | duracao=%.2fs | mensagem=%s",
            operacao,
            resultado.get("http_status"),
            resultado.get("retorno"),
            duracao,
            resultado.get("mensagem"),
        )
        return resultado

    except requests.exceptions.ConnectionError:
        duracao = time.perf_counter() - inicio
        resultado["mensagem"] = (
            "Não foi possível conectar ao ReceitanetBX. "
            f"Verifique se o serviço está rodando em {RECEITANETBX_ENDPOINT}."
        )
        logger.exception(
            "[ReceitanetBX] Falha de conexão | operacao=%s | endpoint=%s | duracao=%.2fs",
            operacao,
            RECEITANETBX_ENDPOINT,
            duracao,
        )
        return resultado

    except requests.exceptions.Timeout:
        duracao = time.perf_counter() - inicio
        resultado["mensagem"] = "Timeout ao consultar o ReceitanetBX."
        logger.warning(
            "[ReceitanetBX] Timeout | operacao=%s | endpoint=%s | timeout=%s | duracao=%.2fs",
            operacao,
            RECEITANETBX_ENDPOINT,
            timeout,
            duracao,
        )
        return resultado

    except Exception as e:
        duracao = time.perf_counter() - inicio
        resultado["mensagem"] = f"Erro ao consultar ReceitanetBX: {e}"
        logger.exception(
            "[ReceitanetBX] Erro inesperado | operacao=%s | endpoint=%s | duracao=%.2fs",
            operacao,
            RECEITANETBX_ENDPOINT,
            duracao,
        )
        return resultado


def montar_xml_pesquisa(cnpj: str, ano: int) -> str:
    data_inicio, data_fim = periodo_ano(ano)

    return f"""<pesquisa>
  <identificacao
    perfil="{PERFIL}"
    sistema="{SISTEMA}"
    tipoarquivo="{TIPO_ARQUIVO}"
    tipopesquisa="{TIPO_PESQUISA}"
    nirepresentado="{cnpj}"
    tiponirepresentado="cnpj" />
  <campo nome="dataInicio" valor="{data_inicio}" />
  <campo nome="dataFim" valor="{data_fim}" />
</pesquisa>"""


def extrair_ids_arquivos(saida_xml: Optional[str]) -> List[str]:
    if not saida_xml:
        return []

    try:
        root = ET.fromstring(saida_xml.encode("utf-8"))
        return [
            arquivo.attrib.get("id")
            for arquivo in root.findall(".//arquivo")
            if arquivo.attrib.get("id")
        ]
    except Exception:
        logger.exception("[ReceitanetBX] Não foi possível extrair ids dos arquivos da saída XML")
        return []


def pesquisar_ecd(cnpj: str, ano: int) -> Dict:
    logger.info("[ReceitanetBX] PesquisarArquivos iniciado | cnpj=%s | ano=%s", cnpj, ano)
    xml_entrada = montar_xml_pesquisa(cnpj, ano)
    resposta = chamar_soap("PesquisarArquivos", xml_entrada)

    ids = extrair_ids_arquivos(resposta.get("saida_xml"))
    mensagem = resposta.get("mensagem") or ""

    if ids:
        status = "ENCONTRADO"
    elif "Nenhum arquivo foi encontrado" in mensagem:
        status = "NAO_ENCONTRADA"
    else:
        status = "ERRO"

    logger.info(
        "[ReceitanetBX] PesquisarArquivos concluído | cnpj=%s | ano=%s | status=%s | qtd_ids=%s | mensagem=%s",
        cnpj,
        ano,
        status,
        len(ids),
        mensagem,
    )

    return {
        "status": status,
        "http_status": resposta.get("http_status"),
        "retorno": resposta.get("retorno"),
        "mensagem": resposta.get("mensagem"),
        "qtd_arquivos": len(ids),
        "ids_arquivos": ids,
        "saida_xml": resposta.get("saida_xml"),
        "raw": resposta.get("raw"),
    }


def montar_xml_solicitacao(cnpj: str, ids_arquivos: List[str]) -> str:
    arquivos_xml = "\n".join(f'    <arquivo id="{arquivo_id}" />' for arquivo_id in ids_arquivos)

    return f"""<pedido>
  <identificacao
    perfil="{PERFIL}"
    sistema="{SISTEMA}"
    tipoarquivo="{TIPO_ARQUIVO}"
    tipopesquisa="{TIPO_PESQUISA}"
    nirepresentado="{cnpj}"
    tiponirepresentado="cnpj" />
  <arquivos>
{arquivos_xml}
  </arquivos>
</pedido>"""


def extrair_numero_pedido(saida_xml: Optional[str]) -> Optional[str]:
    if not saida_xml:
        return None

    try:
        root = ET.fromstring(saida_xml.encode("utf-8"))
        return root.attrib.get("id")
    except Exception:
        logger.exception("[ReceitanetBX] Não foi possível extrair número do pedido da saída XML")
        return None


def solicitar_arquivos(cnpj: str, ids_arquivos: List[str]) -> Dict:
    logger.info("[ReceitanetBX] SolicitarArquivos iniciado | cnpj=%s | qtd_ids=%s", cnpj, len(ids_arquivos))
    xml_entrada = montar_xml_solicitacao(cnpj, ids_arquivos)
    resposta = chamar_soap("SolicitarArquivos", xml_entrada)

    numero_pedido = extrair_numero_pedido(resposta.get("saida_xml"))

    logger.info(
        "[ReceitanetBX] SolicitarArquivos concluído | cnpj=%s | numero_pedido=%s | mensagem=%s",
        cnpj,
        numero_pedido,
        resposta.get("mensagem"),
    )

    return {
        "http_status": resposta.get("http_status"),
        "retorno": resposta.get("retorno"),
        "mensagem": resposta.get("mensagem"),
        "numero_pedido": numero_pedido,
        "saida_xml": resposta.get("saida_xml"),
        "raw": resposta.get("raw"),
    }
