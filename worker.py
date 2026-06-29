import logging
import threading
import time
from datetime import datetime
from typing import Dict, Optional

import database
from config import (
    DOWNLOAD_AUTO_CHECK_ENABLED,
    DOWNLOAD_CHECK_INTERVAL_SECONDS,
    DOWNLOAD_CHECK_MAX_MINUTES,
)
from services.downloads_lote import verificar_downloads_lote
from services.receitanetbx import pesquisar_declaracao, solicitar_arquivos

logger = logging.getLogger(__name__)


class WorkerECD:
    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._state = {
            "rodando": False,
            "mensagem": "Aguardando.",
            "ultimo_cnpj": None,
            "ultimo_ano": None,
            "ultimo_status": None,
            "ultimo_mensagem": None,
            "lote_id": None,
            "fase": "aguardando",
            "inicio": None,
            "fim": None,
            "erro": None,
        }

    def status(self) -> Dict:
        with self._lock:
            return dict(self._state)

    def iniciar(
        self,
        tamanho_lote: int = 100,
        solicitar: bool = False,
        pausa: float = 1.0,
        lote_id: Optional[str] = None,
    ) -> Dict:
        with self._lock:
            if self._state["rodando"]:
                raise RuntimeError("As consultas já estão em execução.")

            self._state.update({
                "rodando": True,
                "mensagem": "Iniciando consultas.",
                "ultimo_cnpj": None,
                "ultimo_ano": None,
                "ultimo_status": None,
                "ultimo_mensagem": None,
                "lote_id": lote_id,
                "fase": "consulta",
                "inicio": datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
                "fim": None,
                "erro": None,
            })

            self._thread = threading.Thread(
                target=self._executar,
                kwargs={
                    "tamanho_lote": tamanho_lote,
                    "solicitar": solicitar,
                    "pausa": pausa,
                    "lote_id": lote_id,
                },
                daemon=True,
            )
            self._thread.start()

        return self.status()

    def _set_state(self, **kwargs) -> None:
        with self._lock:
            self._state.update(kwargs)

    def _atualizar_status_lote(self, lote_id: Optional[str], status: str, **extras) -> None:
        if not lote_id:
            return
        try:
            dados = {"status": status, **extras}
            database.atualizar_lote(lote_id, dados)
        except Exception:
            logger.exception("[WorkerECD] Falha ao atualizar status do lote %s para %s", lote_id, status)

    def _monitorar_downloads(self, lote_id: Optional[str]) -> Dict:
        if not lote_id:
            return {}

        if not DOWNLOAD_AUTO_CHECK_ENABLED:
            logger.info("[WorkerECD] Verificação automática de downloads desativada | lote_id=%s", lote_id)
            return database.resumo_status(lote_id=lote_id)

        intervalo = max(int(DOWNLOAD_CHECK_INTERVAL_SECONDS or 30), 5)
        max_segundos = max(int(DOWNLOAD_CHECK_MAX_MINUTES or 20), 1) * 60
        prazo_final = time.monotonic() + max_segundos
        tentativa = 0
        ultimo_resultado = {}

        while time.monotonic() <= prazo_final:
            resumo_atual = database.resumo_status(lote_id=lote_id)
            aguardando_total = int(resumo_atual.get("AGUARDANDO_DOWNLOAD", 0)) + int(resumo_atual.get("SOLICITADO", 0))

            if aguardando_total <= 0:
                self._set_state(
                    fase="finalizado",
                    mensagem="Todos os downloads localizados ou não há arquivos aguardando download.",
                    ultimo_status="BAIXADO" if int(resumo_atual.get("BAIXADO", 0)) > 0 else "FINALIZADO",
                )
                return resumo_atual

            tentativa += 1
            self._set_state(
                fase="download",
                mensagem=f"Aguardando download do ReceitanetBX. Verificação automática {tentativa}. Aguardando: {aguardando_total}.",
                ultimo_status="AGUARDANDO_DOWNLOAD",
                ultimo_mensagem="O sistema está procurando os arquivos baixados nos logs/pasta do ReceitanetBX.",
            )
            self._atualizar_status_lote(lote_id, "AGUARDANDO_DOWNLOAD")

            logger.info(
                "[WorkerECD] Verificação automática de downloads | lote_id=%s | tentativa=%s | aguardando=%s",
                lote_id,
                tentativa,
                aguardando_total,
            )

            ultimo_resultado = verificar_downloads_lote(lote_id=lote_id)
            resumo = ultimo_resultado.get("resumo") or database.resumo_status(lote_id=lote_id)
            aguardando_apos = int(resumo.get("AGUARDANDO_DOWNLOAD", 0)) + int(resumo.get("SOLICITADO", 0))
            baixados = int(resumo.get("BAIXADO", 0))

            self._set_state(
                mensagem=f"Downloads: {baixados} baixado(s), {aguardando_apos} aguardando.",
                ultimo_status="AGUARDANDO_DOWNLOAD" if aguardando_apos else "BAIXADO",
                ultimo_mensagem=ultimo_resultado.get("mensagem") or None,
            )

            if aguardando_apos <= 0:
                return resumo

            time.sleep(intervalo)

        logger.info("[WorkerECD] Prazo de verificação automática encerrado | lote_id=%s", lote_id)
        return ultimo_resultado.get("resumo") or database.resumo_status(lote_id=lote_id)

    def _executar(self, tamanho_lote: int, solicitar: bool, pausa: float, lote_id: Optional[str]) -> None:
        final_status_lote = "FINALIZADO"

        try:
            logger.info(
                "[WorkerECD] Iniciando execução | lote_id=%s | tamanho_lote=%s | solicitar=%s | pausa=%s",
                lote_id,
                tamanho_lote,
                solicitar,
                pausa,
            )
            self._atualizar_status_lote(lote_id, "CONSULTANDO", started_at=datetime.now(), finished_at=None)

            while True:
                pendentes = database.buscar_pendentes(tamanho_lote, lote_id=lote_id)
                logger.info("[WorkerECD] Pendentes encontrados nesta rodada: %s | lote_id=%s", len(pendentes), lote_id)

                if not pendentes:
                    self._set_state(mensagem="Nenhuma consulta pendente. Verificando downloads.", fase="download")
                    break

                for consulta in pendentes:
                    consulta_id = consulta["_id"]
                    cnpj = consulta.get("cnpj")
                    ano = int(consulta.get("ano_calendario"))

                    # 1. ADICIONE ESTA LINHA: Recupera se é ECD ou ECF
                    tipo_declaracao = consulta.get("tipo_declaracao", "ECD")

                    marcado = database.marcar_processando(consulta_id)
                    if not marcado:
                        continue

                    self._set_state(
                        fase="consulta",
                        # 2. ALTERE AQUI: Inclua a variável {tipo_declaracao} na mensagem
                        mensagem=f"Consultando {tipo_declaracao} - CNPJ {cnpj} - ano {ano}.",
                        ultimo_cnpj=cnpj,
                        ultimo_ano=ano,
                        ultimo_status="PROCESSANDO",
                        ultimo_mensagem=None,
                    )
                    logger.info(
                        "[WorkerECD] Consultando ReceitanetBX | lote_id=%s | consulta_id=%s | cnpj=%s | ano=%s",
                        lote_id,
                        consulta_id,
                        cnpj,
                        ano,
                    )

                    try:
                        if not cnpj or len(cnpj) != 14:
                            mensagem = f"CNPJ inválido: {consulta.get('cnpj_original') or cnpj}"
                            database.atualizar_consulta(consulta_id, {
                                "status": "CNPJ_INVALIDO",
                                "mensagem": "CNPJ inválido.",
                                "observacao": mensagem,
                                "data_consulta": datetime.now(),
                            })
                            self._set_state(
                                mensagem=mensagem,
                                ultimo_status="CNPJ_INVALIDO",
                                ultimo_mensagem=mensagem,
                            )
                            logger.warning("[WorkerECD] %s", mensagem)
                            continue

                        resultado = pesquisar_declaracao(cnpj, ano, tipo_declaracao)

                        dados_atualizacao = {
                            "status": resultado["status"],
                            "http_status": resultado.get("http_status"),
                            "retorno": resultado.get("retorno"),
                            "mensagem": resultado.get("mensagem"),
                            "qtd_arquivos": resultado.get("qtd_arquivos", 0),
                            "ids_arquivos": resultado.get("ids_arquivos", []),
                            "saida_xml": resultado.get("saida_xml"),
                            "raw": resultado.get("raw"),
                            "data_consulta": datetime.now(),
                        }

                        ids_arquivos = resultado.get("ids_arquivos") or []
                        if solicitar and ids_arquivos:
                            logger.info(
                                "[WorkerECD] %s encontrada. Solicitando arquivos | cnpj=%s | qtd_ids=%s",
                                tipo_declaracao,
                                cnpj,
                                len(ids_arquivos),
                            )
                            solicitacao = solicitar_arquivos(cnpj, ids_arquivos, tipo_declaracao)
                            numero_pedido = solicitacao.get("numero_pedido")

                            dados_atualizacao.update({
                                "solicitado": "SIM" if numero_pedido else "ERRO",
                                "numero_pedido": numero_pedido,
                                "mensagem_solicitacao": solicitacao.get("mensagem"),
                                "saida_xml_solicitacao": solicitacao.get("saida_xml"),
                                "raw_solicitacao": solicitacao.get("raw"),
                            })

                            if numero_pedido:
                                dados_atualizacao.update({
                                    "status": "AGUARDANDO_DOWNLOAD",
                                    "download_localizado": False,
                                    "mensagem_download": "Pedido registrado. Aguardando baixar o arquivo.",
                                    "ultima_verificacao_download": None,
                                })
                            else:
                                dados_atualizacao.update({
                                    "status": "ERRO_DOWNLOAD",
                                    "download_localizado": False,
                                    "mensagem_download": solicitacao.get("mensagem") or "Não foi possível registrar o pedido de download.",
                                })

                        database.atualizar_consulta(consulta_id, dados_atualizacao)

                        mensagem_final = (
                            dados_atualizacao.get("mensagem_download")
                            or resultado.get("mensagem")
                            or dados_atualizacao["status"]
                        )
                        self._set_state(
                            mensagem=f"{dados_atualizacao['status']}: {cnpj}",
                            ultimo_cnpj=cnpj,
                            ultimo_ano=ano,
                            ultimo_status=dados_atualizacao["status"],
                            ultimo_mensagem=mensagem_final,
                        )
                        logger.info(
                            "[WorkerECD] Consulta finalizada | cnpj=%s | ano=%s | status=%s | http=%s | retorno=%s | qtd=%s | mensagem=%s",
                            cnpj,
                            ano,
                            dados_atualizacao["status"],
                            resultado.get("http_status"),
                            resultado.get("retorno"),
                            resultado.get("qtd_arquivos", 0),
                            mensagem_final,
                        )

                    except Exception as e:
                        database.atualizar_consulta(consulta_id, {
                            "status": "ERRO",
                            "mensagem": f"Erro inesperado no worker: {e}",
                            "observacao": str(e),
                            "data_consulta": datetime.now(),
                        })
                        self._set_state(
                            mensagem=f"Erro ao consultar {cnpj}.",
                            ultimo_status="ERRO",
                            ultimo_mensagem=str(e),
                            erro=str(e),
                        )
                        logger.exception("[WorkerECD] Erro inesperado ao consultar cnpj=%s", cnpj)

                    time.sleep(max(float(pausa or 0), 0))

            # Depois de pesquisar/solicitar, o próprio sistema tenta localizar os arquivos.
            resumo_final = self._monitorar_downloads(lote_id) if solicitar else database.resumo_status(lote_id=lote_id)
            aguardando = int(resumo_final.get("AGUARDANDO_DOWNLOAD", 0)) + int(resumo_final.get("SOLICITADO", 0))
            erros_download = int(resumo_final.get("ERRO_DOWNLOAD", 0))

            if aguardando > 0:
                final_status_lote = "AGUARDANDO_DOWNLOAD"
                self._set_state(
                    fase="download",
                    mensagem=f"Consulta finalizada. {aguardando} arquivo(s) ainda aguardando download do ReceitanetBX.",
                    ultimo_status="AGUARDANDO_DOWNLOAD",
                )
            elif erros_download > 0:
                final_status_lote = "FINALIZADO_COM_ERRO_DOWNLOAD"
            else:
                final_status_lote = "FINALIZADO"

        except Exception as e:
            final_status_lote = "ERRO"
            self._set_state(erro=str(e), mensagem="Erro geral no worker.", fase="erro")
            logger.exception("[WorkerECD] Erro geral no worker | lote_id=%s", lote_id)

        finally:
            resumo = database.resumo_status(lote_id=lote_id) if lote_id else {}
            self._atualizar_status_lote(
                lote_id,
                final_status_lote,
                finished_at=datetime.now(),
                resumo_status=resumo,
            )
            self._set_state(
                rodando=False,
                fim=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            )
            logger.info(
                "[WorkerECD] Execução finalizada | lote_id=%s | status_lote=%s | resumo=%s",
                lote_id,
                final_status_lote,
                resumo,
            )
