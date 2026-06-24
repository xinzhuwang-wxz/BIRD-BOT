// Shared helpers for the three faces. Vanilla JS, no build step.
const BB = {
  async api(path, opts) {
    const r = await fetch(path, opts);
    if (!r.ok) throw new Error(`${r.status} ${await r.text()}`);
    return r.json();
  },
  post(path, body) {
    return BB.api(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body || {}),
    });
  },

  // Live SSE with auto-reconnect; flips the nav live dot.
  sse(onEvent) {
    const dot = document.querySelector(".dot-live");
    let es;
    const connect = () => {
      es = new EventSource("/api/events/stream");
      es.onopen = () => dot && dot.classList.add("on");
      es.onerror = () => { dot && dot.classList.remove("on"); };
      es.onmessage = (e) => {
        try { onEvent(JSON.parse(e.data)); } catch (_) {}
      };
    };
    connect();
    return () => es && es.close();
  },

  nav(active) {
    const tabs = [
      ["/", "Overview", "home"],
      ["/device.html", "🛰  Device Simulator", "device"],
      ["/app.html", "📱  NatureFeed App", "app"],
      ["/console.html", "🏢  Ops Console", "console"],
    ];
    return `<nav class="nav">
      <span class="brand">Bird<span class="dot">●</span>Bot</span>
      ${tabs.map(([href, label, key]) =>
        `<a class="tab ${key === active ? "active" : ""}" href="${href}">${label}</a>`).join("")}
      <span class="spacer"></span>
      <span class="live"><span class="dot-live"></span> live</span>
    </nav>`;
  },

  mountNav(active) {
    const el = document.createElement("div");
    el.innerHTML = BB.nav(active);
    document.body.insertBefore(el.firstElementChild, document.body.firstChild);
  },

  esc(s) {
    return String(s ?? "").replace(/[&<>"]/g, (c) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  },

  avatar(species, size = 52) {
    const c = species.color || "#888";
    return `<div class="avatar" style="width:${size}px;height:${size}px;font-size:${Math.round(size*0.5)}px;
      background:linear-gradient(135deg, ${c}, ${c}55);">${species.emoji || "🐦"}</div>`;
  },

  rarityBadge(r) {
    const cls = ["rare", "seasonal", "common"].includes(r) ? r : "unknown";
    return `<span class="badge ${cls}">${r}</span>`;
  },
  decisionBadge(d) {
    const cls = ["accept", "rollup", "escalate"].includes(d) ? d : "unknown";
    return `<span class="badge ${cls}">${d}</span>`;
  },

  timeAgo(iso) {
    const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
    if (s < 60) return `${Math.floor(s)}s ago`;
    if (s < 3600) return `${Math.floor(s / 60)}m ago`;
    return `${Math.floor(s / 3600)}h ago`;
  },

  money(v) { return "$" + Number(v || 0).toFixed(v < 0.01 ? 5 : 2); },
};
