/* AirDrop Compress - dashboard & settings UI. Talks to Python via window.pywebview.api. */
"use strict";

const $ = (sel, el = document) => el.querySelector(sel);
const $$ = (sel, el = document) => [...el.querySelectorAll(sel)];
const api = () => window.pywebview.api;

const state = { settings: null, schema: null, app: null, formats: null, plugins: [], revision: -1,
                activity: [], filter: "all", status: null, update: null, historyCount: 0 };

const ICON = {
  image: '<svg viewBox="0 0 24 24"><path d="M21 19V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2M8.5 13.5l2.5 3 3.5-4.5 4.5 6H5z"/></svg>',
  document: '<svg viewBox="0 0 24 24"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8zm-1 7V3.5L18.5 9zM8 13h8v2H8zm0 4h5v2H8z"/></svg>',
  plugin: '<svg viewBox="0 0 24 24"><path d="M20.5 11H19V7a2 2 0 0 0-2-2h-4V3.5a2.5 2.5 0 0 0-5 0V5H4a2 2 0 0 0-2 2v3.8h1.5a2.7 2.7 0 0 1 0 5.4H2V20a2 2 0 0 0 2 2h3.8v-1.5a2.7 2.7 0 0 1 5.4 0V22H17a2 2 0 0 0 2-2v-4h1.5a2.5 2.5 0 0 0 0-5"/></svg>',
  other: '<svg viewBox="0 0 24 24"><path d="M6 2a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm7 7V3.5L18.5 9z"/></svg>',
  warn: '<svg viewBox="0 0 24 24"><path d="M1 21h22L12 2zm12-3h-2v-2h2zm0-4h-2v-4h2z"/></svg>',
  info: '<svg viewBox="0 0 24 24"><path d="M12 2a10 10 0 1 0 0 20 10 10 0 0 0 0-20m1 15h-2v-6h2zm0-8h-2V7h2z"/></svg>',
  inbox: '<svg viewBox="0 0 24 24"><path d="M19 3H5a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2m0 12h-4a3 3 0 0 1-6 0H5V5h14z"/></svg>',
};

const FORMAT_HELP = {
  auto: { lead: "Encodes each image as WebP, AVIF and JPEG (WebP and AVIF if it has transparency) and keeps the smallest. No single format wins every time: photos often favour AVIF, graphics WebP.",
          pros: ["Always the smallest file", "Good when images go to different places"], cons: ["About three times slower", "The file type can differ from image to image"] },
  webp: { lead: "Google's format, supported by every modern browser. Typically 25–35% smaller than JPEG at the same visual quality.",
          pros: ["Transparency and animation", "Fast to create", "Accepted by most websites and CMSs"], cons: ["Some older apps, email clients and print services don't accept it"] },
  avif: { lead: "The newest format. For photos it's often 20–50% smaller than WebP.",
          pros: ["Smallest photos", "Wide colour and HDR", "Transparency and animation"], cons: ["Slower to create", "Needs Safari 16+ / iOS 16+; some CMSs and social sites reject it"] },
  jpeg: { lead: "The universal format. Choose it when compatibility matters more than file size.",
          pros: ["Opens everywhere: email, Office, marketplaces, print", "Progressive loading"], cons: ["Largest files", "No transparency (flattened onto white)", "No animation"] },
};

const STATE_INFO = {
  running: ["Watching for AirDrop files", "running"],
  starting: ["Starting…", "paused"],
  paused: ["Paused", "paused"],
  stopped: ["Stopped", "paused"],
  waiting_access: ["Waiting for permission", "problem"],
  locked: ["Another copy is running", "problem"],
  legacy: ["Action needed", "problem"],
  error: ["Something went wrong", "error"],
};

const PLUGIN_STATUS = {
  ok: ["Active", "done"], disabled: ["Off", ""], needs_approval: ["Needs approval", "warn"],
  changed: ["Changed – approve again", "warn"], incompatible: ["Not compatible", "warn"],
  invalid: ["Invalid", "failed"], no_sandbox: ["Sandbox unavailable", "failed"],
};

/* ------------------------------------------------------------------ helpers */
function human(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 ** 3) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 ** 3).toFixed(2)} GB`;
}
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function ago(ts) {
  const s = Math.max(0, Date.now() / 1000 - ts);
  if (s < 45) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(ts * 1000).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}
function get(path) { return path.split(".").reduce((o, k) => o?.[k], state.settings); }
function patchFor(path, value) { const [section, key] = path.split("."); return { [section]: { [key]: value } }; }
function debounce(fn, ms) { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; }

function toast(message, type = "ok", ms = 2600) {
  const el = document.createElement("div");
  el.className = `toast ${type}`;
  el.textContent = message;
  $("#toasts").append(el);
  setTimeout(() => { el.classList.add("out"); setTimeout(() => el.remove(), 300); }, ms);
}

function modal({ title, body, ok = "OK", cancel = "Cancel", danger = false }) {
  return new Promise(resolve => {
    $("#modal-title").textContent = title;
    $("#modal-body").innerHTML = body;
    const okBtn = $("#modal-ok"), cancelBtn = $("#modal-cancel");
    okBtn.textContent = ok;
    okBtn.className = `btn ${danger ? "danger" : "primary"}`;
    cancelBtn.textContent = cancel;
    cancelBtn.hidden = !cancel;
    $("#modal").hidden = false;
    okBtn.focus();
    const done = value => { $("#modal").hidden = true; okBtn.onclick = cancelBtn.onclick = null; document.onkeydown = null; resolve(value); };
    okBtn.onclick = () => done(true);
    cancelBtn.onclick = () => done(false);
    document.onkeydown = e => { if (e.key === "Escape") done(false); if (e.key === "Enter") done(true); };
  });
}

async function busy(button, fn) {
  button?.classList.add("busy");
  try { return await fn(); } finally { button?.classList.remove("busy"); }
}

/* ------------------------------------------------------------------ routing */
function showPage(name) {
  if (!$(`#page-${name}`)) name = "dashboard";
  $$(".page").forEach(p => p.classList.toggle("active", p.id === `page-${name}`));
  $$(".nav-item").forEach(a => a.classList.toggle("active", a.dataset.page === name));
  $("#content").scrollTop = 0;
  if (name === "plugins") loadPlugins();
}

/* ----------------------------------------------------------------- settings */
async function save(patch, quiet = false) {
  const res = await api().save_settings(patch);
  state.settings = res.settings;
  if (res.ok) { if (!quiet) toast("Saved"); }
  else toast(res.errors.join(" · "), "error", 4500);
  renderSettings();
  return res.ok;
}
const saveSoon = debounce(save, 350);

function bindSettings() {
  $$("[data-setting]").forEach(el => {
    const path = el.dataset.setting;
    if (el.classList.contains("segmented")) {
      $$("button", el).forEach(b => b.addEventListener("click", () => save(patchFor(path, b.dataset.value))));
    } else if (el.type === "checkbox") {
      el.addEventListener("change", () => save(patchFor(path, el.checked)));
    } else if (el.type === "range") {
      el.addEventListener("input", () => { el.nextElementSibling.textContent = el.value; saveSoon(patchFor(path, +el.value)); });
    } else if (el.tagName === "SELECT") {
      el.addEventListener("change", () => save(patchFor(path, el.dataset.type === "int" ? +el.value : el.value)));
    } else {
      el.addEventListener("change", () => save(patchFor(path, el.value)));
    }
  });

  // Target size: a switch + number feeding one setting (0 = off).
  const toggle = $("#target-toggle"), size = $("#target-size");
  toggle.addEventListener("change", () => save({ images: { target_size_kb: toggle.checked ? (+size.value || 200) : 0 } }));
  size.addEventListener("change", () => {
    const v = Math.round(+size.value);
    if (!(v >= 1)) { size.classList.add("invalid"); toast("Enter a size of at least 1 KB", "error"); return; }
    size.classList.remove("invalid");
    save({ images: { target_size_kb: v } });
  });
  $$("#target-presets button").forEach(b => b.addEventListener("click", () => save({ images: { target_size_kb: +b.dataset.kb } })));

  $$("#responsive-widths button").forEach(b => b.addEventListener("click", () => {
    const set = new Set(state.settings.images.responsive_widths);
    const w = +b.dataset.w;
    set.has(w) ? set.delete(w) : set.add(w);
    save({ images: { responsive_widths: [...set] } });
  }));
}

function renderSettings() {
  const s = state.settings;
  $$("[data-setting]").forEach(el => {
    const v = get(el.dataset.setting);
    if (el.classList.contains("segmented")) $$("button", el).forEach(b => b.classList.toggle("on", b.dataset.value === String(v)));
    else if (el.type === "checkbox") el.checked = !!v;
    else if (el.type === "range") { el.value = v; el.nextElementSibling.textContent = v; }
    else if (el.tagName === "SELECT") {
      if (![...el.options].some(o => o.value === String(v))) el.add(new Option(`${v}`, v));
      el.value = String(v);
    } else if (document.activeElement !== el) el.value = v;
  });

  const img = s.images;
  $("#target-toggle").checked = img.target_size_kb > 0;
  if (img.target_size_kb > 0) $("#target-size").value = img.target_size_kb;
  else if (!$("#target-size").value) $("#target-size").value = 200;
  $("#target-wrap").classList.toggle("disabled", img.target_size_kb === 0);
  $("#target-presets-row").hidden = img.target_size_kb === 0;
  $$("#target-presets button").forEach(b => b.classList.toggle("on", +b.dataset.kb === img.target_size_kb));
  $$("#responsive-widths button").forEach(b => b.classList.toggle("on", img.responsive_widths.includes(+b.dataset.w)));

  // Show only the controls that apply to the chosen format.
  $$("[data-show-format]").forEach(el => {
    el.hidden = !(img.format === "auto" || img.format === el.dataset.showFormat);
  });
  const help = FORMAT_HELP[img.format];
  $("#format-help").innerHTML = `<p>${esc(help.lead)}</p>` +
    help.pros.map(p => `<div class="pro">${esc(p)}</div>`).join("") + help.cons.map(c => `<div class="con">${esc(c)}</div>`).join("");
  $("#effort-hint").textContent = {
    fast: "Quicker, with slightly larger files.",
    balanced: "A good balance of speed and size (recommended).",
    best: "Slowest, smallest files. Makes the biggest difference for AVIF.",
  }[img.effort];

  $$("#page-images .card").forEach(c => c.classList.toggle("disabled-section", !img.enabled));
  $$("#page-documents .card").forEach(c => c.classList.toggle("disabled-section", !s.documents.enabled));

  const pills = imageSummary(img);
  $("#images-summary").innerHTML = pills.map(p => `<span>${esc(p)}</span>`).join("");
  $("#sum-images").textContent = img.enabled ? pills.slice(0, 3).join(" · ") : "Off";
  $("#sum-docs").textContent = s.documents.enabled ? `Markdown · up to ${s.documents.max_size_mb} MB` : "Off";

  const g = s.general;
  $("#watch-hint").innerHTML = g.watch_folder
    ? `<span class="mono">${esc(g.watch_folder)}</span>`
    : `Automatic: <span class="mono">${esc(state.status?.watch_folder || "")}</span> (~/Desktop/AirDrop if you sort AirDrops there, otherwise Downloads)`;
  $("#watch-auto").hidden = !g.watch_folder;
  const loginToggle = $('[data-setting="general.launch_at_login"]');
  loginToggle.disabled = !state.app.frozen;
  $("#login-hint").textContent = state.app.frozen
    ? "Starts quietly in the menu bar when you log in."
    : "Available in the installed app (you're running from source).";
}

function imageSummary(img) {
  const f = state.formats[img.format]?.label || "Auto";
  const q = { webp: img.webp_quality, avif: img.avif_quality, jpeg: img.jpeg_quality }[img.format];
  const out = [img.format === "auto" ? "Auto format (smallest)" : f];
  if (img.target_size_kb) out.push(`≤ ${img.target_size_kb >= 1000 ? (img.target_size_kb / 1000) + " MB" : img.target_size_kb + " KB"}`);
  else if (q) out.push(`quality ${q}`);
  out.push(img.max_dimension ? `max ${img.max_dimension} px` : "original size");
  if (img.responsive_widths.length) out.push(`${img.responsive_widths.length} responsive size${img.responsive_widths.length > 1 ? "s" : ""}`);
  out.push({ keep: "metadata kept", no_location: "location removed", strip: "metadata removed" }[img.metadata]);
  if (img.color === "srgb") out.push("sRGB");
  if (img.seo_filenames) out.push("SEO names");
  if (img.jpeg_fallback && img.format !== "jpeg") out.push("+ JPEG fallback");
  return out;
}

/* --------------------------------------------------------------- dashboard */
function renderStatus(status) {
  state.status = status;
  const [title, cls] = STATE_INFO[status.state] || [status.state, "problem"];
  for (const el of [$("#hero"), $("#status-mini")]) {
    el.className = el.className.replace(/\bstate-\S+/g, "").trim() + ` state-${cls}`;
  }
  $("#hero-title").textContent = title;
  $("#hero-folder").textContent = status.watch_folder.replace(/^\/Users\/[^/]+/, "~");
  $("#status-mini .label").textContent = title;
  const pauseBtn = $("#toggle-pause");
  const paused = status.paused;
  pauseBtn.textContent = paused ? "Resume" : "Pause";
  pauseBtn.className = `btn ${paused ? "primary" : ""}`;
  pauseBtn.disabled = ["legacy", "locked"].includes(status.state);

  const banners = [];
  if (status.state === "legacy") {
    banners.push({ cls: "warn", icon: ICON.warn, title: "The command-line version is still running",
      text: "Version 1's background service is installed. Running both would convert every file twice.",
      action: ["Switch to the app", "switch-legacy"] });
  } else if (status.state === "waiting_access") {
    banners.push({ cls: "warn", icon: ICON.warn, title: "macOS is blocking access to your AirDrop folder",
      text: "Open Privacy & Security, then allow AirDrop Compress under Files and Folders (or Full Disk Access). It continues automatically.",
      action: ["Open Privacy settings", "privacy"] });
  } else if (["locked", "error"].includes(status.state)) {
    banners.push({ cls: status.state === "error" ? "error" : "warn", icon: ICON.warn, title: title, text: status.message });
  }
  if (state.update?.available) {
    banners.push({ cls: "info", icon: ICON.info, title: `Version ${state.update.latest} is available`,
      text: `You have ${state.app.version}.`, action: ["Download", "update"] });
  }
  const html = banners.map(b => `<div class="banner ${b.cls}">${b.icon}<div class="banner-text"><b>${esc(b.title)}</b>${esc(b.text)}</div>` +
    (b.action ? `<button class="btn ${b.cls === "info" ? "primary" : ""}" data-banner="${b.action[1]}">${esc(b.action[0])}</button>` : "") + "</div>").join("");
  if ($("#banners").innerHTML !== html) $("#banners").innerHTML = html;
}

function renderStats(stats) {
  const t = stats.today, all = stats.total;
  $("#stat-today").textContent = t.files;
  $("#stat-today-sub").textContent = t.failed ? `${t.failed} failed` : (t.files === 1 ? "file" : "files");
  const saved = Math.max(0, t.before - t.after);
  $("#stat-saved").textContent = human(saved);
  $("#stat-saved-sub").textContent = t.before ? `${Math.round(saved / t.before * 100)}% smaller` : "nothing yet";
  $("#stat-total").textContent = human(Math.max(0, all.before - all.after));
  $("#stat-total-sub").textContent = `${all.files} file${all.files === 1 ? "" : "s"}`;
  $("#stat-busy").textContent = stats.busy;
}

function renderActivity() {
  const items = state.activity.filter(i => state.filter === "all" || i.status === state.filter);
  const list = $("#activity");
  if (!items.length) {
    list.innerHTML = `<div class="empty">${ICON.inbox}<strong>${state.filter === "all" ? "Nothing yet" : "Nothing here"}</strong>` +
      `${state.filter === "all" ? "AirDrop a photo or document to this Mac and it appears here." : "No files with this status."}</div>`;
    return;
  }
  list.innerHTML = items.map(i => {
    const label = { queued: "Queued", processing: "Converting", done: "Done", skipped: "Skipped", failed: "Failed" }[i.status];
    let detail = esc(i.message);
    let side = "";
    if (i.status === "done") {
      const outs = i.outputs.map((o, n) => n < 2 ? `<span class="out" data-reveal="${esc(o)}">${esc(o)}</span>` : "").join(", ");
      const more = i.outputs.length > 2 ? ` +${i.outputs.length - 2} more` : "";
      detail = `→ ${outs}${more}${i.message ? " · " + esc(i.message) : ""}`;
      const pct = i.before ? Math.round((1 - i.after / i.before) * 100) : 0;
      side = `<span class="saving">${human(i.before)} → ${human(i.after)}${i.kind === "image" && pct > 0 ? ` (−${pct}%)` : ""}</span>`;
    }
    return `<div class="item"><div class="item-icon ${i.kind}">${ICON[i.kind] || ICON.other}</div>` +
      `<div class="item-main"><div class="item-name" title="${esc(i.name)}">${esc(i.name)}</div><div class="item-detail" title="${esc(i.message)}">${detail || "&nbsp;"}</div></div>` +
      `<div class="item-side"><span class="badge ${i.status}">${label}</span>${side}<span class="item-time">${ago(i.finished || i.started)}</span></div></div>`;
  }).join("");
}

async function poll() {
  try {
    const res = await api().poll(state.revision);
    renderStatus(res.status);
    renderStats(res.stats);
    if (res.activity) { state.activity = res.activity; state.revision = res.revision; renderActivity(); }
  } catch (e) { console.error(e); }
}

/* ------------------------------------------------------------------ compare */
async function compare() {
  const res = await busy($("#compare-btn"), () => api().compare_formats());
  if (!res.ok) { if (res.error) toast(res.error, "error", 4500); return; }
  state.compare = res;
  renderCompare();
}

function renderCompare() {
  const res = state.compare;
  if (!res) return;
  const max = Math.max(...res.rows.map(r => r.size));
  $("#compare-result").innerHTML =
    `<table class="compare"><thead><tr><th>Format</th><th>Size</th><th style="width:30%"></th><th>vs original</th><th>Quality</th><th>Time</th><th></th></tr></thead><tbody>` +
    res.rows.map(r => {
      const pct = Math.round((1 - r.size / res.original) * 100);
      const current = state.settings.images.format === r.format;
      return `<tr class="${r.best ? "best" : ""}"><td><b>${r.label}</b>${r.best ? ' <span class="badge done">Smallest</span>' : ""}${r.note ? `<div class="row-hint">${esc(r.note)}</div>` : ""}</td>` +
        `<td>${human(r.size)}</td><td><div class="bar" style="width:${Math.max(2, r.size / max * 100)}%"></div></td>` +
        `<td>${pct >= 0 ? "−" + pct : "+" + -pct}%</td><td>${r.quality}</td><td>${r.ms < 1000 ? r.ms + " ms" : (r.ms / 1000).toFixed(1) + " s"}</td>` +
        `<td>${current ? '<span class="badge">In use</span>' : `<button class="btn subtle" data-use-format="${r.format}">Use</button>`}</td></tr>`;
    }).join("") + "</tbody></table>" +
    `<div class="compare-meta">${esc(res.name)} · ${res.width}×${res.height} · original ${human(res.original)}${res.has_alpha ? " · has transparency" : ""}${res.animated ? " · animated" : ""}</div>`;
}

/* ------------------------------------------------------------------ plugins */
async function loadPlugins(list) {
  state.plugins = list || await api().list_plugins();
  renderPlugins();
}

function renderPlugins() {
  const active = state.plugins.filter(p => p.status === "ok").length;
  $("#plugins-badge").hidden = !state.plugins.length;
  $("#plugins-badge").textContent = active ? `${active} on` : state.plugins.length;
  $("#sum-plugins").textContent = state.plugins.length ? `${active} of ${state.plugins.length} active` : "None installed";
  const box = $("#plugin-list");
  if (!state.plugins.length) {
    box.innerHTML = `<div class="card empty">${ICON.plugin}<strong>No plugins installed</strong>Install a plugin (.zip or folder) to support more file types. ` +
      `Try the example in <span class="mono">examples/plugins/svg-minify</span>.</div>`;
    return;
  }
  box.innerHTML = state.plugins.map(p => {
    const [label, cls] = PLUGIN_STATUS[p.status] || [p.status, ""];
    const perms = p.permissions.length
      ? p.permissions.map(k => `<span class="badge warn">${esc(p.permission_labels[k] || k)}</span>`).join("")
      : '<span class="badge">No special permissions</span>';
    const types = p.file_types.length ? `<span class="badge">${esc(p.file_types.join(" "))} → ${esc(p.outputs.join(" "))}</span>` : "";
    const problems = [...p.errors, p.incompatible].filter(Boolean);
    const canToggle = !p.errors.length && !p.incompatible;
    const needsReview = ["needs_approval", "changed"].includes(p.status);
    const settings = p.status === "ok" && p.settings.length ? `<div class="plugin-settings">${p.settings.map(s => pluginSetting(p, s)).join("")}</div>` : "";
    return `<div class="card plugin" data-plugin="${esc(p.id)}"><div class="plugin-icon">${ICON.plugin}</div><div>` +
      `<div class="plugin-name">${esc(p.name)} <span class="badge ${cls}">${label}</span></div>` +
      `<div class="plugin-meta">v${esc(p.version)}${p.author ? " · " + esc(p.author) : ""} · <span class="mono">${esc(p.id)}</span></div>` +
      (p.description ? `<p class="plugin-desc">${esc(p.description)}</p>` : "") +
      `<div class="plugin-tags">${types}${perms}</div>` +
      (problems.length ? `<ul class="plugin-errors">${problems.map(e => `<li>${esc(e)}</li>`).join("")}</ul>` : "") +
      `</div><div class="plugin-actions">` +
      (canToggle ? `<label class="switch" title="Turn on/off"><input type="checkbox" data-plugin-toggle ${p.status === "ok" ? "checked" : ""}><span></span></label>` : "") +
      (needsReview ? `<button class="btn primary" data-plugin-approve>Review…</button>` : "") +
      (p.homepage ? `<button class="btn subtle" data-url="${esc(p.homepage)}">Website</button>` : "") +
      `<button class="btn subtle danger-text" data-plugin-remove>Remove</button></div>${settings}</div>`;
  }).join("");
}

function pluginSetting(p, s) {
  const v = p.values[s.key];
  let control;
  if (s.type === "bool") control = `<label class="switch"><input type="checkbox" data-plugin-setting="${esc(s.key)}" ${v ? "checked" : ""}><span></span></label>`;
  else if (s.type === "choice") control = `<select data-plugin-setting="${esc(s.key)}">${s.options.map(o => `<option ${o === v ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>`;
  else if (s.type === "int") control = `<div class="input-unit"><input type="number" data-plugin-setting="${esc(s.key)}" data-type="int" value="${esc(v)}" ${s.min !== undefined ? `min="${esc(s.min)}"` : ""} ${s.max !== undefined ? `max="${esc(s.max)}"` : ""}></div>`;
  else control = `<input type="text" class="text" data-plugin-setting="${esc(s.key)}" value="${esc(v)}">`;
  return `<div class="row"><div class="row-text"><div class="row-title">${esc(s.label || s.key)}</div>${s.help ? `<div class="row-hint">${esc(s.help)}</div>` : ""}</div>${control}</div>`;
}

async function approvePlugin(p) {
  const allowed = p.permissions.map(k => `<li class="allow">${esc(p.permission_labels[k] || k)}</li>`).join("");
  const denied = ["Read or change your other files", "Read this app's settings and history"]
    .concat(p.permissions.includes("network") ? [] : ["Connect to the internet"])
    .concat(p.permissions.includes("subprocess") ? [] : ["Run other programs"])
    .map(t => `<li class="deny">${t}</li>`).join("");
  const changed = p.status === "changed" ? "<p><b>This plugin's files changed since you approved it.</b> Only continue if you updated it yourself.</p>" : "";
  const ok = await modal({
    title: `Turn on ${p.name}?`, ok: "Turn on",
    body: `${changed}<p>It will convert <b>${esc(p.file_types.join(", "))}</b> files you receive.</p>` +
      (allowed ? `<p>It asks to:</p><ul class="perm-list">${allowed}</ul>` : "") +
      `<p>It can never:</p><ul class="perm-list">${denied}</ul>`,
  });
  if (!ok) { renderPlugins(); return; }
  const res = await api().enable_plugin(p.id);
  loadPlugins(res.plugins);
  res.ok ? toast(`${p.name} is on`) : toast(res.error, "error", 4500);
}

async function installPlugin(fromFolder) {
  let res = await api().install_plugin(fromFolder, false);
  if (res.exists && await modal({ title: "Replace the installed plugin?", body: `<p>${esc(res.error)}. Replacing it switches it off until you approve the new version.</p>`, ok: "Replace" })) {
    res = await api().install_plugin_path(res.source, true);
  }
  if (res.ok) { loadPlugins(res.plugins); toast(`Installed ${res.name}. Turn it on to use it.`); }
  else if (res.error && !res.exists) toast(res.error, "error", 6000);
}

/* -------------------------------------------------------------------- about */
async function checkUpdates(force) {
  const box = $("#update-result");
  box.innerHTML = '<span class="badge processing">Checking…</span>';
  const info = await api().check_updates(force);
  state.update = info;
  $("#update-badge").hidden = !info.available;
  if (info.error) box.innerHTML = `<span class="badge failed">${esc(info.error)}</span>`;
  else if (info.available) box.innerHTML = `<span class="badge warn">Version ${esc(info.latest)} is available</span> <button class="btn primary" data-banner="update">Download</button>`;
  else box.innerHTML = `<span class="badge done">You're up to date</span>${info.note ? `<div class="row-hint">${esc(info.note)}</div>` : ""}`;
}

/* --------------------------------------------------------------------- init */
function bindActions() {
  $$(".nav-item").forEach(a => a.addEventListener("click", e => { e.preventDefault(); history.replaceState(null, "", `#${a.dataset.page}`); showPage(a.dataset.page); }));
  $$("[data-goto]").forEach(el => el.addEventListener("click", () => {
    showPage(el.dataset.goto);
    if (el.dataset.scroll) setTimeout(() => document.getElementById(el.dataset.scroll)?.scrollIntoView({ behavior: "smooth" }), 50);
  }));

  document.addEventListener("click", async e => {
    const t = e.target.closest("button, [data-reveal], [data-open]");
    if (!t) return;
    if (t.dataset.open) api().open_folder(t.dataset.open);
    if (t.dataset.contact) { api().contact(t.dataset.contact); toast("Opening your email app…", "info"); }
    if (t.dataset.url) api().open_url(t.dataset.url);
    if (t.dataset.reveal) api().reveal_output(t.dataset.reveal);
    if (t.dataset.useFormat) { await save({ images: { format: t.dataset.useFormat } }); renderCompare(); }
    if (t.dataset.reset) {
      const all = t.dataset.reset === "all";
      if (await modal({ title: all ? "Reset all settings?" : "Reset image settings?", body: "<p>Settings go back to their defaults. Your files and plugins aren't affected.</p>", ok: "Reset", danger: true })) {
        const res = await api().reset_settings(all ? null : t.dataset.reset);
        state.settings = res.settings; renderSettings(); toast("Settings reset");
      }
    }
    const banner = t.dataset.banner;
    if (banner === "switch-legacy") { await busy(t, () => api().remove_legacy_service()); toast("Switched to the app - the command-line service was removed"); poll(); }
    if (banner === "privacy") api().open_privacy_settings();
    if (banner === "update" && state.update?.url) api().open_url(state.update.url);

    const card = t.closest("[data-plugin]");
    if (card) {
      const p = state.plugins.find(x => x.id === card.dataset.plugin);
      if (t.hasAttribute("data-plugin-approve")) approvePlugin(p);
      if (t.hasAttribute("data-plugin-remove") && await modal({ title: `Remove ${p.name}?`, body: "<p>The plugin is deleted. Files it already created stay.</p>", ok: "Remove", danger: true })) {
        const res = await api().remove_plugin(p.id);
        res.ok ? (loadPlugins(res.plugins), toast(`Removed ${p.name}`)) : toast(res.error, "error");
      }
    }
  });

  document.addEventListener("change", async e => {
    const card = e.target.closest("[data-plugin]");
    if (!card) return;
    const p = state.plugins.find(x => x.id === card.dataset.plugin);
    if (e.target.hasAttribute("data-plugin-toggle")) {
      if (e.target.checked) approvePlugin(p);
      else { const res = await api().disable_plugin(p.id); loadPlugins(res.plugins); toast(`${p.name} is off`); }
    }
    const key = e.target.dataset.pluginSetting;
    if (key) {
      const v = e.target.type === "checkbox" ? e.target.checked : e.target.dataset.type === "int" ? Math.round(+e.target.value) : e.target.value;
      const res = await api().save_plugin_settings(p.id, { [key]: v });
      res.ok ? toast("Saved") : toast(res.error, "error");
      loadPlugins(res.plugins);
    }
  });

  $("#toggle-pause").addEventListener("click", async e => {
    const paused = state.status?.paused;
    const status = await busy(e.currentTarget, () => paused ? api().resume() : api().pause());
    renderStatus(status);
    toast(paused ? "Watching for AirDrop files" : "Paused - new files won't be processed", "info");
    setTimeout(poll, 800);
  });
  $("#choose-files").addEventListener("click", () => window.convertFiles());
  $("#compare-btn").addEventListener("click", compare);
  $("#watch-choose").addEventListener("click", async () => { const r = await api().choose_watch_folder(); if (r.ok) { state.settings = r.settings; renderSettings(); toast("Now watching the new folder"); setTimeout(poll, 1500); } else if (r.errors) toast(r.errors.join(" · "), "error"); });
  $("#watch-auto").addEventListener("click", async () => { await save({ general: { watch_folder: "" } }); setTimeout(poll, 1500); });
  $("#scan-btn").addEventListener("click", async e => {
    const res = await busy(e.currentTarget, () => api().scan_existing());
    if (!res.ok) toast(res.error, "error");
    else toast(res.count ? `Processing ${res.count} file${res.count === 1 ? "" : "s"} - see the Dashboard` : "Nothing to process", "info");
  });
  $("#clear-history").addEventListener("click", async () => {
    if (!await modal({ title: "Clear conversion history?", body: "<p>The activity list and statistics are cleared, and files you receive again will be converted again. Converted files aren't deleted.</p>", ok: "Clear", danger: true })) return;
    const res = await api().clear_history();
    state.activity = []; renderActivity(); state.historyCount = 0; renderHistoryHint();
    toast(`Cleared ${res.count} record${res.count === 1 ? "" : "s"}`);
    poll();
  });
  $("#install-zip").addEventListener("click", () => installPlugin(false));
  $("#install-folder").addEventListener("click", () => installPlugin(true));
  $("#check-updates").addEventListener("click", () => checkUpdates(true));
  $("#open-privacy").addEventListener("click", () => api().open_privacy_settings());
  $("#uninstall").addEventListener("click", async () => {
    if (!await modal({ title: "Uninstall AirDrop Compress?", danger: true, ok: "Uninstall",
      body: "<p>This removes the app, its login item, settings, history, plugins and log, then quits.</p><p><b>Your original files and everything in the output folder are kept.</b></p>" })) return;
    const res = await api().uninstall();
    await modal({ title: "AirDrop Compress was removed", cancel: null, ok: "Close",
      body: res.trashed ? "<p>The app was moved to the Trash. Thanks for using it!</p>" : "<p>Your data was removed. Drag the app to the Trash to finish.</p>" });
  });
  $$("#activity-filter button").forEach(b => b.addEventListener("click", () => {
    state.filter = b.dataset.value;
    $$("#activity-filter button").forEach(x => x.classList.toggle("on", x === b));
    renderActivity();
  }));

  // Drop zone highlight (the drop itself is handled natively, which gives full file paths).
  let depth = 0;
  document.addEventListener("dragenter", e => { e.preventDefault(); depth++; $("#dropzone").classList.add("over"); });
  document.addEventListener("dragleave", () => { if (--depth <= 0) { depth = 0; $("#dropzone").classList.remove("over"); } });
  document.addEventListener("dragover", e => e.preventDefault());
  document.addEventListener("drop", e => { e.preventDefault(); depth = 0; $("#dropzone").classList.remove("over"); showPage("dashboard"); });
}

function renderHistoryHint() {
  $("#history-hint").textContent = `${state.historyCount} file${state.historyCount === 1 ? "" : "s"} remembered, so the same file is never converted twice.`;
}

window.convertFiles = async () => {
  showPage("dashboard");
  const res = await api().convert_files();
  window.onFilesDropped(res);
};
window.onFilesDropped = res => {
  if (res.error) toast(res.error, "error");
  else if (res.count) toast(`Converting ${res.count} file${res.count === 1 ? "" : "s"}${res.unsupported ? ` (${res.unsupported} not supported)` : ""}`, "info");
  else if (res.unsupported) toast("Those files aren't supported", "error");
  setTimeout(poll, 300);
};

async function init() {
  const data = await api().bootstrap();
  Object.assign(state, { settings: data.settings, schema: data.schema, app: data.app, formats: data.formats,
                         plugins: data.plugins, update: data.update, historyCount: data.history_count });
  $("#brand-version").textContent = `Version ${data.app.version}`;
  $("#about-version").textContent = `Version ${data.app.version}${data.app.frozen ? "" : " (running from source)"}`;
  $("#about-support").textContent = data.app.support_dir;
  $("#about-log").textContent = data.app.log_file;
  $("#author-name").textContent = data.app.author;
  $("#author-links").innerHTML = Object.entries(data.app.author_links)
    .map(([name, url]) => `<button class="btn subtle" data-url="${esc(url)}">${esc(name)}</button>`).join("") +
    `<button class="btn subtle" data-url="${esc(data.app.website)}">Website</button>`;
  $("#types-documents").innerHTML = data.file_types.documents.map(t => `<span>${esc(t)}</span>`).join("");
  $("#types-legacy").innerHTML = data.file_types.legacy_documents.map(t => `<span>${esc(t)}</span>`).join("");
  $("#types-code").innerHTML = data.file_types.code.map(t => `<span>${esc(t)}</span>`).join("");
  renderStatus(data.status);
  renderStats(data.stats);
  state.activity = data.activity || []; state.revision = data.revision;
  renderActivity();
  renderSettings();
  renderPlugins();
  renderHistoryHint();
  bindSettings();
  bindActions();
  showPage(location.hash.slice(1) || "dashboard");
  setInterval(poll, 1000);
  setInterval(renderActivity, 30000); // refresh "x min ago"
  if (data.settings.general.check_for_updates) setTimeout(() => checkUpdates(false), 3000);
}

window.addEventListener("pywebviewready", init);
