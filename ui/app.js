const PROJECT_RESULT_PATH = "../runs/result.json";
const API_HEALTH_PATH = "/api/health";
const API_INSPECT_PATH = "/api/inspect";
const API_MISSING_MESSAGE =
  "Inspection API is not available. Start it with python report_server.py --port 8766 and open http://127.0.0.1:8766/ui/.";

const checks = [
  {
    key: "form_found",
    label: "Form detected",
    present: (report) => report.form_found === true,
    detail: (report) =>
      report.form_found
        ? `${count(report.form_evidence)} form evidence item${plural(report.form_evidence)}`
        : "No visible form was confirmed",
  },
  {
    key: "steps",
    label: "Step history",
    present: (report) => count(report.steps) > 0,
    detail: (report) => `${count(report.steps)} recorded navigation step${plural(report.steps)}`,
  },
  {
    key: "screenshots",
    label: "Screenshots",
    present: (report) => count(report.screenshots) > 0,
    detail: (report) => `${count(report.screenshots)} artifact${plural(report.screenshots)} captured`,
  },
  {
    key: "consent_evidence",
    label: "Consent evidence",
    present: (report) => Boolean(report.submit_language) || count(report.consent_evidence) > 0,
    detail: (report) =>
      report.submit_language || `${count(report.consent_evidence)} consent item${plural(report.consent_evidence)}`,
  },
  {
    key: "terms_url",
    label: "Terms URL",
    present: (report) => Boolean(report.terms_url),
    detail: (report) => report.terms_url || "Terms link was not returned",
  },
  {
    key: "terms_text",
    label: "Terms text",
    present: (report) => Boolean(report.terms_text),
    detail: (report) => textLength(report.terms_text),
  },
  {
    key: "privacy_url",
    label: "Privacy URL",
    present: (report) => Boolean(report.privacy_url),
    detail: (report) => report.privacy_url || "Privacy link was not returned",
  },
  {
    key: "privacy_text",
    label: "Privacy text",
    present: (report) => Boolean(report.privacy_text),
    detail: (report) => textLength(report.privacy_text),
  },
  {
    key: "errors",
    label: "Errors",
    present: (report) => count(report.errors) === 0,
    issueWhenMissing: true,
    detail: (report) =>
      count(report.errors) === 0 ? "No extraction errors returned" : report.errors.join(" | "),
  },
];

const state = {
  apiAvailable: false,
  raw: null,
  report: null,
};

const elements = {};

document.addEventListener("DOMContentLoaded", () => {
  bindElements();
  bindEvents();
  renderEmpty();
  checkApiHealth();
  loadLatest();
});

function bindElements() {
  for (const id of [
    "loadLatestButton",
    "resultFile",
    "pasteButton",
    "pastePanel",
    "jsonInput",
    "applyJsonButton",
    "clearJsonButton",
    "dropZone",
    "targetUrl",
    "assessmentBadge",
    "summaryGrid",
    "coverageList",
    "stepsList",
    "evidenceList",
    "formCandidateList",
    "policyList",
    "screenshotGrid",
    "rawJson",
    "copyRawButton",
    "emptyStateTemplate",
    "inspectForm",
    "urlInput",
    "maxStepsInput",
    "maxRuntimeInput",
    "modelInput",
    "useLlmInput",
    "headfulInput",
    "runInspectionButton",
    "runStatus",
  ]) {
    elements[id] = document.getElementById(id);
  }
}

function bindEvents() {
  elements.inspectForm.addEventListener("submit", runInspection);
  elements.loadLatestButton.addEventListener("click", loadLatest);
  elements.resultFile.addEventListener("change", handleFileImport);
  elements.pasteButton.addEventListener("click", togglePastePanel);
  elements.applyJsonButton.addEventListener("click", applyPastedJson);
  elements.clearJsonButton.addEventListener("click", () => {
    elements.jsonInput.value = "";
  });
  elements.copyRawButton.addEventListener("click", copyRawJson);

  elements.dropZone.addEventListener("dragover", (event) => {
    event.preventDefault();
    elements.dropZone.classList.add("dragging");
  });
  elements.dropZone.addEventListener("dragleave", () => {
    elements.dropZone.classList.remove("dragging");
  });
  elements.dropZone.addEventListener("drop", handleDrop);
}

async function runInspection(event) {
  event.preventDefault();
  if (!state.apiAvailable) {
    renderError(API_MISSING_MESSAGE);
    setRunning(false, "API Offline");
    return;
  }
  const payload = {
    url: elements.urlInput.value.trim(),
    max_steps: Number(elements.maxStepsInput.value || 5),
    max_runtime: Number(elements.maxRuntimeInput.value || 120),
    model: elements.modelInput.value.trim(),
    use_llm: elements.useLlmInput.checked,
    headful: elements.headfulInput.checked,
  };
  if (!payload.url) {
    renderError("Enter a URL before running inspection.");
    return;
  }

  setRunning(true, "Inspecting");
  renderEmpty(`Running inspection for ${payload.url}`);
  try {
    const response = await fetch(API_INSPECT_PATH, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await readJsonResponse(response, "Inspection API");
    if (!response.ok) {
      throw new Error(result.error || `HTTP ${response.status}`);
    }
    setReport(result);
    setRunning(false, "Complete");
  } catch (error) {
    renderError(error.message || "Inspection failed.");
    setRunning(false, "Failed");
  }
}

async function checkApiHealth() {
  try {
    const response = await fetch(`${API_HEALTH_PATH}?t=${Date.now()}`, { cache: "no-store" });
    const payload = await readJsonResponse(response, "Inspection API");
    state.apiAvailable = response.ok && payload.ok === true;
  } catch (error) {
    state.apiAvailable = false;
  }

  if (state.apiAvailable) {
    elements.runInspectionButton.disabled = false;
    elements.runStatus.textContent = "Ready";
  } else {
    elements.runInspectionButton.disabled = true;
    elements.runStatus.textContent = "API Offline";
  }
}

async function loadLatest() {
  try {
    const response = await fetch(`${PROJECT_RESULT_PATH}?t=${Date.now()}`, { cache: "no-store" });
    if (!response.ok) {
      throw new Error(`HTTP ${response.status}`);
    }
    const report = await readJsonResponse(response, PROJECT_RESULT_PATH);
    setReport(report);
  } catch (error) {
    renderEmpty(`Could not load ${PROJECT_RESULT_PATH}`);
  }
}

async function handleFileImport(event) {
  const file = event.target.files?.[0];
  if (!file) return;
  try {
    const text = await file.text();
    setReport(JSON.parse(text));
  } catch (error) {
    renderError("The selected file is not valid report JSON.");
  } finally {
    event.target.value = "";
  }
}

async function handleDrop(event) {
  event.preventDefault();
  elements.dropZone.classList.remove("dragging");
  const file = event.dataTransfer.files?.[0];
  if (!file) return;
  try {
    const text = await file.text();
    setReport(JSON.parse(text));
  } catch (error) {
    renderError("Dropped file could not be parsed as report JSON.");
  }
}

function togglePastePanel() {
  elements.pastePanel.hidden = !elements.pastePanel.hidden;
  if (!elements.pastePanel.hidden) {
    elements.jsonInput.focus();
  }
}

function applyPastedJson() {
  try {
    setReport(JSON.parse(elements.jsonInput.value));
    elements.pastePanel.hidden = true;
  } catch (error) {
    renderError("Pasted content is not valid JSON.");
  }
}

async function copyRawJson() {
  if (!state.raw) return;
  const rawText = JSON.stringify(state.raw, null, 2);
  try {
    if (!navigator.clipboard?.writeText) {
      throw new Error("Clipboard API unavailable");
    }
    await navigator.clipboard.writeText(rawText);
  } catch (error) {
    const fallback = document.createElement("textarea");
    fallback.value = rawText;
    fallback.setAttribute("readonly", "");
    fallback.style.position = "fixed";
    fallback.style.inset = "-9999px";
    document.body.append(fallback);
    fallback.select();
    document.execCommand("copy");
    fallback.remove();
  }
  const original = elements.copyRawButton.textContent;
  elements.copyRawButton.textContent = "Copied";
  window.setTimeout(() => {
    elements.copyRawButton.textContent = original;
  }, 1200);
}

function setReport(report) {
  state.raw = report;
  state.report = normalizeReport(report);
  if (state.report.final_url && !elements.urlInput.value) {
    elements.urlInput.value = state.report.final_url;
  }
  renderReport();
}

function normalizeReport(report) {
  return {
    form_found: Boolean(report?.form_found),
    final_url: value(report?.final_url),
    steps: array(report?.steps),
    screenshots: array(report?.screenshots),
    submit_language: value(report?.submit_language),
    consent_evidence: array(report?.consent_evidence),
    form_candidates: array(report?.form_candidates),
    primary_form_candidate: report?.primary_form_candidate || null,
    llm_form_assessment: report?.llm_form_assessment || {},
    llm_button_candidates: array(report?.llm_button_candidates),
    decision_source: value(report?.decision_source),
    terms_url: value(report?.terms_url),
    privacy_url: value(report?.privacy_url),
    terms_text: value(report?.terms_text),
    privacy_text: value(report?.privacy_text),
    link_evidence: array(report?.link_evidence),
    form_evidence: array(report?.form_evidence),
    errors: array(report?.errors),
  };
}

function renderReport() {
  const report = state.report;
  const assessment = assess(report);
  elements.targetUrl.textContent = report.final_url || "Unknown target";
  elements.assessmentBadge.textContent = assessment.label;
  elements.assessmentBadge.className = `assessment-badge ${assessment.tone}`;

  renderSummary(report, assessment);
  renderCoverage(report);
  renderSteps(report);
  renderEvidence(report);
  renderFormCandidates(report);
  renderPolicies(report);
  renderScreenshots(report);
  elements.rawJson.textContent = JSON.stringify(state.raw, null, 2);
}

function renderFormCandidates(report) {
  const candidates = report.form_candidates;
  const hasLlmAssessment = Object.keys(report.llm_form_assessment || {}).length > 0;
  const hasLlmButtons = report.llm_button_candidates.length > 0;
  if (!candidates.length && !hasLlmAssessment && !hasLlmButtons) {
    renderTemplate(elements.formCandidateList);
    return;
  }
  const primarySelector = value(report.primary_form_candidate?.selector);
  const llmAssessment = hasLlmAssessment ? renderLlmFormAssessment(report.llm_form_assessment) : "";
  const llmButtons = hasLlmButtons ? renderLlmButtonCandidates(report.llm_button_candidates) : "";
  const domCandidates = candidates
    .map((candidate, index) => {
      const selector = value(candidate.selector);
      const isPrimary = index === 0 || (primarySelector && selector === primarySelector);
      return `
        <div class="candidate-item ${isPrimary ? "primary" : ""}">
          <div class="candidate-top">
            <div>
              <span class="timeline-index">${String(index + 1).padStart(2, "0")}</span>
              <strong>${escapeHtml(value(candidate.label) || value(candidate.text) || "Unnamed candidate")}</strong>
            </div>
            <span class="status-pill ${isPrimary ? "present" : "issue"}">${isPrimary ? "Selected" : "Candidate"}</span>
          </div>
          <p class="detail-text">${escapeHtml(value(candidate.reason) || "No detector reason returned")}</p>
          <div class="candidate-grid">
            <span><b>Kind</b>${escapeHtml(value(candidate.kind) || "unknown")}</span>
            <span><b>Score</b>${escapeHtml(value(candidate.score) || "0")}</span>
            <span><b>Selector</b>${escapeHtml(selector || "not returned")}</span>
            <span><b>Inputs</b>${escapeHtml(value(candidate.input_count) || "0")}</span>
            <span><b>Submit Controls</b>${escapeHtml(value(candidate.submit_button_count) || "0")}</span>
            <span><b>Box</b>${escapeHtml(formatBox(candidate))}</span>
          </div>
          ${
            candidate.text
              ? `<div class="candidate-text">${escapeHtml(candidate.text)}</div>`
              : ""
          }
        </div>
      `;
    })
    .join("");
  elements.formCandidateList.innerHTML = llmAssessment + llmButtons + domCandidates;
}

function renderLlmFormAssessment(assessment) {
  const fields = array(assessment.visible_fields);
  return `
    <div class="candidate-item primary">
      <div class="candidate-top">
        <div>
          <span class="timeline-index">LLM</span>
          <strong>${escapeHtml(value(assessment.label) || value(assessment.purpose) || "Finance form assessment")}</strong>
        </div>
        <span class="status-pill present">Selected</span>
      </div>
      <p class="detail-text">${escapeHtml(value(assessment.why_valid_finance_form) || value(assessment.reason) || "LLM marked this as the valid finance form.")}</p>
      <div class="candidate-grid">
        <span><b>Purpose</b>${escapeHtml(value(assessment.purpose) || "not returned")}</span>
        <span><b>Location</b>${escapeHtml(value(assessment.location) || "not returned")}</span>
        <span><b>Submit</b>${escapeHtml(value(assessment.submit_text) || "not returned")}</span>
        <span><b>Confidence</b>${escapeHtml(value(assessment.confidence) || "0")}</span>
        <span><b>Fields</b>${escapeHtml(fields.join(", ") || "not returned")}</span>
        <span><b>Consent</b>${escapeHtml(value(assessment.consent_or_disclosure) || "not returned")}</span>
      </div>
    </div>
  `;
}

function renderLlmButtonCandidates(candidates) {
  return `
    <div class="candidate-item">
      <div class="candidate-top">
        <div>
          <span class="timeline-index">CTA</span>
          <strong>LLM Button Candidates</strong>
        </div>
        <span class="status-pill issue">${candidates.length}</span>
      </div>
      <ul class="candidate-buttons">
        ${candidates
          .map(
            (candidate) => `
              <li>
                <strong>${escapeHtml(value(candidate.text))}</strong>
                <span>${escapeHtml(value(candidate.reason) || "No reason returned")}</span>
                <em>${escapeHtml(value(candidate.confidence) || "0")}</em>
              </li>
            `
          )
          .join("")}
      </ul>
    </div>
  `;
}

function assess(report) {
  const missing = checks.filter((check) => !check.present(report) && !check.issueWhenMissing);
  const hasErrors = count(report.errors) > 0;
  if (!report.form_found) {
    return { label: "Blocked", tone: "bad" };
  }
  if (hasErrors || missing.length > 0) {
    return { label: "Needs Review", tone: "warn" };
  }
  return { label: "Complete", tone: "good" };
}

function renderSummary(report, assessment) {
  const metrics = [
    ["Status", assessment.label],
    ["Steps", count(report.steps)],
    ["Screenshots", count(report.screenshots)],
    ["Missing", checks.filter((check) => !check.present(report) && !check.issueWhenMissing).length],
  ];
  elements.summaryGrid.innerHTML = metrics
    .map(
      ([label, metric]) => `
        <div class="metric">
          <span>${escapeHtml(label)}</span>
          <strong>${escapeHtml(String(metric))}</strong>
        </div>
      `
    )
    .join("");
}

function renderCoverage(report) {
  elements.coverageList.innerHTML = checks
    .map((check) => {
      const present = check.present(report);
      const status = present ? "present" : check.issueWhenMissing ? "issue" : "missing";
      const label = present ? "Present" : check.issueWhenMissing ? "Issue" : "Missing";
      return `
        <div class="coverage-row">
          <strong>${escapeHtml(check.label)}</strong>
          <span class="status-pill ${status}">${label}</span>
          <p class="detail-text">${escapeHtml(check.detail(report) || "No detail returned")}</p>
        </div>
      `;
    })
    .join("");
}

function renderSteps(report) {
  if (!report.steps.length) {
    renderTemplate(elements.stepsList);
    return;
  }
  elements.stepsList.innerHTML = report.steps
    .map((step, index) => {
      const success = step.success ? "Present" : "Issue";
      const statusClass = step.success ? "present" : "issue";
      return `
        <div class="timeline-item">
          <div class="timeline-top">
            <div>
              <span class="timeline-index">${indexLabel(step.index, index)}</span>
              <strong>${escapeHtml(value(step.action) || "unknown action")}</strong>
            </div>
            <span class="status-pill ${statusClass}">${success}</span>
          </div>
          <p class="detail-text">${escapeHtml(value(step.reason) || "No reason returned")}</p>
          <div class="meta-list">
            <span>${escapeHtml(value(step.url) || "No URL")}</span>
            <span>${escapeHtml(value(step.target) || "No target")}</span>
            <span>${count(step.screenshots)} screenshot${plural(step.screenshots)}</span>
          </div>
          ${step.error ? `<p class="detail-text">${escapeHtml(step.error)}</p>` : ""}
        </div>
      `;
    })
    .join("");
}

function renderEvidence(report) {
  const groups = [
    ["Submit language", array(report.submit_language ? [report.submit_language] : [])],
    ["Consent evidence", report.consent_evidence],
    ["Form evidence", report.form_evidence],
  ];
  elements.evidenceList.innerHTML = groups
    .map(
      ([title, items]) => `
        <div class="evidence-item">
          <strong>${escapeHtml(title)}</strong>
          ${renderList(items)}
        </div>
      `
    )
    .join("");
}

function renderPolicies(report) {
  const policies = [
    ["Terms", report.terms_url, report.terms_text],
    ["Privacy", report.privacy_url, report.privacy_text],
  ];
  const linkEvidence = report.link_evidence.length
    ? `
      <div class="policy-item">
        <strong>Link evidence</strong>
        ${renderList(report.link_evidence.map((item) => `${value(item.text)} - ${value(item.href)}`))}
      </div>
    `
    : "";

  elements.policyList.innerHTML =
    policies
      .map(
        ([title, url, text]) => `
          <div class="policy-item">
            <strong>${escapeHtml(title)}</strong>
            <div class="policy-actions">
              ${
                url
                  ? `<a href="${escapeAttribute(url)}" target="_blank" rel="noreferrer">Open ${escapeHtml(title)}</a>`
                  : `<span class="status-pill missing">Missing URL</span>`
              }
              <span class="status-pill ${text ? "present" : "missing"}">${text ? "Text Present" : "Missing Text"}</span>
            </div>
            ${text ? `<div class="policy-text">${escapeHtml(text)}</div>` : ""}
          </div>
        `
      )
      .join("") + linkEvidence;
}

function renderScreenshots(report) {
  if (!report.screenshots.length) {
    renderTemplate(elements.screenshotGrid);
    return;
  }
  elements.screenshotGrid.innerHTML = report.screenshots
    .map((path, index) => {
      const src = screenshotUrl(path);
      const label = shortPath(path);
      return `
        <div class="screenshot-tile">
          <a href="${escapeAttribute(src)}" target="_blank" rel="noreferrer">
            <img src="${escapeAttribute(src)}" alt="Screenshot ${index + 1}" loading="lazy" />
            ${escapeHtml(label)}
          </a>
        </div>
      `;
    })
    .join("");
}

function renderEmpty(message = "No report loaded") {
  state.raw = null;
  state.report = null;
  elements.targetUrl.textContent = message;
  elements.assessmentBadge.textContent = "Waiting";
  elements.assessmentBadge.className = "assessment-badge muted";
  elements.summaryGrid.innerHTML = "";
  for (const target of [
    elements.coverageList,
    elements.stepsList,
    elements.evidenceList,
    elements.formCandidateList,
    elements.policyList,
    elements.screenshotGrid,
  ]) {
    renderTemplate(target);
  }
  elements.rawJson.textContent = "{}";
}

function renderError(message) {
  elements.targetUrl.textContent = message;
  elements.assessmentBadge.textContent = "Issue";
  elements.assessmentBadge.className = "assessment-badge bad";
}

function setRunning(isRunning, label) {
  elements.runInspectionButton.disabled = isRunning || !state.apiAvailable;
  elements.loadLatestButton.disabled = isRunning;
  elements.runStatus.textContent = label;
  elements.inspectForm.classList.toggle("is-running", isRunning);
}

async function readJsonResponse(response, source) {
  const text = await response.text();
  try {
    return JSON.parse(text);
  } catch (error) {
    const contentType = response.headers.get("content-type") || "unknown content";
    const looksLikeHtml = text.trim().startsWith("<");
    if (looksLikeHtml) {
      throw new Error(`${source} returned HTML instead of JSON. ${API_MISSING_MESSAGE}`);
    }
    throw new Error(`${source} returned invalid JSON (${contentType}).`);
  }
}

function renderTemplate(target) {
  target.innerHTML = "";
  target.append(elements.emptyStateTemplate.content.cloneNode(true));
}

function renderList(items) {
  if (!items.length) {
    return `<div class="empty-state"><span>Missing</span></div>`;
  }
  return `<ul>${items.map((item) => `<li>${escapeHtml(String(item))}</li>`).join("")}</ul>`;
}

function screenshotUrl(path) {
  const normalized = String(path || "").replaceAll("\\", "/");
  const runIndex = normalized.toLowerCase().indexOf("/runs/");
  if (runIndex >= 0) {
    return `..${normalized.slice(runIndex)}`;
  }
  if (normalized.startsWith("runs/")) {
    return `../${normalized}`;
  }
  return normalized;
}

function shortPath(path) {
  const normalized = String(path || "").replaceAll("\\", "/");
  const parts = normalized.split("/").filter(Boolean);
  return parts.slice(-3).join("/");
}

function indexLabel(value, fallback) {
  const number = Number.isFinite(Number(value)) ? Number(value) : fallback;
  return String(number).padStart(2, "0");
}

function count(value) {
  return Array.isArray(value) ? value.length : 0;
}

function plural(value) {
  return count(value) === 1 ? "" : "s";
}

function textLength(text) {
  return text ? `${text.length.toLocaleString()} characters returned` : "Document text was not returned";
}

function formatBox(candidate) {
  const x = Number(candidate.x || 0);
  const y = Number(candidate.y || 0);
  const width = Number(candidate.width || 0);
  const height = Number(candidate.height || 0);
  return `x ${x}, y ${y}, ${width} x ${height}`;
}

function value(input) {
  return input === null || input === undefined ? "" : String(input);
}

function array(input) {
  return Array.isArray(input) ? input : [];
}

function escapeHtml(input) {
  return String(input)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function escapeAttribute(input) {
  return escapeHtml(input).replaceAll("`", "&#096;");
}
