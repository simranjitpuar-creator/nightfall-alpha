/* ============================================================
   NightFall Alpha — Theme, customization & motion controller
   ============================================================ */
(function () {
  const STORE_KEY = "pw-theme";
  const root = document.documentElement;

  const DEFAULTS = {
    "--accent": "#6366f1",
    "--accent-2": "#22d3ee",
    "--gain": "#34d399",
    "--loss": "#fb7185",
  };

  const PRESETS = [
    { name: "indigo", label: "Indigo", accent: "#6366f1", accent2: "#22d3ee" },
    { name: "violet", label: "Violet", accent: "#8b5cf6", accent2: "#ec4899" },
    { name: "emerald", label: "Emerald", accent: "#10b981", accent2: "#a3e635" },
    { name: "teal", label: "Teal", accent: "#0ea5a8", accent2: "#38bdf8" },
    { name: "amber", label: "Amber", accent: "#f59e0b", accent2: "#f43f5e" },
    { name: "rose", label: "Rose", accent: "#f43f5e", accent2: "#fb923c" },
    { name: "sky", label: "Sky", accent: "#0ea5e9", accent2: "#6366f1" },
    { name: "lime", label: "Lime", accent: "#84cc16", accent2: "#22d3ee" },
  ];

  const COLOR_FIELDS = [
    { var: "--accent", name: "Primary accent" },
    { var: "--accent-2", name: "Secondary accent" },
    { var: "--gain", name: "Gain / up" },
    { var: "--loss", name: "Loss / down" },
  ];

  // ---------- state ----------
  function load() {
    try {
      return JSON.parse(localStorage.getItem(STORE_KEY) || "{}");
    } catch (e) {
      return {};
    }
  }

  const state = Object.assign(
    { mode: "dark", vars: {}, accentName: "indigo", collapsed: false, aurora: true, motion: true },
    load()
  );

  function save() {
    localStorage.setItem(STORE_KEY, JSON.stringify(state));
  }

  // ---------- helpers ----------
  function hexToRgb(hex) {
    const m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex || "");
    if (!m) return "99, 102, 241";
    return `${parseInt(m[1], 16)}, ${parseInt(m[2], 16)}, ${parseInt(m[3], 16)}`;
  }

  function currentVar(name) {
    return state.vars[name] || DEFAULTS[name];
  }

  function applyVars() {
    Object.entries(state.vars).forEach(([k, v]) => root.style.setProperty(k, v));
    // keep --accent-rgb in sync with the accent hex
    const accent = currentVar("--accent");
    root.style.setProperty("--accent-rgb", hexToRgb(accent));
  }

  function redrawCharts() {
    if (typeof window.renderCurves === "function") {
      window.requestAnimationFrame(() => window.renderCurves());
    }
  }

  function applyAll() {
    root.setAttribute("data-theme", state.mode);
    root.setAttribute("data-aurora", state.aurora ? "on" : "off");
    root.setAttribute("data-motion", state.motion ? "on" : "off");
    if (state.collapsed) root.setAttribute("data-sidebar", "collapsed");
    else root.removeAttribute("data-sidebar");
    applyVars();
    redrawCharts();
  }

  // ---------- actions ----------
  function setMode(mode) {
    state.mode = mode;
    save();
    applyAll();
    syncUI();
  }

  function setVar(name, value) {
    state.vars[name] = value;
    state.accentName = null; // custom edit clears preset highlight
    save();
    applyVars();
    redrawCharts();
    syncUI();
  }

  function applyPreset(preset) {
    state.vars["--accent"] = preset.accent;
    state.vars["--accent-2"] = preset.accent2;
    state.accentName = preset.name;
    save();
    applyVars();
    redrawCharts();
    syncUI();
  }

  function resetTheme() {
    state.vars = {};
    state.accentName = "indigo";
    Object.keys(DEFAULTS).forEach((k) => root.style.removeProperty(k));
    root.style.removeProperty("--accent-rgb");
    save();
    applyAll();
    syncUI();
    toast("Palette reset to defaults");
  }

  function toggleCollapse() {
    state.collapsed = !state.collapsed;
    save();
    applyAll();
    redrawCharts();
  }

  function toast(message) {
    if (typeof window.toast === "function") return window.toast(message);
    const node = document.getElementById("toast");
    if (!node) return;
    node.textContent = message;
    node.classList.add("show");
    setTimeout(() => node.classList.remove("show"), 2200);
  }

  // ---------- build settings UI ----------
  function buildSwatches() {
    const host = document.getElementById("presetSwatches");
    if (!host) return;
    host.innerHTML = "";
    PRESETS.forEach((preset) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "swatch";
      btn.dataset.preset = preset.name;
      btn.title = preset.label;
      btn.style.background = `linear-gradient(135deg, ${preset.accent}, ${preset.accent2})`;
      btn.style.color = preset.accent;
      btn.addEventListener("click", () => applyPreset(preset));
      host.appendChild(btn);
    });
  }

  function buildColorFields() {
    const host = document.getElementById("colorGrid");
    if (!host) return;
    host.innerHTML = "";
    COLOR_FIELDS.forEach((field) => {
      const wrap = document.createElement("label");
      wrap.className = "color-field";
      const value = currentVar(field.var);
      wrap.innerHTML = `
        <input type="color" value="${value}" data-var="${field.var}" />
        <span class="cf-text">
          <span class="cf-name">${field.name}</span>
          <span class="cf-hex" data-hex="${field.var}">${value}</span>
        </span>`;
      const input = wrap.querySelector("input");
      input.addEventListener("input", (e) => {
        const v = e.target.value;
        wrap.querySelector("[data-hex]").textContent = v;
        setVar(field.var, v);
      });
      host.appendChild(wrap);
    });
  }

  // ---------- sync controls to state ----------
  function syncUI() {
    document.querySelectorAll("#modeSeg .seg-btn").forEach((b) => {
      b.classList.toggle("active", b.dataset.mode === state.mode);
    });
    document.querySelectorAll("#presetSwatches .swatch").forEach((s) => {
      s.classList.toggle("active", s.dataset.preset === state.accentName);
    });
    document.querySelectorAll("#colorGrid input[type=color]").forEach((input) => {
      const v = currentVar(input.dataset.var);
      input.value = v;
      const hex = input.parentElement.querySelector("[data-hex]");
      if (hex) hex.textContent = v;
    });
    const aurora = document.getElementById("toggleAurora");
    const motion = document.getElementById("toggleMotion");
    if (aurora) aurora.checked = state.aurora;
    if (motion) motion.checked = state.motion;
  }

  // ---------- wire up ----------
  function init() {
    applyAll();
    buildSwatches();
    buildColorFields();
    if (typeof window.decorateHelpTargets === "function") window.decorateHelpTargets();
    syncUI();

    const toggle = document.getElementById("themeToggle");
    if (toggle) toggle.addEventListener("click", () => {
      setMode(state.mode === "dark" ? "light" : "dark");
    });

    const collapse = document.getElementById("collapseButton");
    if (collapse) collapse.addEventListener("click", toggleCollapse);

    const customize = document.getElementById("customizeButton");
    if (customize) customize.addEventListener("click", () => {
      if (typeof window.activateTab === "function") window.activateTab("settings");
    });

    document.querySelectorAll("#modeSeg .seg-btn").forEach((b) => {
      b.addEventListener("click", () => setMode(b.dataset.mode));
    });

    const reset = document.getElementById("resetTheme");
    if (reset) reset.addEventListener("click", resetTheme);

    const aurora = document.getElementById("toggleAurora");
    if (aurora) aurora.addEventListener("change", (e) => {
      state.aurora = e.target.checked;
      save();
      root.setAttribute("data-aurora", state.aurora ? "on" : "off");
    });

    const motion = document.getElementById("toggleMotion");
    if (motion) motion.addEventListener("change", (e) => {
      state.motion = e.target.checked;
      save();
      root.setAttribute("data-motion", state.motion ? "on" : "off");
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
