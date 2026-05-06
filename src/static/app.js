let currentJobId = null;
let pollTimer = null;
let autoScrollLogs = true;
const renderedDraftKeys = new Set();
const AVAILABLE_EXTENSIONS = [
    ".py", ".js", ".ts", ".tsx", ".java", ".kt", ".cs", ".go", ".cpp",
    ".c", ".rb", ".php", ".html", ".css", ".scss", ".sh", ".rs", ".swift",
];
let selectedExtensions = new Set();
const APP_CONFIG = window.__APP_CONFIG__ || {};
const API_BASE = APP_CONFIG.apiBase || "/api";
const DEFAULT_MODELS_BY_PROVIDER = {
    ollama: "qwen2.5-coder:1.5b",
    gemini: "gemini-1.5-flash",
};

async function apiRequest(path, options = {}) {
    const res = await fetch(`${API_BASE}${path}`, options);
    let data = {};
    try {
        data = await res.json();
    } catch {
        data = {};
    }
    if (!res.ok) {
        throw new Error(data.error || "Falha na requisição da API");
    }
    return data;
}

const ApiClient = {
    start: (body) => apiRequest("/start", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
    }),
    stop: (jobId) => apiRequest(`/stop/${jobId}`, { method: "POST" }),
    status: (jobId) => apiRequest(`/status/${jobId}`),
    save: (jobId, drafts) => apiRequest(`/save/${jobId}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ drafts }),
    }),
};

function setButtonLoading(buttonId, loading, loadingText) {
    const btn = document.getElementById(buttonId);
    if (!btn) return;
    if (!btn.dataset.originalLabel) {
        btn.dataset.originalLabel = btn.textContent;
    }
    btn.disabled = loading;
    btn.textContent = loading ? loadingText : btn.dataset.originalLabel;
}

function setStopBtnState(enabled) {
    const btn = document.getElementById("stopBtn");
    if (!btn) return;
    btn.disabled = !enabled;
    btn.textContent = "Parar Execução";
    btn.className = enabled ? "stop-btn-on" : "stop-btn-off";
}

function showFormMessage(text, type = "error") {
    const box = document.getElementById("formMessage");
    if (!box) return;
    if (!text) {
        box.className = "inline-msg";
        box.style.display = "none";
        box.textContent = "";
        return;
    }
    box.className = `inline-msg ${type}`;
    box.style.display = "block";
    box.textContent = text;
}

function esc(str) {
    return (str || "").replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function draftKey(draft) {
    return `${draft.repository || ""}::${draft.student || ""}`;
}

function findDraftCardByKey(key) {
    const cards = document.querySelectorAll(".review-item[data-draft-key]");
    for (const card of cards) {
        if (card.dataset.draftKey === key) {
            return card;
        }
    }
    return null;
}

function clearRenderedDrafts() {
    renderedDraftKeys.clear();
    const container = document.getElementById("drafts");
    if (container) {
        container.innerHTML = "";
    }
}

function setSaveButtonEnabled(enabled) {
    const btn = document.getElementById("saveBtn");
    if (!btn) return;
    btn.disabled = !enabled;
    btn.title = enabled
        ? ""
        : "Aguarde o fim da análise para liberar a publicação das issues.";
}

function setPublishProgress({ visible, percent = 0, text = "", indeterminate = false }) {
    const wrapper = document.getElementById("publishProgress");
    const fill = document.getElementById("publishProgressFill");
    const label = document.getElementById("publishProgressLabel");
    const value = document.getElementById("publishProgressValue");
    if (!wrapper || !fill || !label || !value) return;

    if (!visible) {
        wrapper.style.display = "none";
        fill.classList.remove("indeterminate");
        fill.style.width = "0%";
        label.textContent = "Preparando publicação...";
        value.textContent = "0%";
        return;
    }

    wrapper.style.display = "block";
    if (indeterminate) {
        fill.classList.add("indeterminate");
    } else {
        fill.classList.remove("indeterminate");
    }

    const clamped = Math.max(0, Math.min(100, Number(percent) || 0));
    fill.style.width = `${clamped}%`;
    label.textContent = text || "Publicando...";
    value.textContent = `${Math.round(clamped)}%`;
}

function getSelectedExtensions() {
    return Array.from(selectedExtensions);
}

function updateExtensionsSummary() {
    const summary = document.getElementById("extensionsSummary");
    if (!summary) return;
    const selected = getSelectedExtensions();
    summary.textContent = selected.length
        ? `${selected.length} selecionada(s): ${selected.join(" ")}`
        : "Selecionar extensões";
}

function renderExtensionsOptions() {
    const container = document.getElementById("extensionsList");
    if (!container) return;
    container.innerHTML = "";

    AVAILABLE_EXTENSIONS.forEach((extension) => {
        const label = document.createElement("label");
        label.className = "flex items-center gap-2 px-2 py-1 rounded hover:bg-slate-50 text-sm text-slate-700 cursor-pointer";

        const input = document.createElement("input");
        input.type = "checkbox";
        input.value = extension;
        input.className = "accent-rose-600";
        input.checked = selectedExtensions.has(extension);
        input.addEventListener("change", () => {
            if (input.checked) {
                selectedExtensions.add(extension);
            } else {
                selectedExtensions.delete(extension);
            }
            updateExtensionsSummary();
        });

        const span = document.createElement("span");
        span.textContent = extension;

        label.appendChild(input);
        label.appendChild(span);
        container.appendChild(label);
    });
}

function setupExtensionsDropdown() {
    const btn = document.getElementById("extensionsDropdownBtn");
    const menu = document.getElementById("extensionsDropdownMenu");
    if (!btn || !menu) return;

    renderExtensionsOptions();
    updateExtensionsSummary();

    btn.addEventListener("click", (event) => {
        event.stopPropagation();
        menu.classList.toggle("hidden");
    });

    menu.addEventListener("click", (event) => {
        event.stopPropagation();
    });

    document.addEventListener("click", () => {
        menu.classList.add("hidden");
    });
}

async function startJob() {
    const assignment = document.getElementById("assignment").value.trim();
    if (!assignment) {
        showFormMessage("Informe a URL ou ID da assignment para iniciar a prévia.", "error");
        return;
    }

    const extensions = getSelectedExtensions();
    if (!extensions.length) {
        showFormMessage("Selecione ao menos uma extensão para iniciar a prévia.", "error");
        return;
    }

    showFormMessage("");

    const provider = document.getElementById("provider").value;
    const body = {
        assignment,
        instruction: document.getElementById("instruction").value.trim(),
        provider,
        model: document.getElementById("model").value.trim(),
        extensions,
        analysis_level: document.getElementById("analysisLevel").value,
    };

    setButtonLoading("startBtn", true, "Iniciando...");

    let data;
    try {
        data = await ApiClient.start(body);
    } catch (err) {
        showFormMessage(err.message || "Erro ao iniciar job", "error");
        setButtonLoading("startBtn", false, "");
        return;
    }

    currentJobId = data.job_id;
    const logs = document.getElementById("logs");
    logs.textContent = "";
    clearRenderedDrafts();
    setSaveButtonEnabled(false);
    setPublishProgress({ visible: false });
    document.getElementById("publishResult").style.display = "none";
    setStopBtnState(true);
    document.getElementById("reviewCard").style.display = "none";
    if (pollTimer) clearInterval(pollTimer);
    pollTimer = setInterval(fetchStatus, 1500);
    await fetchStatus();
    setButtonLoading("startBtn", false, "");
}

function setupProviderSelector() {
    const providerEl = document.getElementById("provider");
    const modelEl = document.getElementById("model");
    if (!providerEl || !modelEl) return;

    providerEl.addEventListener("change", () => {
        const selected = providerEl.value;
        const defaultModel = DEFAULT_MODELS_BY_PROVIDER[selected] || "";
        const currentValue = (modelEl.value || "").trim();
        const knownDefault = Object.values(DEFAULT_MODELS_BY_PROVIDER).includes(currentValue);
        if (!currentValue || knownDefault) {
            modelEl.value = defaultModel;
        }
    });
}

async function stopJob() {
    if (!currentJobId) return;
    const btn = document.getElementById("stopBtn");
    if (btn) { btn.disabled = true; btn.textContent = "Parando..."; }
    try {
        await ApiClient.stop(currentJobId);
    } catch (err) {
        alert(err.message || "Erro ao parar job");
        setStopBtnState(true);
        return;
    }
    await fetchStatus();
}

async function fetchStatus() {
    if (!currentJobId) return;
    let data;
    try {
        data = await ApiClient.status(currentJobId);
    } catch (err) {
        document.getElementById("status").innerText = err.message || "Erro ao consultar status";
        return;
    }

    const logsEl = document.getElementById("logs");
    logsEl.textContent = (data.logs || []).join("\n");
    if (autoScrollLogs) {
        logsEl.scrollTop = logsEl.scrollHeight;
    }
    const statusEl = document.getElementById("status");
    statusEl.className = `status-chip ${data.status || ""}`;
    statusEl.innerText = `Status: ${data.status}`;
    document.getElementById("statStatus").innerText = data.status || "-";
    document.getElementById("statDrafts").innerText = String((data.drafts || []).length);
    document.getElementById("statJob").innerText = currentJobId ? currentJobId.slice(0, 8) : "-";

    const running = data.status === "running" || data.status === "stopping";
    setStopBtnState(running);

    const drafts = data.drafts || [];
    if (drafts.length > 0) {
        document.getElementById("reviewCard").style.display = "block";
        renderDrafts(drafts);
    }

    setSaveButtonEnabled(data.status === "ready_for_review" && drafts.length > 0);

    if (data.status === "ready_for_review") {
        document.getElementById("reviewCard").style.display = "block";
        clearInterval(pollTimer);
        pollTimer = null;
    }

    if (data.status === "failed" || data.status === "canceled") {
        clearInterval(pollTimer);
        pollTimer = null;
    }
}

function renderDrafts(drafts) {
    const container = document.getElementById("drafts");
    drafts.forEach((d) => {
        const key = draftKey(d);
        if (renderedDraftKeys.has(key)) {
            return;
        }

        renderedDraftKeys.add(key);
        const div = document.createElement("div");
        div.className = "review-item";
        div.dataset.draftKey = key;
        div.innerHTML = `
      <div class="review-head">
        <strong>${esc(d.student)}</strong>
        <span>Nota sugerida: <strong>${Number(d.grade || 0).toFixed(1)} / 10</strong></span>
      </div>
      <div class="review-repo">${esc(d.repository)}</div>
      <div style="margin-top:6px;"><strong>Comentário:</strong> ${esc(d.grade_comment || "")}</div>
      <label>Título da issue</label>
            <input class="draft-title" value="${esc(d.issue_title || "")}" />
      <label>Corpo da issue (Markdown)</label>
            <textarea class="draft-body" rows="8">${esc(d.issue_body || "")}</textarea>
    `;
        container.appendChild(div);
    });
}

async function saveIssues() {
    if (!currentJobId) return;
    setPublishProgress({
        visible: true,
        percent: 10,
        text: "Preparando dados para publicação...",
        indeterminate: false,
    });
    setButtonLoading("saveBtn", true, "Publicando...");
    let statusData;
    try {
        statusData = await ApiClient.status(currentJobId);
    } catch (err) {
        renderPublishResult({
            created: 0,
            skipped: 0,
            failed: 1,
            failed_details: [{ student: "-", repository: "-", error: err.message || "Erro ao obter status" }],
        });
        setPublishProgress({
            visible: true,
            percent: 100,
            text: "Falha ao preparar publicação.",
            indeterminate: false,
        });
        setButtonLoading("saveBtn", false, "");
        return;
    }
    const drafts = statusData.drafts || [];
    setPublishProgress({
        visible: true,
        percent: 25,
        text: `Preparando ${drafts.length} issue(s)...`,
        indeterminate: false,
    });

    const payload = drafts.map((d) => {
        const key = draftKey(d);
        const card = findDraftCardByKey(key);
        const issueTitle = card?.querySelector(".draft-title")?.value || d.issue_title || "";
        const issueBody = card?.querySelector(".draft-body")?.value || d.issue_body || "";
        return {
            repository: d.repository,
            student: d.student,
            issue_title: issueTitle,
            issue_body: issueBody,
        };
    });

    setPublishProgress({
        visible: true,
        percent: 55,
        text: "Publicando issues no GitHub...",
        indeterminate: true,
    });

    let data;
    try {
        data = await ApiClient.save(currentJobId, payload);
    } catch (err) {
        renderPublishResult({
            created: 0,
            skipped: 0,
            failed: 1,
            failed_details: [{
                student: "-",
                repository: "-",
                error: err.message || "Erro ao salvar issues",
            }],
        });
        setPublishProgress({
            visible: true,
            percent: 100,
            text: "Falha ao publicar issues.",
            indeterminate: false,
        });
        setButtonLoading("saveBtn", false, "");
        return;
    }

    setPublishProgress({
        visible: true,
        percent: 100,
        text: `Publicação concluída (${Number(data.created || 0)} criada(s), ${Number(data.failed || 0)} falha(s)).`,
        indeterminate: false,
    });
    renderPublishResult(data);
    await fetchStatus();
    setButtonLoading("saveBtn", false, "");
}

function renderPublishResult(data) {
    const box = document.getElementById("publishResult");
    if (!box) return;

    const created = Number(data.created || 0);
    const skipped = Number(data.skipped || 0);
    const failed = Number(data.failed || 0);
    const failedDetails = Array.isArray(data.failed_details) ? data.failed_details : [];

    let html = `
    <h3>Resultado da publicação</h3>
    <div class="meta">
      <span>Criadas: ${created}</span>
      <span>Ignoradas: ${skipped}</span>
      <span>Falhas: ${failed}</span>
    </div>
  `;

    if (failedDetails.length > 0) {
        html += "<strong>Falhas por aluno:</strong><ul>";
        failedDetails.forEach((f) => {
            html += `<li>${esc(f.student)} (${esc(f.repository)}): ${esc(f.error)}</li>`;
        });
        html += "</ul>";
    }

    box.innerHTML = html;
    box.style.display = "block";
}

document.addEventListener("DOMContentLoaded", () => {
    const startBtn = document.getElementById("startBtn");
    const stopBtn = document.getElementById("stopBtn");
    const saveBtn = document.getElementById("saveBtn");
    const clearLogsBtn = document.getElementById("clearLogsBtn");
    const copyLogsBtn = document.getElementById("copyLogsBtn");
    const autoScrollInput = document.getElementById("autoScrollLogs");
    setupProviderSelector();
    setupExtensionsDropdown();
    if (startBtn) startBtn.addEventListener("click", startJob);
    if (stopBtn) stopBtn.addEventListener("click", stopJob);
    if (saveBtn) saveBtn.addEventListener("click", saveIssues);
    if (clearLogsBtn) {
        clearLogsBtn.addEventListener("click", () => {
            const logs = document.getElementById("logs");
            if (logs) logs.textContent = "";
        });
    }
    if (copyLogsBtn) {
        copyLogsBtn.addEventListener("click", async () => {
            const logs = document.getElementById("logs")?.textContent || "";
            if (!logs) return;
            try {
                await navigator.clipboard.writeText(logs);
                showFormMessage("Logs copiados para a área de transferência.", "info");
            } catch {
                showFormMessage("Não foi possível copiar os logs neste navegador.", "error");
            }
        });
    }
    if (autoScrollInput) {
        autoScrollInput.addEventListener("change", (ev) => {
            autoScrollLogs = Boolean(ev.target && ev.target.checked);
        });
    }
});
