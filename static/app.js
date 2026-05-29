const sections = {
  "nova-consulta": {
    title: "Nova Consulta",
    subtitle: "Importe a planilha e o sistema já inicia a consulta pelo ReceitanetBX."
  },
  resultados: {
    title: "Resultados",
    subtitle: "Consulte, filtre e exporte os registros salvos no MongoDB."
  }
};

let loteAtualId = null;
let workerRodando = false;
let atualizandoConsultas = false;
let verificandoDownloads = false;
let ultimoResumo = {};
let ultimaMensagemFlash = "";

function qs(selector) {
  return document.querySelector(selector);
}

function qsa(selector) {
  return Array.from(document.querySelectorAll(selector));
}

function setText(id, value) {
  const el = qs(`#${id}`);
  if (!el) return;
  if (value === null || value === undefined || value === "") {
    el.textContent = "-";
    return;
  }
  el.textContent = value;
}

function escapeHtml(value) {
  if (value === null || value === undefined) return "";
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function formatarCnpj(cnpj) {
  if (!cnpj) return "";
  const digits = String(cnpj).replace(/\D/g, "");
  if (digits.length !== 14) return escapeHtml(cnpj);
  return digits.replace(/^(\d{2})(\d{3})(\d{3})(\d{4})(\d{2})$/, "$1.$2.$3/$4-$5");
}

function normalizarListaIds(ids) {
  if (!ids) return "";
  if (Array.isArray(ids)) return ids.join(" | ");
  return String(ids);
}

function getMongoId(item) {
  if (!item) return "";
  if (item.id) return item.id;
  if (item._id) {
    if (typeof item._id === "string") return item._id;
    if (item._id.$oid) return item._id.$oid;
  }
  return "";
}

function mostrarMensagem(message, tipo = "info", autoHide = true) {
  const el = qs("#flashMensagem");
  if (!el || !message) return;

  ultimaMensagemFlash = message;
  el.classList.remove("hidden", "flash-info", "flash-success", "flash-warning", "flash-error");
  el.classList.add(`flash-${tipo}`);
  el.innerHTML = escapeHtml(message);

  if (autoHide) {
    setTimeout(() => {
      if (ultimaMensagemFlash === message) {
        el.classList.add("hidden");
      }
    }, 7000);
  }
}

async function apiGet(url) {
  const resp = await fetch(url);
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.erro || data.message || `Erro HTTP ${resp.status}`);
  return data;
}

async function apiPost(url, body = {}) {
  const resp = await fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body)
  });
  const data = await resp.json().catch(() => ({}));
  if (!resp.ok) throw new Error(data.erro || data.message || `Erro HTTP ${resp.status}`);
  return data;
}

function trocarSecao(secao) {
  qsa(".section").forEach(el => el.classList.remove("active"));
  qsa(".nav-item").forEach(el => el.classList.remove("active"));

  qs(`#section-${secao}`)?.classList.add("active");
  qs(`.nav-item[data-section="${secao}"]`)?.classList.add("active");

  setText("pageTitle", sections[secao]?.title || "Consulta ECD");
  setText("pageSubtitle", sections[secao]?.subtitle || "");

  if (secao === "resultados") carregarConsultas();
}

function atualizarBadge(worker) {
  const badge = qs("#workerBadge");
  if (!badge) return;

  badge.classList.remove("badge-idle", "badge-running", "badge-paused", "badge-error");

  if (worker?.erro) {
    badge.classList.add("badge-error");
    badge.textContent = "Atenção";
    return;
  }

  if (worker?.rodando) {
    badge.classList.add("badge-running");
    badge.textContent = worker?.fase === "download" ? "Downloads" : "Consultando";
    return;
  }

  badge.classList.add("badge-idle");
  badge.textContent = "Aguardando";
}

function atualizarResumo(resumo = {}) {
  ultimoResumo = resumo || {};

  const solicitacoes =
    Number(resumo.SOLICITADO || 0) +
    Number(resumo.AGUARDANDO_DOWNLOAD || 0) +
    Number(resumo.BAIXADO || 0) +
    Number(resumo.ERRO_DOWNLOAD || 0);

  setText("statPendente", resumo.PENDENTE || 0);
  setText("statProcessando", resumo.PROCESSANDO || 0);
  setText("statEncontrado", resumo.ENCONTRADO || 0);
  setText("statSolicitacoes", solicitacoes);
  setText("statAguardandoDownload", Number(resumo.AGUARDANDO_DOWNLOAD || 0) + Number(resumo.SOLICITADO || 0));
  setText("statBaixado", resumo.BAIXADO || 0);
  setText("statNaoEncontrada", resumo.NAO_ENCONTRADA || 0);
  setText("statErro", (resumo.ERRO || 0) + (resumo.ERRO_DOWNLOAD || 0) + (resumo.CNPJ_INVALIDO || 0));

  atualizarResumoDownloads();
}

function atualizarResumoDownloads(lote = null) {
  const baixados = Number(ultimoResumo.BAIXADO || 0);
  const aguardando = Number(ultimoResumo.AGUARDANDO_DOWNLOAD || 0) + Number(ultimoResumo.SOLICITADO || 0);
  const solicitados = baixados + aguardando + Number(ultimoResumo.ERRO_DOWNLOAD || 0);

  setText("downloadSolicitados", solicitados);
  setText("downloadAguardando", aguardando);
  setText("downloadBaixados", baixados);
  setText("downloadZipStatus", baixados > 0 ? "Disponível" : "Indisponível");

  const ultima = lote?.ultima_verificacao_download || "-";
  setText("downloadUltimaVerificacao", ultima);

  const btnZip = qs("#btnBaixarZip");
  if (btnZip) {
    btnZip.disabled = baixados <= 0;
    btnZip.textContent = baixados > 0 ? `Baixar ZIP do lote (${baixados})` : "Baixar ZIP do lote";
  }
}

function atualizarLote(lote = {}) {
  loteAtualId = lote.id || lote._id || loteAtualId;
  setText("loteArquivo", lote.nome_original || lote.arquivo_original || lote.nome_arquivo || lote.filename || lote.arquivo || "-");
  setText("loteAno", lote.ano_calendario || lote.ano || "-");
  setText("loteStatus", lote.status || "-");
  setText("loteTotal", lote.total_importado || lote.total_linhas || lote.total || lote.total_registros || "-");
  setText("loteValidos", lote.total_validos || lote.validos || lote.total_validos_unicos || "-");
  setText("loteInvalidos", lote.total_invalidos || lote.invalidos || "-");
  atualizarResumoDownloads(lote);
}

function atualizarWorker(worker = {}) {
  workerRodando = Boolean(worker.rodando);

  const liveBox = qs("#liveBox");
  const liveDot = qs("#liveDot");
  if (liveBox) liveBox.classList.remove("running", "paused", "error");
  if (liveDot) liveDot.classList.remove("running", "paused", "error");

  let titulo = "Aguardando";
  if (worker.erro) {
    titulo = "Atenção";
    liveBox?.classList.add("error");
    liveDot?.classList.add("error");
  } else if (worker.rodando) {
    titulo = worker.fase === "download" ? "Verificando downloads" : "Consultando";
    liveBox?.classList.add("running");
    liveDot?.classList.add("running");
  }

  setText("workerTitulo", titulo);
  setText("workerMensagem", worker.mensagem || "Nenhuma consulta em execução.");
  setText("workerUltimoCnpj", worker.ultimo_cnpj ? formatarCnpj(worker.ultimo_cnpj) : "-");
  setText("workerInicio", worker.inicio || "-");
  setText("workerFim", worker.fim || "-");
}

async function atualizarStatus() {
  try {
    const data = await apiGet("/api/status");
    atualizarResumo(data.resumo || {});
    atualizarBadge(data.worker || {});
    atualizarWorker(data.worker || {});
    atualizarLote(data.lote_atual || data.lote || {});
    return data;
  } catch (err) {
    console.error("Erro ao atualizar status:", err);
    atualizarBadge({ rodando: false, erro: true });
    atualizarWorker({ rodando: false, erro: true, mensagem: err.message });
    return null;
  }
}

function montarLinkArquivo(item) {
  const id = getMongoId(item);
  if (item.status === "BAIXADO" && item.caminho_arquivo_baixado && id) {
    return `<a class="link-download" href="/api/downloads/arquivo/${encodeURIComponent(id)}">Baixar</a>`;
  }

  if (item.status === "AGUARDANDO_DOWNLOAD" || item.status === "SOLICITADO") {
    return `<span class="muted-mini">Aguardando</span>`;
  }

  if (item.status === "ERRO_DOWNLOAD") {
    return `<span class="muted-mini danger-text">Erro</span>`;
  }

  return "-";
}

async function carregarConsultas() {
  if (atualizandoConsultas) return;

  const tbody = qs("#tbodyConsultas");
  if (!tbody) return;

  atualizandoConsultas = true;

  const status = qs("#filtroStatus")?.value || "";
  const params = new URLSearchParams();
  params.set("limit", "500");
  if (status) params.set("status", status);
  params.set("lote_id", loteAtualId || "atual");

  try {
    const data = await apiGet(`/api/consultas?${params.toString()}`);
    const consultas = data.consultas || data.items || [];

    if (!consultas.length) {
      tbody.innerHTML = `<tr><td colspan="12">Nenhuma consulta encontrada.</td></tr>`;
      return;
    }

    tbody.innerHTML = consultas.map(item => {
      const id = getMongoId(item);
      const status = item.status || "";
      const statusClass = `status-${status}`;
      const idsArquivos = normalizarListaIds(item.ids_arquivos || item.arquivos_ids || item.ids);
      const qtdArquivos = item.qtd_arquivos ?? item.quantidade_arquivos ?? item.qtd ?? "";
      const numeroPedido = item.numero_pedido || item.pedido || "";
      const mensagem = item.mensagem_download || item.mensagem || item.mensagem_receitanetbx || item.mensagem_solicitacao || item.observacao || "";

      return `
        <tr>
          <td title="${escapeHtml(id)}">${escapeHtml(id).slice(-8)}</td>
          <td>${escapeHtml(item.codigo || item.codigo_empresa || "")}</td>
          <td title="${escapeHtml(item.razao_social || "")}">${escapeHtml(item.razao_social || "")}</td>
          <td>${formatarCnpj(item.cnpj)}</td>
          <td>${escapeHtml(item.ano_calendario || item.ano || "")}</td>
          <td><span class="status ${statusClass}">${escapeHtml(status)}</span></td>
          <td>${escapeHtml(qtdArquivos)}</td>
          <td title="${escapeHtml(idsArquivos)}">${escapeHtml(idsArquivos)}</td>
          <td title="${escapeHtml(numeroPedido)}">${escapeHtml(numeroPedido)}</td>
          <td>${escapeHtml(item.tentativas ?? "")}</td>
          <td>${montarLinkArquivo(item)}</td>
          <td title="${escapeHtml(mensagem)}">${escapeHtml(mensagem)}</td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error("Erro ao carregar consultas:", err);
    tbody.innerHTML = `<tr><td colspan="12">Erro ao carregar consultas: ${escapeHtml(err.message)}</td></tr>`;
  } finally {
    atualizandoConsultas = false;
  }
}

async function importarPlanilha() {
  const form = qs("#formImportar");
  const resultBox = qs("#importResultado");
  const arquivo = qs("#arquivo");

  if (!form || !resultBox) return null;

  if (!arquivo || !arquivo.files || arquivo.files.length === 0) {
    resultBox.innerHTML = `<strong>Erro:</strong> selecione uma planilha .xlsx antes de iniciar.`;
    resultBox.classList.remove("hidden");
    return null;
  }

  const formData = new FormData(form);
  formData.set("solicitar", qs("#solicitarArquivos")?.checked ? "true" : "false");
  formData.set("iniciar", "true");

  resultBox.classList.remove("hidden");
  resultBox.innerHTML = "Importando planilha, criando fila no MongoDB e iniciando consultas...";

  const resp = await fetch("/api/importar", { method: "POST", body: formData });
  const data = await resp.json().catch(() => ({}));

  if (!resp.ok || data.ok === false) {
    throw new Error(data.erro || data.message || "Falha ao importar planilha.");
  }

  const r = data.resultado || data;
  loteAtualId = r.lote_id || loteAtualId;

  resultBox.innerHTML = `
    <strong>Importação concluída.</strong><br>
    Lote: ${escapeHtml(loteAtualId || "-")}<br>
    Inseridos/Válidos: ${escapeHtml(r.total_validos_unicos ?? r.validos ?? r.inseridos ?? "-")}<br>
    Inválidos: ${escapeHtml(r.invalidos ?? r.total_invalidos ?? "-")}<br>
    ${escapeHtml(data.worker_mensagem || "Consultas iniciadas.")}
  `;

  mostrarMensagem("Consulta iniciada. Acompanhe o andamento nos cards e na tela de resultados.", "success");
  await atualizarStatus();
  await carregarConsultas();

  return r;
}

async function iniciarConsulta(loteId = null) {
  const solicitar = Boolean(qs("#solicitarArquivos")?.checked);
  await apiPost("/api/iniciar", {
    tamanho_lote: 100,
    pausa: 1,
    solicitar,
    lote_id: loteId || loteAtualId
  });
  await atualizarStatus();
  await carregarConsultas();
}

async function importarEIniciarConsultas() {
  const botao = qs("#btnImportarIniciar");
  const resultBox = qs("#importResultado");

  try {
    if (botao) {
      botao.disabled = true;
      botao.textContent = "Importando e iniciando...";
    }

    await importarPlanilha();
  } catch (err) {
    if (resultBox) {
      resultBox.innerHTML = `<strong>Erro:</strong> ${escapeHtml(err.message)}`;
      resultBox.classList.remove("hidden");
    }
    mostrarMensagem(err.message, "error", false);
  } finally {
    if (botao) {
      botao.disabled = false;
      botao.textContent = "Importar e iniciar consultas";
    }
  }
}

async function verificarDownloadsAutomatico() {
  const aguardando = Number(ultimoResumo.AGUARDANDO_DOWNLOAD || 0) + Number(ultimoResumo.SOLICITADO || 0);
  if (verificandoDownloads || workerRodando || aguardando <= 0) return;

  verificandoDownloads = true;
  try {
    const data = await apiPost("/api/downloads/verificar", { lote_id: loteAtualId || "atual" });
    await atualizarStatus();
    await carregarConsultas();

    if ((data.encontrados || 0) > 0) {
      mostrarMensagem(`${data.encontrados} arquivo(s) localizado(s). O ZIP do lote já pode ser baixado.`, "success");
    }
  } catch (err) {
    console.error("Erro na verificação automática de downloads:", err);
  } finally {
    verificandoDownloads = false;
  }
}

function baixarZipLote() {
  const qtdBaixados = Number(ultimoResumo.BAIXADO || 0);
  if (qtdBaixados <= 0) {
    mostrarMensagem("Nenhum arquivo baixado neste lote ainda. O sistema está verificando automaticamente.", "warning");
    return;
  }

  const lote = encodeURIComponent(loteAtualId || "atual");
  window.location.href = `/api/downloads/zip?lote_id=${lote}`;
}

async function reprocessarErros() {
  if (!confirm("Deseja voltar os registros com ERRO/CNPJ inválido do lote atual para PENDENTE e iniciar novamente?")) return;
  try {
    const data = await apiPost("/api/reprocessar-erros", { lote_id: loteAtualId });
    await atualizarStatus();
    await carregarConsultas();

    if ((data.modificados || 0) > 0) {
      await iniciarConsulta(data.lote_id || loteAtualId);
      mostrarMensagem("Erros enviados para reprocessamento.", "success");
    } else {
      mostrarMensagem("Nenhum erro encontrado no lote atual para reprocessar.", "info");
    }
  } catch (err) {
    mostrarMensagem(err.message, "error", false);
  }
}

async function atualizarTudo() {
  await atualizarStatus();
  await carregarConsultas();
  await verificarDownloadsAutomatico();
}

function bindEvents() {
  qsa(".nav-item").forEach(btn => btn.addEventListener("click", () => trocarSecao(btn.dataset.section)));
  qs("#btnAtualizarResultados")?.addEventListener("click", atualizarTudo);
  qs("#btnBaixarZip")?.addEventListener("click", baixarZipLote);

  qs("#btnToggleSidebar")?.addEventListener("click", () => {
    qs("#sidebar")?.classList.toggle("collapsed");
  });

  qs("#arquivo")?.addEventListener("change", function() {
    const msg = qs("#fileMsg");
    const dropArea = qs("#fileDropArea");
    if (this.files && this.files.length > 0) {
      msg.textContent = this.files[0].name;
      dropArea.classList.add("has-file");
    } else {
      msg.textContent = "Clique ou arraste o arquivo .xlsx aqui";
      dropArea.classList.remove("has-file");
    }
  });

  qs("#formImportar")?.addEventListener("submit", event => {
    event.preventDefault();
    importarEIniciarConsultas();
  });

  qs("#btnImportarIniciar")?.addEventListener("click", importarEIniciarConsultas);
  qs("#btnReprocessarErros")?.addEventListener("click", reprocessarErros);
  qs("#filtroStatus")?.addEventListener("change", carregarConsultas);
}

async function boot() {
  bindEvents();
  await atualizarStatus();
  await carregarConsultas();

  setInterval(async () => {
    await atualizarStatus();

    const resultadosAtivo = qs("#section-resultados")?.classList.contains("active");
    if (workerRodando || resultadosAtivo) {
      await carregarConsultas();
    }
  }, 2000);

  setInterval(async () => {
    await verificarDownloadsAutomatico();
  }, 30000);
}

boot();
