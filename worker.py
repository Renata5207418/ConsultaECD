import logging
import threading
import time
from datetime import datetime
from typing import Dict, Optional

import database
from services.receitanetbx import pesquisar_ecd, solicitar_arquivos

logger = logging.getLogger(__name__)


class WorkerECD:
    def __init__(self):
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._pause_event = threading.Event()
        self._state = {
            "rodando": False,
            "pausado": False,
            "mensagem": "Aguardando.",
            "ultimo_cnpj": None,
            "ultimo_ano": None,
            "ultimo_status": None,
            "ultimo_mensagem": None,
            "lote_id": None,
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

            self._stop_event.clear()
            self._pause_event.clear()
            self._state.update({
                "rodando": True,
                "pausado": False,
                "mensagem": "Iniciando consultas.",
                "ultimo_cnpj": None,
                "ultimo_ano": None,
                "ultimo_status": None,
                "ultimo_mensagem": None,
                "lote_id": lote_id,
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

    def pausar(self) -> Dict:
        with self._lock:
            if self._state["rodando"]:
                self._pause_event.set()
                self._state["pausado"] = True
                self._state["mensagem"] = "Pausado pelo usuário."
                logger.info("[WorkerECD] Execução pausada pelo usuário")
        return self.status()

    def continuar(self) -> Dict:
        with self._lock:
            if self._state["rodando"]:
                self._pause_event.clear()
                self._state["pausado"] = False
                self._state["mensagem"] = "Continuando consultas."
                logger.info("[WorkerECD] Execução continuada pelo usuário")
        return self.status()

    def parar(self) -> Dict:
        with self._lock:
            if self._state["rodando"]:
                self._stop_event.set()
                self._pause_event.clear()
                self._state["pausado"] = False
                self._state["mensagem"] = "Parada solicitada pelo usuário."
                logger.info("[WorkerECD] Parada solicitada pelo usuário")
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

            while not self._stop_event.is_set():
                while self._pause_event.is_set() and not self._stop_event.is_set():
                    time.sleep(0.5)

                pendentes = database.buscar_pendentes(tamanho_lote, lote_id=lote_id)
                logger.info("[WorkerECD] Pendentes encontrados nesta rodada: %s | lote_id=%s", len(pendentes), lote_id)

                if not pendentes:
                    self._set_state(mensagem="Nenhuma consulta pendente. Finalizado.")
                    break

                for consulta in pendentes:
                    if self._stop_event.is_set():
                        final_status_lote = "PARADO"
                        break

                    while self._pause_event.is_set() and not self._stop_event.is_set():
                        time.sleep(0.5)

                    consulta_id = consulta["_id"]
                    cnpj = consulta.get("cnpj")
                    ano = int(consulta.get("ano_calendario"))

                    marcado = database.marcar_processando(consulta_id)
                    if not marcado:
                        continue

                    self._set_state(
                        mensagem=f"Consultando CNPJ {cnpj} - ano {ano}.",
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

                        resultado = pesquisar_ecd(cnpj, ano)

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
                                "[WorkerECD] ECD encontrada. Solicitando arquivos | cnpj=%s | qtd_ids=%s",
                                cnpj,
                                len(ids_arquivos),
                            )
                            solicitacao = solicitar_arquivos(cnpj, ids_arquivos)
                            dados_atualizacao.update({
                                "solicitado": "SIM" if solicitacao.get("numero_pedido") else "ERRO",
                                "numero_pedido": solicitacao.get("numero_pedido"),
                                "mensagem_solicitacao": solicitacao.get("mensagem"),
                                "saida_xml_solicitacao": solicitacao.get("saida_xml"),
                                "raw_solicitacao": solicitacao.get("raw"),
                            })

                            if solicitacao.get("numero_pedido"):
                                dados_atualizacao["status"] = "SOLICITADO"

                        database.atualizar_consulta(consulta_id, dados_atualizacao)

                        mensagem_final = resultado.get("mensagem") or dados_atualizacao["status"]
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

            if self._stop_event.is_set():
                final_status_lote = "PARADO"
                self._set_state(mensagem="Execução parada pelo usuário.")
                logger.info("[WorkerECD] Execução parada pelo usuário | lote_id=%s", lote_id)

        except Exception as e:
            final_status_lote = "ERRO"
            self._set_state(erro=str(e), mensagem="Erro geral no worker.")
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
                pausado=False,
                fim=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            )
            logger.info(
                "[WorkerECD] Execução finalizada | lote_id=%s | status_lote=%s | resumo=%s",
                lote_id,
                final_status_lote,
                resumo,
            )
