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
