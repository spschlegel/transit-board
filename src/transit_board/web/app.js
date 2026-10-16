"use strict";

const TOKEN_KEY = "board-token";
const POLL_MS = 3000;

const SCENES = {
  transit: ["Transit", "departures"],
  sports: ["Sports", "scores"],
  idle: ["Idle", "moon & stars"],
  auto: ["Auto", "sports if live"],
};
const SHOWING = {
  departures: "Transit",
  idle: "Idle",
  sports_full: "Sports",
  sports_hybrid: "Sports + transit",
};
const REASONS = { "transit-window": "transit window", night: "night", day: "day" };
const DURATIONS = [[15, "15m"], [30, "30m"], [60, "1h"], [120, "2h"], [null, "Hold"]];

const $ = (id) => document.getElementById(id);
let token = localStorage.getItem(TOKEN_KEY);
let minutes = 15;
let durationInit = false;
let scenesBuilt = false;
let pollTimer = null;
let restarting = false;

async function api(path, method = "GET", body) {
  const res = await fetch(path, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (res.status === 401) {
    logout();
    throw new Error("unauthorized");
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok && !data.error && data.ok !== false) throw new Error(`HTTP ${res.status}`);
  return { ok: res.ok, data };
}

function logout() {
  localStorage.removeItem(TOKEN_KEY);
  token = null;
  $("panel").hidden = true;
  $("login").hidden = false;
}

function fmtRemaining(secs) {
  if (secs == null) return "held until cleared";
  const m = Math.floor(secs / 60);
  if (m >= 60) return `${Math.floor(m / 60)}h ${m % 60}m left`;
  return m > 0 ? `${m} min left` : `${secs}s left`;
}

function fmtAge(secs) {
  if (secs == null) return "never";
  if (secs < 90) return `${secs}s ago`;
  if (secs < 5400) return `${Math.round(secs / 60)}m ago`;
  return `${Math.round(secs / 3600)}h ago`;
}

function buildDurations() {
  const box = $("durations");
  box.replaceChildren();
  for (const [value, label] of DURATIONS) {
    const b = document.createElement("button");
    b.type = "button";
    b.className = "chip";
    b.setAttribute("role", "radio");
    b.dataset.minutes = value === null ? "hold" : String(value);
    b.textContent = label;
    b.addEventListener("click", () => {
      minutes = value;
      markDurations();
    });
    box.appendChild(b);
  }
  markDurations();
}

function markDurations() {
  for (const b of $("durations").children) {
    const mine = b.dataset.minutes === (minutes === null ? "hold" : String(minutes));
    b.setAttribute("aria-checked", String(mine));
  }
}

function buildScenes(names) {
  const box = $("scenes");
  box.replaceChildren();
  for (const name of names) {
    const [title, sub] = SCENES[name] || [name, ""];
    const b = document.createElement("button");
    b.type = "button";
    b.className = "scene";
    b.dataset.scene = name;
    b.textContent = title;
    const small = document.createElement("small");
    small.textContent = sub;
    b.appendChild(small);
    b.addEventListener("click", () => setOverride(name));
    box.appendChild(b);
  }
  scenesBuilt = true;
}

async function setOverride(scene) {
  try {
    const { data } = await api("/api/override", "POST", { scene, minutes });
    render(data);
  } catch (e) {
    if (e.message !== "unauthorized") showConn(true);
  }
}

async function clearOverride() {
  try {
    const { data } = await api("/api/override", "DELETE");
    render(data);
  } catch (e) {
    if (e.message !== "unauthorized") showConn(true);
  }
}

function render(s) {
  showConn(false);
  $("login").hidden = true;
  $("panel").hidden = false;

  if (!scenesBuilt) buildScenes(s.scenes);
  if (!durationInit) {
    durationInit = true;
    minutes = DURATIONS.some(([v]) => v === s.override_minutes) ? s.override_minutes : 15;
    buildDurations();
  }

  $("showing").textContent = SHOWING[s.showing] || s.showing || "…";
  $("default").textContent = `${SCENES[s.default.scene]?.[0] ?? s.default.scene} (${
    REASONS[s.default.reason] ?? s.default.reason
  })`;
  $("override-row").hidden = !s.override;
  if (s.override) {
    $("override").textContent = `${SCENES[s.override.scene]?.[0] ?? s.override.scene} · ${fmtRemaining(
      s.override.remaining_secs,
    )}`;
  }
  $("clear").hidden = !s.override;
  for (const b of $("scenes").children) {
    b.classList.toggle("active", !!s.override && s.override.scene === b.dataset.scene);
  }
}

function renderHealth(h) {
  const box = $("health");
  box.replaceChildren();
  const add = (label, text, cls) => {
    const row = document.createElement("div");
    row.className = "row";
    const l = document.createElement("span");
    l.className = "label";
    l.textContent = label;
    const v = document.createElement("span");
    v.textContent = text;
    if (cls) v.className = cls;
    row.append(l, v);
    box.appendChild(row);
  };
  add("Uptime", fmtAge(h.uptime_secs).replace(" ago", ""));
  add("Config loaded", fmtAge(h.config_age_secs));
  for (const [name, src] of Object.entries(h.sources)) {
    add(name, src.error ? `error: ${src.error}` : fmtAge(src.age_secs), src.error ? "err" : "");
  }
  if (h.board_restarts) add("Render restarts", `${h.board_restarts} (${h.board_last_error})`, "err");
}

function showConn(bad) {
  $("conn").hidden = !bad;
}

async function poll() {
  clearTimeout(pollTimer);
  if (token) {
    try {
      const { data } = await api("/api/state");
      render(data);
      if (restarting) {
        restarting = false;
        adminMsg("Board is back.", "ok");
      }
      if ($("admin").open) {
        const h = await api("/api/health");
        renderHealth(h.data);
      }
    } catch (e) {
      if (e.message !== "unauthorized") showConn(true);
    }
  }
  pollTimer = setTimeout(poll, POLL_MS);
}

function adminMsg(text, cls = "muted") {
  const el = $("admin-msg");
  el.hidden = !text;
  el.textContent = text;
  el.className = cls;
}

$("login-form").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  token = $("token").value.trim();
  $("login-error").hidden = true;
  try {
    const { data } = await api("/api/state");
    localStorage.setItem(TOKEN_KEY, token);
    $("token").value = "";
    render(data);
    poll();
  } catch (e) {
    if (e.message === "unauthorized") {
      $("login-error").textContent = "Wrong token.";
    } else {
      $("login-error").textContent = "Can't reach the board.";
    }
    $("login-error").hidden = false;
    $("login").hidden = false;
  }
});

$("clear").addEventListener("click", clearOverride);

$("admin").addEventListener("toggle", async () => {
  if ($("admin").open && token) {
    try {
      renderHealth((await api("/api/health")).data);
    } catch (_) {}
  }
});

$("reload").addEventListener("click", async () => {
  adminMsg("Reloading…");
  try {
    const { ok, data } = await api("/api/reload", "POST");
    if (!ok) return adminMsg(`Rejected: ${data.error}`, "err");
    adminMsg(data.notes.length ? `Reloaded. ${data.notes.join(" ")}` : "Reloaded.", "ok");
  } catch (e) {
    if (e.message !== "unauthorized") adminMsg("Request failed.", "err");
  }
});

$("restart").addEventListener("click", async () => {
  if (!confirm("Restart the whole board process? It's offline for a few seconds.")) return;
  try {
    await api("/api/restart", "POST");
    restarting = true;
    adminMsg("Restarting… waiting for the board.");
  } catch (e) {
    if (e.message !== "unauthorized") adminMsg("Request failed.", "err");
  }
});

if (token) {
  poll();
} else {
  $("login").hidden = false;
}
