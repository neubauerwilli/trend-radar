(() => {
  "use strict";

  const SOURCES = [
    { key: "all", label: "Alle" },
    { key: "hackernews", label: "Hacker News", cls: "hackernews" },
    { key: "r/ClaudeAI", label: "r/ClaudeAI", cls: "claudeai" },
    { key: "r/artificial", label: "r/artificial", cls: "artificial" },
  ];
  const STALE_HOURS = 30;
  const nf = new Intl.NumberFormat("de-AT");
  const $ = (id) => document.getElementById(id);

  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const safeUrl = (u) => (/^https?:\/\//i.test(String(u || "")) ? esc(u) : "#");
  const num = (n) => (Number.isFinite(Number(n)) ? nf.format(Number(n)) : "–");
  const paras = (t) => String(t || "").split(/\n+/).filter(Boolean).map((p) => `<p>${esc(p)}</p>`).join("");

  // Lokal (Repo-Root servieren, /site/ öffnen) liegen die Daten unter ../data, auf GitHub Pages unter data/.
  async function load(name) {
    for (const base of ["data/", "../data/"]) {
      try {
        const r = await fetch(`${base}${name}.json`, { cache: "no-store" });
        if (r.ok) return await r.json();
      } catch (_) { /* nächster Pfad */ }
    }
    return null;
  }

  function fmtDate(iso) {
    const d = new Date(iso);
    if (isNaN(d)) return null;
    return d.toLocaleString("de-AT", { timeZone: "Europe/Vienna", weekday: "short", day: "2-digit", month: "2-digit", year: "numeric", hour: "2-digit", minute: "2-digit" });
  }

  function ago(iso) {
    const d = new Date(iso);
    if (isNaN(d)) return "";
    const h = Math.round((Date.now() - d) / 36e5);
    if (h < 1) return "gerade eben";
    if (h < 24) return `vor ${h} Std.`;
    const days = Math.round(h / 24);
    return `vor ${days} ${days === 1 ? "Tag" : "Tagen"}`;
  }

  function header(files) {
    const stamps = files.filter(Boolean).map((f) => new Date(f.generated_at)).filter((d) => !isNaN(d));
    if (!stamps.length) { $("stand").textContent = "Noch keine Daten vorhanden"; return; }
    const newest = new Date(Math.max(...stamps));
    const oldest = new Date(Math.min(...stamps));
    $("stand").textContent = `Stand: ${fmtDate(newest.toISOString())}`;
    $("sample-badge").hidden = !files.some((f) => f && f.sample);
    const hours = (Date.now() - oldest) / 36e5;
    if (hours > STALE_HOURS) {
      const n = $("stale");
      n.hidden = false;
      n.textContent = `Hinweis: Teile der Daten sind älter als ${STALE_HOURS} Stunden (${ago(oldest.toISOString())}). Die letzte Aktualisierung ist vermutlich fehlgeschlagen.`;
    }
  }

  function kpis(news, gh, ideas) {
    const items = news?.items || [];
    const top = [...items].sort((a, b) => (b.points || 0) - (a.points || 0))[0];
    const totalComments = items.reduce((s, i) => s + (Number(i.comments) || 0), 0);
    const repo = gh?.repos?.[0];
    const topic = ideas?.topics?.[0];
    const cards = [
      ["Beiträge", num(items.length), `${num(totalComments)} Kommentare`],
      ["Top-Beitrag", top ? num(top.points) : "–", top ? top.title : "keine Daten"],
      ["Top-Repo", repo ? `+${num(repo.stars_week)}` : "–", repo ? repo.name : "keine Daten"],
      ["Heißestes Thema", topic ? "#1" : "–", topic ? topic.topic : "keine Daten"],
    ];
    $("kpis").innerHTML = cards.map(([l, v, s]) => `<div class="kpi"><div class="label">${esc(l)}</div><div class="value">${esc(v)}</div><div class="sub" title="${esc(s)}">${esc(s)}</div></div>`).join("");
  }

  function renderIdeas(ideas) {
    const topics = ideas?.topics || [];
    if (!topics.length) { $("ideas").innerHTML = `<div class="empty">Noch keine Content-Ideen.</div>`; return; }
    $("ideas").innerHTML = topics.slice(0, 5).map((t, i) => {
      const src = (t.sources || []).slice(0, 4).map((u, j) => `<a href="${safeUrl(u)}" target="_blank" rel="noopener">Quelle ${j + 1}</a>`).join("");
      return `<article class="idea">
        <div class="idea-head"><span class="rank">${i + 1}</span><h3>${esc(t.topic)}</h3>${t.score != null ? `<span class="score">${num(t.score)} Pkt.</span>` : ""}</div>
        <div class="fmt"><div class="k">Short</div>${paras(t.short)}</div>
        <div class="fmt"><div class="k">Karussell</div>${paras(t.carousel)}</div>
        <div class="fmt"><div class="k">Langes Video</div>${paras(t.long_video)}</div>
        ${src ? `<div class="src">${src}</div>` : ""}
      </article>`;
    }).join("");
  }

  function renderNews(news) {
    const items = [...(news?.items || [])].sort((a, b) => (b.points || 0) - (a.points || 0));
    let current = "all";
    const tabs = $("tabs");
    tabs.innerHTML = SOURCES.map((s) => {
      const n = s.key === "all" ? items.length : items.filter((i) => i.source === s.key).length;
      return `<button class="tab" role="tab" data-key="${esc(s.key)}" aria-selected="${s.key === current}">${esc(s.label)} <span aria-hidden="true">${n}</span></button>`;
    }).join("");
    const draw = () => {
      const list = (current === "all" ? items : items.filter((i) => i.source === current)).slice(0, 25);
      if (!list.length) { $("news").innerHTML = `<li class="empty" style="border:0">Keine Beiträge.</li>`; return; }
      $("news").innerHTML = list.map((i) => {
        const s = SOURCES.find((x) => x.key === i.source) || { label: i.source, cls: "" };
        const disc = i.discussion_url ? `<a href="${safeUrl(i.discussion_url)}" target="_blank" rel="noopener">${num(i.comments)} Kommentare</a>` : `<span>${num(i.comments)} Kommentare</span>`;
        return `<li>
          <a class="title" href="${safeUrl(i.url)}" target="_blank" rel="noopener">${esc(i.title)}</a>
          <div class="row-meta"><span class="src-tag ${s.cls}">${esc(s.label)}</span><span>▲ ${num(i.points)}</span>${disc}${i.created_at ? `<span>${esc(ago(i.created_at))}</span>` : ""}</div>
        </li>`;
      }).join("");
    };
    tabs.addEventListener("click", (e) => {
      const b = e.target.closest(".tab");
      if (!b) return;
      current = b.dataset.key;
      tabs.querySelectorAll(".tab").forEach((t) => t.setAttribute("aria-selected", String(t === b)));
      draw();
    });
    draw();
  }

  function renderRepos(gh) {
    const repos = [...(gh?.repos || [])].sort((a, b) => (b.stars_week || 0) - (a.stars_week || 0)).slice(0, 10);
    if (!repos.length) { $("repos").innerHTML = `<li class="empty" style="border:0">Noch keine GitHub-Daten.</li>`; return; }
    const max = Math.max(...repos.map((r) => r.stars_week || 0), 1);
    $("repos").innerHTML = repos.map((r, i) => `<li>
      <span class="pos">${i + 1}</span>
      <div><a class="name" href="${safeUrl(r.url)}" target="_blank" rel="noopener">${esc(r.name)}</a>
        ${r.description ? `<div class="desc">${esc(r.description)}</div>` : ""}
        ${r.language ? `<div class="row-meta"><span>${esc(r.language)}</span>${r.stars_total != null ? `<span>★ ${num(r.stars_total)} gesamt</span>` : ""}</div>` : ""}
      </div>
      <div class="stars">+${num(r.stars_week)}<small>Sterne</small></div>
      <div class="bar"><span style="width:${Math.max(2, Math.round(((r.stars_week || 0) / max) * 100))}%"></span></div>
    </li>`).join("");
  }

  Promise.all(["news", "github", "ideas"].map(load)).then(([news, gh, ideas]) => {
    header([news, gh, ideas]);
    kpis(news, gh, ideas);
    renderIdeas(ideas);
    renderNews(news);
    renderRepos(gh);
  });
})();
