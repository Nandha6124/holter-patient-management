// Holter Patient Management System: vanilla JS single-page app (hash routing, fetch API).
// All text is inserted with textContent, never innerHTML, so patient data can't inject markup.

const TOKEN_KEY = "holter_token";
const root = document.getElementById("app");

/* ---------- helpers ---------- */
function h(tag, props = {}, ...children) {
  const el = document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (k === "class") el.className = v;
    else if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
    else if (v === true) el.setAttribute(k, "");
    else if (v !== false && v != null) el.setAttribute(k, v);
  }
  for (const c of children.flat()) {
    if (c == null || c === false) continue;
    el.append(c instanceof Node ? c : document.createTextNode(String(c)));
  }
  return el;
}

const token = () => localStorage.getItem(TOKEN_KEY);

async function api(path, { method = "GET", body } = {}) {
  const headers = { "Content-Type": "application/json" };
  if (token()) headers.Authorization = `Bearer ${token()}`;
  let res;
  try {
    res = await fetch(`/api${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined });
  } catch {
    throw new Error("Cannot reach the server");
  }
  if (res.status === 401 && path !== "/auth/login") {
    localStorage.removeItem(TOKEN_KEY);
    location.hash = "";
    render();
    throw new Error("Session expired, please sign in again");
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const d = data.detail;
    throw new Error(Array.isArray(d) ? d.map((e) => `${(e.loc || []).slice(1).join(".")}: ${e.msg}`).join("; ") : d || "Request failed");
  }
  return data;
}

const fmtDate = (d) => new Date(d + "T00:00:00").toLocaleDateString(undefined, { year: "numeric", month: "short", day: "numeric" });
const sexLabel = { M: "Male", F: "Female", O: "Other" };
const statusBadge = (s) => h("span", { class: `badge ${s}` }, s);

/* ---------- modal form ---------- */
function openForm({ title, fields, initial = {}, submitLabel = "Save", onSubmit }) {
  const inputs = {};
  const errorBox = h("div", { class: "error" });
  const grid = h("div", { class: "grid2" });
  for (const f of fields) {
    let input;
    if (f.type === "select") {
      input = h("select", {}, f.options.map(([v, l]) => h("option", { value: v }, l)));
    } else if (f.type === "textarea") {
      input = h("textarea", { maxlength: f.max || 2000 });
    } else if (f.type === "checkbox") {
      input = h("input", { type: "checkbox" });
    } else {
      input = h("input", { type: f.type || "text", ...(f.attrs || {}) });
    }
    const val = initial[f.name] ?? f.default ?? "";
    if (f.type === "checkbox") input.checked = Boolean(val);
    else if (f.type === "select") input.value = val !== "" ? val : f.options[0][0];  // never leave a select blank
    else input.value = val;
    inputs[f.name] = input;
    const label = h("label", { class: f.type === "checkbox" ? "check" : "", style: f.wide ? "grid-column: 1 / -1" : null },
      f.type === "checkbox" ? [input, f.label] : [f.label, input]);
    grid.append(label);
  }
  const close = () => overlay.remove();
  const form = h("form", {
    onsubmit: async (e) => {
      e.preventDefault();
      errorBox.textContent = "";
      const values = {};
      for (const f of fields) {
        const el = inputs[f.name];
        if (f.type === "checkbox") values[f.name] = el.checked;
        else if (f.type === "number") values[f.name] = el.value === "" ? null : Number(el.value);
        else values[f.name] = el.value.trim();
      }
      try {
        await onSubmit(values);
        close();
      } catch (err) {
        errorBox.textContent = err.message;
      }
    },
  },
    h("h3", {}, title), grid, errorBox,
    h("div", { class: "row", style: "justify-content:flex-end;margin:12px 0 0" },
      h("button", { type: "button", class: "secondary", onclick: close }, "Cancel"),
      h("button", { type: "submit" }, submitLabel)));
  const overlay = h("div", { class: "overlay", onclick: (e) => e.target === overlay && close() }, h("div", { class: "modal" }, form));
  document.body.append(overlay);
  overlay.querySelector("input,select,textarea")?.focus();
}

const patientFields = [
  { name: "full_name", label: "Full name", wide: true, attrs: { required: true, minlength: 2, maxlength: 120 } },
  { name: "age", label: "Age", type: "number", attrs: { required: true, min: 0, max: 120 } },
  { name: "sex", label: "Sex", type: "select", options: [["F", "Female"], ["M", "Male"], ["O", "Other"]] },
  { name: "phone", label: "Phone", attrs: { maxlength: 30 } },
  { name: "indication", label: "Indication for Holter", attrs: { maxlength: 200 } },
  { name: "notes", label: "Notes", type: "textarea", wide: true },
];

const recordingFields = [
  { name: "recorded_on", label: "Recording date", type: "date", default: new Date().toISOString().slice(0, 10), attrs: { required: true } },
  { name: "duration_hours", label: "Duration (hours)", type: "number", default: 24, attrs: { required: true, min: 1, max: 240, step: "any" } },
  { name: "avg_hr", label: "Average HR (bpm)", type: "number", attrs: { required: true, min: 20, max: 250 } },
  { name: "min_hr", label: "Minimum HR (bpm)", type: "number", attrs: { required: true, min: 20, max: 250 } },
  { name: "max_hr", label: "Maximum HR (bpm)", type: "number", attrs: { required: true, min: 20, max: 250 } },
  { name: "pvc_count", label: "PVC count", type: "number", default: 0, attrs: { min: 0 } },
  { name: "pause_count", label: "Pauses (>2 s)", type: "number", default: 0, attrs: { min: 0 } },
  { name: "status", label: "Status", type: "select", options: [["pending", "Pending review"], ["reviewed", "Reviewed"]] },
  { name: "af_detected", label: "Atrial fibrillation detected", type: "checkbox" },
  { name: "summary", label: "Findings / summary", type: "textarea", wide: true },
];

/* ---------- views ---------- */
function loginView() {
  const err = h("div", { class: "error" });
  const email = h("input", { type: "email", required: true, autocomplete: "username" });
  const pw = h("input", { type: "password", required: true, autocomplete: "current-password" });
  const form = h("form", {
    class: "card",
    onsubmit: async (e) => {
      e.preventDefault();
      err.textContent = "";
      try {
        const { access_token } = await api("/auth/login", { method: "POST", body: { email: email.value, password: pw.value } });
        localStorage.setItem(TOKEN_KEY, access_token);
        location.hash = "#/dashboard";
        render();
      } catch (ex) {
        err.textContent = ex.message;
      }
    },
  },
    h("h1", {}, "Holter PMS"), h("div", { class: "muted" }, "Staff sign in"),
    h("label", {}, "Email", email), h("label", {}, "Password", pw), err, h("button", { type: "submit" }, "Sign in"),
    h("div", { class: "disclaimer" }, "Demonstration software for learning. Use synthetic data only. Not a medical device."));
  return h("div", { class: "login" }, form);
}

function shell(active, content) {
  const link = (href, label, key) => h("a", { href, class: active === key ? "active" : "" }, label);
  return h("div", {},
    h("header", {}, h("h1", {}, "Holter PMS"),
      h("nav", {}, link("#/dashboard", "Dashboard", "dashboard"), link("#/patients", "Patients", "patients")),
      h("button", { class: "secondary small", onclick: () => { localStorage.removeItem(TOKEN_KEY); location.hash = ""; render(); } }, "Log out")),
    h("main", {}, content),
    h("div", { class: "disclaimer" }, "Demonstration software. Use synthetic data only. Not a medical device."));
}

async function dashboardView() {
  const s = await api("/dashboard");
  const stat = (n, l, cls = "") => h("div", { class: `stat ${cls}` }, h("div", { class: "n" }, n ?? "–"), h("div", { class: "l" }, l));
  const rows = s.recent.map((r) =>
    h("tr", { class: "click", onclick: () => (location.hash = `#/patients/${r.patient_id}`) },
      h("td", {}, r.patient_name), h("td", { class: "muted" }, r.patient_mrn), h("td", {}, fmtDate(r.recorded_on)),
      h("td", {}, `${r.avg_hr} (${r.min_hr}–${r.max_hr})`), h("td", {}, r.af_detected ? h("span", { class: "badge af" }, "AF") : "–"),
      h("td", {}, statusBadge(r.status))));
  return shell("dashboard", [
    h("h2", {}, "Dashboard"),
    h("div", { class: "stats" },
      stat(s.total_patients, "Patients"), stat(s.total_recordings, "Holter recordings"),
      stat(s.pending_review, "Pending review", s.pending_review ? "warn" : ""),
      stat(s.af_flagged, "AF flagged", s.af_flagged ? "alert" : ""),
      stat(s.avg_heart_rate, "Mean of avg HR (bpm)")),
    h("div", { class: "card" }, h("h3", {}, "Recent recordings"),
      rows.length
        ? h("div", { class: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["Patient", "MRN", "Date", "HR avg (min–max)", "AF", "Status"].map((t) => h("th", {}, t)))), h("tbody", {}, rows)))
        : h("div", { class: "empty" }, "No recordings yet.")),
  ]);
}

async function patientsView() {
  const tbody = h("tbody");
  const search = h("input", { type: "search", placeholder: "Search by name, MRN or phone…", class: "grow" });
  let timer;
  const load = async () => {
    const q = search.value.trim();
    const list = await api(`/patients${q ? `?q=${encodeURIComponent(q)}` : ""}`);
    tbody.replaceChildren(...(list.length ? list.map((p) =>
      h("tr", { class: "click", onclick: () => (location.hash = `#/patients/${p.id}`) },
        h("td", { class: "muted" }, p.mrn), h("td", {}, p.full_name), h("td", {}, `${p.age} / ${p.sex}`),
        h("td", {}, p.phone || "–"), h("td", {}, p.indication || "–"), h("td", {}, p.recording_count)))
      : [h("tr", {}, h("td", { colspan: 6, class: "empty" }, q ? "No patients match your search." : "No patients yet. Add the first one."))]));
  };
  search.addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => load().catch(() => {}), 250); });
  await load();
  return shell("patients", [
    h("h2", {}, "Patients"),
    h("div", { class: "row" }, search, h("button", {
      onclick: () => openForm({
        title: "Register patient", fields: patientFields, submitLabel: "Register",
        onSubmit: async (v) => { const p = await api("/patients", { method: "POST", body: v }); location.hash = `#/patients/${p.id}`; },
      }),
    }, "+ Register patient")),
    h("div", { class: "card table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["MRN", "Name", "Age / Sex", "Phone", "Indication", "Recordings"].map((t) => h("th", {}, t)))), tbody)),
  ]);
}

async function patientView(id) {
  const [p, recs] = await Promise.all([api(`/patients/${id}`), api(`/patients/${id}/recordings`)]);
  const reload = () => render();
  const recRows = recs.map((r) => h("tr", {},
    h("td", {}, fmtDate(r.recorded_on)), h("td", {}, `${r.duration_hours} h`),
    h("td", {}, `${r.avg_hr} (${r.min_hr}–${r.max_hr})`), h("td", {}, r.pvc_count), h("td", {}, r.pause_count),
    h("td", {}, r.af_detected ? h("span", { class: "badge af" }, "AF") : "–"), h("td", {}, statusBadge(r.status)),
    h("td", { style: "white-space:normal;min-width:160px" }, r.summary || "–"),
    h("td", {}, h("div", { class: "actions" },
      h("button", { class: "secondary small", onclick: () => openForm({ title: "Edit recording", fields: recordingFields, initial: r,
        onSubmit: async (v) => { await api(`/recordings/${r.id}`, { method: "PUT", body: v }); reload(); } }) }, "Edit"),
      h("button", { class: "danger small", onclick: async () => { if (confirm("Delete this recording?")) { await api(`/recordings/${r.id}`, { method: "DELETE" }); reload(); } } }, "Delete")))));
  const field = (label, value) => h("div", {}, h("span", {}, label), value || "–");
  return shell("patients", [
    h("div", { class: "row" }, h("a", { href: "#/patients" }, "← Patients")),
    h("div", { class: "card" },
      h("div", { class: "row", style: "margin:0" }, h("h2", { class: "grow", style: "margin:0" }, p.full_name),
        h("button", { class: "secondary small", onclick: () => openForm({ title: "Edit patient", fields: patientFields, initial: p,
          onSubmit: async (v) => { await api(`/patients/${id}`, { method: "PUT", body: v }); reload(); } }) }, "Edit"),
        h("button", { class: "danger small", onclick: async () => {
          if (confirm(`Delete ${p.full_name} and all their recordings? This cannot be undone.`)) { await api(`/patients/${id}`, { method: "DELETE" }); location.hash = "#/patients"; }
        } }, "Delete")),
      h("div", { class: "detail" }, field("MRN", p.mrn), field("Age", p.age), field("Sex", sexLabel[p.sex]), field("Phone", p.phone), field("Indication", p.indication)),
      p.notes && h("div", {}, h("span", { class: "muted" }, "Notes"), h("div", {}, p.notes))),
    h("div", { class: "card" },
      h("div", { class: "row", style: "margin-bottom:8px" }, h("h3", { class: "grow", style: "margin:0" }, "Holter recordings"),
        h("button", { class: "small", onclick: () => openForm({ title: "Add Holter recording", fields: recordingFields,
          onSubmit: async (v) => { await api(`/patients/${id}/recordings`, { method: "POST", body: v }); reload(); } }) }, "+ Add recording")),
      recs.length
        ? h("div", { class: "table-wrap" }, h("table", {}, h("thead", {}, h("tr", {}, ["Date", "Duration", "HR avg (min–max)", "PVCs", "Pauses", "AF", "Status", "Summary", ""].map((t) => h("th", {}, t)))), h("tbody", {}, recRows)))
        : h("div", { class: "empty" }, "No recordings for this patient yet.")),
  ]);
}

/* ---------- router ---------- */
let renderSeq = 0;
async function render() {
  const seq = ++renderSeq;  // a newer render supersedes this one (avoids stale views overwriting fresh ones)
  if (!token()) return root.replaceChildren(loginView());
  const [, section, id] = (location.hash || "#/dashboard").split("/");
  try {
    let view;
    if (section === "patients" && id) view = await patientView(Number(id));
    else if (section === "patients") view = await patientsView();
    else view = await dashboardView();
    if (seq === renderSeq) root.replaceChildren(view);
  } catch (err) {
    if (!token() || seq !== renderSeq) return;
    root.replaceChildren(shell("", h("div", { class: "card" }, h("div", { class: "error" }, err.message), h("a", { href: "#/dashboard" }, "Back to dashboard"))));
  }
}

window.addEventListener("hashchange", render);
render();
