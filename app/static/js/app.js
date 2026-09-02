// Shared helpers used by every page.

async function api(path, options = {}) {
  const opts = Object.assign({ credentials: "same-origin" }, options);
  opts.headers = Object.assign({}, options.headers);
  if (opts.body && !(opts.body instanceof FormData)) {
    opts.headers["Content-Type"] = "application/json";
  }
  const resp = await fetch(path, opts);
  if (resp.status === 401) {
    if (!location.pathname.endsWith("/login.html")) {
      location.href = "/login.html";
    }
    throw new Error("unauthenticated");
  }
  return resp;
}

async function apiJson(path, options = {}) {
  const resp = await api(path, options);
  const data = await resp.json().catch(() => null);
  if (!resp.ok) {
    const detail = (data && data.detail) || `Erreur ${resp.status}`;
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return data;
}

async function requireAuth() {
  try {
    await apiJson("/api/auth/me");
  } catch (e) {
    // apiJson already redirects on 401
  }
}

async function logout() {
  await api("/api/auth/logout", { method: "POST" });
  location.href = "/login.html";
}

function fmtBytes(bytes) {
  if (bytes === 0) return "0 o";
  const units = ["o", "Ko", "Mo", "Go", "To"];
  const i = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, i)).toFixed(1)} ${units[i]}`;
}

function statusLabel(state) {
  const labels = {
    running: "En ligne",
    starting: "Demarrage...",
    error: "Erreur",
    stopped: "Arretee",
    disabled: "Desactivee",
  };
  return labels[state] || state;
}

let _toastTimer = null;
function toast(message) {
  let node = document.getElementById("toast");
  if (!node) {
    node = document.createElement("div");
    node.id = "toast";
    node.className = "toast";
    document.body.appendChild(node);
  }
  node.textContent = message;
  node.classList.add("show");
  clearTimeout(_toastTimer);
  _toastTimer = setTimeout(() => node.classList.remove("show"), 2200);
}

// Zero-padded local date/time helpers. The server's recording filenames
// and lookups are all in server-local wall-clock time (ffmpeg's
// `-strftime 1`), so timestamps built here deliberately avoid UTC/ISO
// conversion - they're plain "YYYY-MM-DD" / "HH:MM:SS" local strings.
function pad2(n) { return String(n).padStart(2, "0"); }
function localDateStr(d) { return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`; }
function localTimeStr(d) { return `${pad2(d.getHours())}:${pad2(d.getMinutes())}:${pad2(d.getSeconds())}`; }

function el(tag, attrs = {}, children = []) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on") && typeof v === "function") node.addEventListener(k.slice(2), v);
    else if (v !== null && v !== undefined) node.setAttribute(k, v);
  }
  for (const child of [].concat(children)) {
    if (child === null || child === undefined) continue;
    node.appendChild(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

// --- Camera setup helpers: known RTSP URL patterns per brand, and ONVIF
// discovery (works for any ONVIF-compliant camera, which covers virtually
// every brand below plus many more). ---

const CAMERA_BRANDS = {
  hikvision: {
    label: "Hikvision",
    defaultPort: 554,
    hint: "Chemin standard Hikvision (chaine/sous-flux 101/102 par canal).",
    build: (v) => `rtsp://${v.user}:${v.pass}@${v.host}:${v.port}/Streaming/Channels/${v.channel}0${v.sub ? "2" : "1"}`,
  },
  uniview: {
    label: "Uniview",
    defaultPort: 554,
    hint: "Chemin standard Uniview pour une camera IP en connexion directe.",
    build: (v) => `rtsp://${v.user}:${v.pass}@${v.host}:${v.port}/media/video${v.sub ? "2" : "1"}`,
  },
  dahua: {
    label: "Dahua",
    defaultPort: 554,
    hint: "Chemin standard Dahua (subtype 0=principal, 1=secondaire).",
    build: (v) => `rtsp://${v.user}:${v.pass}@${v.host}:${v.port}/cam/realmonitor?channel=${v.channel}&subtype=${v.sub ? "1" : "0"}`,
  },
  axis: {
    label: "Axis",
    defaultPort: 554,
    hint: "Chemin standard Axis Media Control.",
    build: (v) => `rtsp://${v.user}:${v.pass}@${v.host}:${v.port}/axis-media/media.amp`,
  },
  reolink: {
    label: "Reolink",
    defaultPort: 554,
    hint: "Chemin standard Reolink.",
    build: (v) => `rtsp://${v.user}:${v.pass}@${v.host}:${v.port}/h264Preview_${String(v.channel).padStart(2, "0")}_${v.sub ? "sub" : "main"}`,
  },
};

// A brand + fields helper that builds a ready-to-use RTSP URL. These are
// the commonly documented defaults for each brand - firmware/model
// variations exist, so when in doubt prefer the ONVIF detection panel
// below, which asks the camera directly instead of guessing.
function buildBrandUrlWidget({ onUseUrl, onUseLiveUrl }) {
  const brandSelect = el("select", {}, [
    el("option", { value: "" }, "Choisir une marque..."),
    ...Object.entries(CAMERA_BRANDS).map(([key, b]) => el("option", { value: key }, b.label)),
  ]);
  const hostInput = el("input", { type: "text", placeholder: "192.168.1.50" });
  const portInput = el("input", { type: "text", inputmode: "numeric", placeholder: "554" });
  const userInput = el("input", { type: "text", placeholder: "admin" });
  const passInput = el("input", { type: "password", placeholder: "mot de passe" });
  const channelInput = el("input", { type: "text", inputmode: "numeric", value: "1", style: "width:70px" });
  const subCk = el("input", { type: "checkbox" });
  const hintEl = el("div", { class: "hint" });
  const previewEl = el("div", { class: "hint tabular", style: "word-break:break-all;color:var(--text-dim)" });

  function currentUrl() {
    const key = brandSelect.value;
    const brand = CAMERA_BRANDS[key];
    if (!brand || !hostInput.value) return "";
    return brand.build({
      host: hostInput.value.trim(),
      port: portInput.value.trim() || brand.defaultPort,
      user: userInput.value.trim() || "admin",
      pass: passInput.value,
      channel: channelInput.value.trim() || "1",
      sub: subCk.checked,
    });
  }
  function refresh() {
    const brand = CAMERA_BRANDS[brandSelect.value];
    hintEl.textContent = brand ? brand.hint : "";
    if (brand && !portInput.value) portInput.setAttribute("placeholder", String(brand.defaultPort));
    const url = currentUrl();
    previewEl.textContent = url ? `URL generee : ${url}` : "";
  }
  [brandSelect, hostInput, portInput, userInput, passInput, channelInput, subCk].forEach((elm) =>
    elm.addEventListener("input", refresh));
  brandSelect.addEventListener("change", refresh);

  const useMainBtn = el("button", { type: "button", class: "btn secondary", onclick: () => {
    const url = currentUrl();
    if (!url) { toast("Choisissez une marque et une adresse IP"); return; }
    onUseUrl(url);
  }}, "Utiliser pour le flux principal");
  const useLiveBtn = el("button", { type: "button", class: "btn secondary", onclick: () => {
    const url = currentUrl();
    if (!url) { toast("Choisissez une marque et une adresse IP"); return; }
    onUseLiveUrl(url);
  }}, "Utiliser pour le flux secondaire");

  return el("div", { class: "card field-grid" }, [
    el("div", { class: "section-title", style: "margin:0" }, "Assistant d'URL par marque"),
    el("div", {}, [ el("label", {}, "Marque"), brandSelect ]),
    el("div", { class: "row" }, [
      el("div", { style: "flex:2" }, [ el("label", {}, "Adresse IP"), hostInput ]),
      el("div", { style: "flex:1" }, [ el("label", {}, "Port"), portInput ]),
    ]),
    el("div", { class: "row" }, [
      el("div", {}, [ el("label", {}, "Utilisateur"), userInput ]),
      el("div", {}, [ el("label", {}, "Mot de passe"), passInput ]),
    ]),
    el("div", { class: "row", style: "align-items:flex-end" }, [
      el("div", { style: "flex:0" }, [ el("label", {}, "Canal"), channelInput ]),
      el("div", { class: "checkbox-row", style: "padding-bottom:10px" }, [ subCk, el("label", {}, "Sous-flux (basse resolution)") ]),
    ]),
    hintEl,
    previewEl,
    el("div", { style: "display:flex;gap:8px;flex-wrap:wrap;margin-top:4px" }, [useMainBtn, useLiveBtn]),
  ]);
}

// ONVIF-based discovery: asks the camera itself for its stream URL(s)
// instead of guessing a brand pattern. Works across brands since it's a
// standard protocol (Hikvision, Uniview, Dahua, Axis, Reolink, ...).
function buildOnvifDiscoveryWidget({ onUseUrl }) {
  const urlInput = el("input", { type: "text", placeholder: "http://192.168.1.50:8080/onvif/device_service" });
  const userInput = el("input", { type: "text", placeholder: "admin" });
  const passInput = el("input", { type: "password", placeholder: "mot de passe" });
  const errorEl = el("div", { class: "error-msg" });
  const resultsEl = el("div", { style: "display:flex;flex-direction:column;gap:6px;margin-top:8px" });

  async function probe() {
    errorEl.textContent = "";
    resultsEl.innerHTML = "";
    if (!urlInput.value.trim()) { errorEl.textContent = "URL ONVIF requise"; return; }
    resultsEl.appendChild(el("div", { class: "hint" }, "Interrogation de la camera..."));
    try {
      const profiles = await apiJson("/api/onvif/probe", {
        method: "POST",
        body: JSON.stringify({ onvif_url: urlInput.value.trim(), username: userInput.value, password: passInput.value }),
      });
      resultsEl.innerHTML = "";
      profiles.forEach((p) => {
        resultsEl.appendChild(el("div", { class: "rec-item" }, [
          el("span", {}, `${p.name}${p.resolution ? " · " + p.resolution : ""}`),
          p.stream_uri
            ? el("button", { type: "button", class: "btn secondary", onclick: () => onUseUrl(p.stream_uri) }, "Utiliser")
            : el("span", { class: "hint" }, "URL indisponible"),
        ]));
      });
    } catch (e) {
      resultsEl.innerHTML = "";
      errorEl.textContent = e.message;
    }
  }

  async function scanNetwork() {
    errorEl.textContent = "";
    resultsEl.innerHTML = "";
    resultsEl.appendChild(el("div", { class: "hint" }, "Recherche sur le reseau local (quelques secondes)..."));
    try {
      const devices = await apiJson("/api/onvif/discover", { method: "POST" });
      resultsEl.innerHTML = "";
      if (devices.length === 0) {
        resultsEl.appendChild(el("div", { class: "hint" }, "Aucune camera ONVIF trouvee sur le reseau local."));
        return;
      }
      devices.forEach((d) => {
        const xaddr = d.xaddrs && d.xaddrs[0];
        const nameScope = (d.scopes || []).find((s) => s.includes("/name/"));
        const label = nameScope ? decodeURIComponent(nameScope.split("/name/")[1] || "") : (xaddr || d.address);
        resultsEl.appendChild(el("div", { class: "rec-item" }, [
          el("span", {}, label),
          xaddr
            ? el("button", { type: "button", class: "btn secondary", onclick: () => { urlInput.value = xaddr; toast("URL ONVIF renseignee, cliquez sur Detecter les flux"); } }, "Utiliser")
            : null,
        ]));
      });
    } catch (e) {
      resultsEl.innerHTML = "";
      errorEl.textContent = e.message;
    }
  }

  return el("div", { class: "card field-grid" }, [
    el("div", { class: "section-title", style: "margin:0" }, "Detection ONVIF"),
    el("div", { class: "hint", style: "margin-bottom:8px" }, "Fonctionne avec toute camera compatible ONVIF (Hikvision, Uniview, Dahua, Axis, Reolink, ...) - interroge la camera directement plutot que de deviner l'URL."),
    el("div", {}, [ el("label", {}, "URL du service ONVIF"), urlInput ]),
    el("div", { class: "row" }, [
      el("div", {}, [ el("label", {}, "Utilisateur"), userInput ]),
      el("div", {}, [ el("label", {}, "Mot de passe"), passInput ]),
    ]),
    el("div", { style: "display:flex;gap:8px;flex-wrap:wrap" }, [
      el("button", { type: "button", class: "btn secondary", onclick: probe }, "Detecter les flux"),
      el("button", { type: "button", class: "btn secondary", onclick: scanNetwork }, "Rechercher sur le reseau"),
    ]),
    errorEl,
    resultsEl,
  ]);
}

function attachHls(videoEl, src, onFatalError) {
  if (videoEl.canPlayType("application/vnd.apple.mpegurl")) {
    videoEl.src = src;
    return null;
  }
  if (window.Hls && Hls.isSupported()) {
    const hls = new Hls({ liveSyncDurationCount: 3, maxLiveSyncPlaybackRate: 1.2 });
    let consecutiveFatal = 0;
    let recoverTimer = null;
    hls.on(Hls.Events.FRAG_BUFFERED, () => { consecutiveFatal = 0; });
    hls.on(Hls.Events.ERROR, (event, data) => {
      if (!data.fatal) return;
      consecutiveFatal += 1;
      // A camera's stream can briefly hiccup (segment rotated out just as we
      // asked for it, a short network blip...) - hls.js's own recovery
      // handles that. Only surface "offline" once retries keep failing.
      if (consecutiveFatal <= 4) {
        if (data.type === Hls.ErrorTypes.NETWORK_ERROR) {
          clearTimeout(recoverTimer);
          recoverTimer = setTimeout(() => hls.startLoad(), 1000);
          return;
        }
        if (data.type === Hls.ErrorTypes.MEDIA_ERROR) {
          hls.recoverMediaError();
          return;
        }
      }
      if (onFatalError) onFatalError(data);
    });
    hls.loadSource(src);
    hls.attachMedia(videoEl);
    return hls;
  }
  if (onFatalError) onFatalError({ details: "hls_unsupported" });
  return null;
}
