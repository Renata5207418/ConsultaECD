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

function showToast(message) {
  alert(message);
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
  if (worker?.rodando && worker?.pausado) {
    badge.classList.add("badge-paused");
    badge.textContent = "Pausado";
    return;
  }
  if (worker?.rodando) {
    badge.classList.add("badge-running");
    badge.textContent = "Consultando";
    return;
  }
  badge.classList.add("badge-idle");
  badge.textContent = "Aguardando";
}

function atualizarResumo(resumo = {}) {
  const encontradas = (resumo.ENCONTRADO || 0) + (resumo.SOLICITADO || 0);
  const erros = (resumo.ERRO || 0) + (resumo.CNPJ_INVALIDO || 0);

  setText("statPendente", resumo.PENDENTE || 0);
  setText("statProcessando", resumo.PROCESSANDO || 0);
  setText("statEncontrado", encontradas);
  setText("statNaoEncontrada", resumo.NAO_ENCONTRADA || 0);
  setText("statErro", erros);
}

function atualizarLote(lote = {}) {
  loteAtualId = lote?.id || loteAtualId;

  setText("loteArquivo", lote.nome_original || lote.arquivo_original || lote.nome_arquivo || lote.filename || lote.arquivo || "-");
  setText("loteAno", lote.ano_calendario || lote.ano || "-");
  setText("loteStatus", lote.status || "-");
  setText("loteTotal", lote.total_importado || lote.total_linhas || lote.total || lote.total_registros || "-");
  setText("loteValidos", lote.total_validos || lote.validos || lote.total_validos_unicos || "-");
  setText("loteInvalidos", lote.total_invalidos ?? lote.invalidos ?? "-");

  const exportar = qs("#btnExportarExcel");
  if (exportar) {
    exportar.href = loteAtualId ? `/api/exportar?lote_id=${encodeURIComponent(loteAtualId)}` : "/api/exportar?lote_id=atual";
  }
}

function atualizarWorker(worker = {}) {
  workerRodando = Boolean(worker.rodando);

  const liveBox = qs("#liveBox");
  const liveDot = qs("#liveDot");
  if (liveBox && liveDot) {
    liveBox.classList.toggle("running", Boolean(worker.rodando && !worker.pausado && !worker.erro));
    liveBox.classList.toggle("paused", Boolean(worker.rodando && worker.pausado));
    liveBox.classList.toggle("error", Boolean(worker.erro));
    liveDot.classList.toggle("running", Boolean(worker.rodando && !worker.pausado && !worker.erro));
    liveDot.classList.toggle("paused", Boolean(worker.rodando && worker.pausado));
    liveDot.classList.toggle("error", Boolean(worker.erro));
  }

  let titulo = "Aguardando";
  if (worker.erro) titulo = "Atenção";
  else if (worker.rodando && worker.pausado) titulo = "Pausado";
  else if (worker.rodando) titulo = "Consultando em tempo real";
  else if (worker.fim) titulo = "Finalizado";

  setText("workerTitulo", titulo);
  setText("workerMensagem", worker.ultimo_mensagem || worker.mensagem || "Nenhuma consulta em execução.");
  setText("workerUltimoCnpj", formatarCnpj(worker.ultimo_cnpj));
  setText("workerInicio", worker.inicio || "-");
  setText("workerFim", worker.fim || "-");

  const btnPausar = qs("#btnPausar");
  const btnContinuar = qs("#btnContinuar");
  const btnParar = qs("#btnParar");

  if (btnPausar) btnPausar.disabled = !worker.rodando || worker.pausado;
  if (btnContinuar) btnContinuar.disabled = !worker.rodando || !worker.pausado;
  if (btnParar) btnParar.disabled = !worker.rodando;
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
    atualizarBadge({ rodando: false, pausado: false, erro: true });
    atualizarWorker({ rodando: false, pausado: false, erro: true, mensagem: err.message });
    return null;
  }
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
  if (loteAtualId) params.set("lote_id", loteAtualId);
  else params.set("lote_id", "atual");

  try {
    const data = await apiGet(`/api/consultas?${params.toString()}`);
    const consultas = data.consultas || data.items || [];

    if (!consultas.length) {
      tbody.innerHTML = `<tr><td colspan="11">Nenhuma consulta encontrada.</td></tr>`;
      return;
    }

    tbody.innerHTML = consultas.map(item => {
      const id = getMongoId(item);
      const status = item.status || "";
      const statusClass = `status-${status}`;
      const idsArquivos = normalizarListaIds(item.ids_arquivos || item.arquivos_ids || item.ids);
      const qtdArquivos = item.qtd_arquivos ?? item.quantidade_arquivos ?? item.qtd ?? "";
      const numeroPedido = item.numero_pedido || item.pedido || "";
      const mensagem = item.mensagem || item.mensagem_receitanetbx || item.mensagem_solicitacao || item.observacao || "";

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
          <td title="${escapeHtml(mensagem)}">${escapeHtml(mensagem)}</td>
        </tr>
      `;
    }).join("");
  } catch (err) {
    console.error("Erro ao carregar consultas:", err);
    tbody.innerHTML = `<tr><td colspan="11">Erro ao carregar consultas: ${escapeHtml(err.message)}</td></tr>`;
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
    } else {
      showToast(err.message);
    }
  } finally {
    if (botao) {
      botao.disabled = false;
      botao.textContent = "Importar e iniciar consultas";
    }
  }
}

async function reprocessarErros() {
  if (!confirm("Deseja voltar os registros com ERRO/CNPJ inválido do lote atual para PENDENTE e iniciar novamente?")) return;
  try {
    const data = await apiPost("/api/reprocessar-erros", { lote_id: loteAtualId });
    await atualizarStatus();
    await carregarConsultas();

    if ((data.modificados || 0) > 0) {
      await iniciarConsulta(data.lote_id || loteAtualId);
    } else {
      showToast("Nenhum erro encontrado no lote atual para reprocessar.");
    }
  } catch (err) {
    showToast(err.message);
  }
}

async function atualizarTudo() {
  await atualizarStatus();
  await carregarConsultas();
}

function bindEvents() {
  qsa(".nav-item").forEach(btn => btn.addEventListener("click", () => trocarSecao(btn.dataset.section)));
  qs("#btnAtualizarResultados")?.addEventListener("click", atualizarTudo);

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

  qs("#btnPausar")?.addEventListener("click", async () => { await apiPost("/api/pausar"); await atualizarStatus(); });
  qs("#btnContinuar")?.addEventListener("click", async () => { await apiPost("/api/continuar"); await atualizarStatus(); });
  qs("#btnParar")?.addEventListener("click", async () => { await apiPost("/api/parar"); await atualizarStatus(); });
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
  }, 1500);
}

boot();