const ACCENT = "#2f4f4f";
const ACCENT_LIGHT = "#6f8f8f";
const RUST = "#8a3b2e";

Chart.defaults.font.family = "'Iowan Old Style', 'Palatino Linotype', Palatino, Georgia, serif";
Chart.defaults.color = "#444";

async function loadData() {
  const [letters, stats] = await Promise.all([
    fetch("data/letters.json").then((r) => r.json()),
    fetch("data/stats.json").then((r) => r.json()),
  ]);
  return { letters, stats };
}

function formatDate(iso) {
  return new Date(iso).toLocaleDateString("fr-FR", { dateStyle: "long" });
}

function formatExecDate(iso) {
  if (!iso) return "—";
  return new Date(iso + "T12:00:00").toLocaleDateString("fr-FR", {
    day: "numeric",
    month: "short",
    year: "numeric",
  });
}

/* ---------- barres horizontales génériques ---------- */

function hBarChart(canvasId, labels, values, { color = ACCENT, suffix = "" } = {}) {
  const el = document.getElementById(canvasId);
  if (!el) return;
  new Chart(el, {
    type: "bar",
    data: {
      labels,
      datasets: [{ data: values, backgroundColor: color, borderWidth: 0, barPercentage: 0.7 }],
    },
    options: {
      indexAxis: "y",
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => `${ctx.parsed.x}${suffix}` } },
      },
      scales: {
        x: { grid: { color: "#eee" }, ticks: { precision: 0 } },
        y: { grid: { display: false } },
      },
    },
  });
  el.parentElement.style.height = `${Math.max(labels.length * 26 + 40, 160)}px`;
}

function vBarChart(canvasId, labels, values, { color = ACCENT } = {}) {
  const el = document.getElementById(canvasId);
  if (!el) return;
  new Chart(el, {
    type: "bar",
    data: {
      labels,
      datasets: [{ data: values, backgroundColor: color, borderWidth: 0 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: { grid: { display: false } },
        y: { grid: { color: "#eee" }, ticks: { precision: 0 } },
      },
    },
  });
}

/* ---------- sections ---------- */

function renderSummary(stats) {
  const s = stats.summary;
  document.getElementById("corpus-note").innerHTML =
    `Sur les <strong>${s.total_records} fiches</strong> recensées par le Maitron dans la catégorie ` +
    `« Lettres de fusillés », <strong>${s.letters} lettres</strong> ont pu être extraites ` +
    `(${s.excluded_records} fiches sans transcription exploitable sont écartées de l'analyse). ` +
    `Chaque lettre est croisée avec la notice biographique de son auteur.`;

  const items = [
    ["Lettres analysées", s.letters],
    ["Mots au total", s.total_words.toLocaleString("fr-FR")],
    ["Longueur moyenne", `${s.avg_words} mots`],
    ["Âge médian", s.median_age ? `${s.median_age} ans` : "—"],
    ["Exécutions localisées", s.located],
    ["Lettre la plus longue", `${s.max_words.toLocaleString("fr-FR")} mots`],
  ];
  document.getElementById("stats-grid").innerHTML = items
    .map(
      ([label, value]) => `
      <div class="stat-card">
        <span class="stat-value">${value}</span>
        <span class="stat-label">${label}</span>
      </div>`
    )
    .join("");
  document.getElementById("meta-date").textContent =
    `Données extraites du Maitron le ${formatDate(stats.generated_at)} · modèle spaCy ${stats.model}`;
  const modelEl = document.getElementById("model-name");
  if (modelEl) modelEl.textContent = stats.model;
}

function renderLengths(stats) {
  vBarChart(
    "chart-lengths",
    stats.length_bins.map((b) => b.label),
    stats.length_bins.map((b) => b.count)
  );
}

function renderTimeline(stats) {
  const el = document.getElementById("chart-timeline");
  const labels = stats.timeline.map((t) => {
    const [y, m] = t.month.split("-");
    const names = ["janv", "févr", "mars", "avr", "mai", "juin", "juil", "août", "sept", "oct", "nov", "déc"];
    return `${names[Number(m) - 1]} ${y.slice(2)}`;
  });
  new Chart(el, {
    type: "bar",
    data: {
      labels,
      datasets: [
        {
          data: stats.timeline.map((t) => t.count),
          backgroundColor: RUST,
          borderWidth: 0,
          barPercentage: 0.9,
          categoryPercentage: 0.95,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => `${ctx.parsed.y} exécution${ctx.parsed.y > 1 ? "s" : ""}` } },
      },
      scales: {
        x: { grid: { display: false }, ticks: { maxRotation: 60, autoSkip: true, maxTicksLimit: 24 } },
        y: { grid: { color: "#eee" }, ticks: { precision: 0 } },
      },
    },
  });
}

function renderMap(stats) {
  const places = stats.map_places;
  if (!places.length) {
    document.getElementById("map").outerHTML = '<p class="hint">Aucun lieu localisé.</p>';
    return;
  }
  const map = L.map("map", { scrollWheelZoom: false }).setView([47.5, 2.5], 5.4);
  map.attributionControl.setPrefix('<a href="https://leafletjs.com">Leaflet</a>');
  L.tileLayer("https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png", {
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> &copy; <a href="https://carto.com/">CARTO</a>',
    maxZoom: 12,
  }).addTo(map);

  const maxCount = Math.max(...places.map((p) => p.count));
  places.forEach((p) => {
    const radius = 6 + 22 * Math.sqrt(p.count / maxCount);
    const circle = L.circleMarker([p.lat, p.lon], {
      radius,
      color: RUST,
      weight: 1,
      fillColor: RUST,
      fillOpacity: 0.45,
    }).addTo(map);
    const names = p.names.slice(0, 6).join(", ") + (p.count > 6 ? "…" : "");
    circle.bindPopup(
      `<strong>${p.place}</strong><br>${p.count} fusillé${p.count > 1 ? "s" : ""} du corpus<br><em>${names}</em>`
    );
  });

  document.getElementById("map-note").textContent =
    `${stats.summary.located} exécutions localisées sur ${stats.summary.letters} lettres ; ` +
    `les autres notices ne précisent pas le lieu de façon exploitable.`;
}

function renderProfiles(stats) {
  vBarChart(
    "chart-ages",
    stats.age_bins.map((b) => b.label),
    stats.age_bins.map((b) => b.count)
  );
  hBarChart(
    "chart-groups",
    stats.group_counts.map((g) => g.group),
    stats.group_counts.map((g) => g.count),
    { suffix: " lettres" }
  );
}

function renderLexicon(stats) {
  hBarChart(
    "chart-words",
    stats.top_words.slice(0, 20).map((w) => w.word),
    stats.top_words.slice(0, 20).map((w) => w.count),
    { suffix: " occurrences" }
  );
  hBarChart("chart-nouns", stats.top_nouns.map((w) => w.word), stats.top_nouns.map((w) => w.count), { suffix: " occ." });
  hBarChart("chart-verbs", stats.top_verbs.map((w) => w.word), stats.top_verbs.map((w) => w.count), { suffix: " occ.", color: ACCENT_LIGHT });
  hBarChart("chart-adjectives", stats.top_adjectives.map((w) => w.word), stats.top_adjectives.map((w) => w.count), { suffix: " occ.", color: ACCENT_LIGHT });
  hBarChart(
    "chart-phrases",
    stats.phrase_stats.map((p) => `« ${p.phrase} »`),
    stats.phrase_stats.map((p) => p.percentage),
    { suffix: " % des lettres", color: RUST }
  );
}

function renderEntities(stats) {
  hBarChart("chart-ent-locations", stats.entities.locations.slice(0, 18).map((w) => w.word), stats.entities.locations.slice(0, 18).map((w) => w.count), { suffix: " mentions" });
  hBarChart("chart-ent-persons", stats.entities.persons.slice(0, 15).map((w) => w.word), stats.entities.persons.slice(0, 15).map((w) => w.count), { suffix: " mentions" });
  hBarChart("chart-ent-organisations", stats.entities.organisations.slice(0, 12).map((w) => w.word), stats.entities.organisations.slice(0, 12).map((w) => w.count), { suffix: " mentions" });
}

function renderFigures(stats) {
  hBarChart(
    "chart-figures",
    stats.figures.map((f) => f.figure),
    stats.figures.map((f) => f.percentage),
    { suffix: " % des lettres", color: RUST }
  );
}

function renderComparison(stats) {
  const c = stats.comparison;
  if (!c.groups || c.groups.length < 2) {
    document.getElementById("chart-comparison").outerHTML =
      '<p class="hint">Notices insuffisantes pour la comparaison.</p>';
    return;
  }
  const el = document.getElementById("chart-comparison");
  const colors = { communiste: RUST, autres: ACCENT_LIGHT };
  new Chart(el, {
    type: "bar",
    data: {
      labels: c.terms,
      datasets: c.groups.map((g) => ({
        label: `${g.name} (${g.size})`,
        data: c.rates[g.name],
        backgroundColor: colors[g.name] || ACCENT,
        borderWidth: 0,
      })),
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { position: "top" },
        tooltip: { callbacks: { label: (ctx) => `${ctx.dataset.label} : ${ctx.parsed.y} % des lettres` } },
      },
      scales: {
        x: { grid: { display: false } },
        y: { grid: { color: "#eee" }, title: { display: true, text: "% des lettres du groupe" } },
      },
    },
  });
  const sizes = c.groups.map((g) => `${g.name} : ${g.size} lettres, ${g.avg_words} mots en moyenne`);
  document.getElementById("comparison-note").textContent = sizes.join(" · ");
}

function renderThemes(stats) {
  const el = document.getElementById("chart-clusters");
  new Chart(el, {
    type: "doughnut",
    data: {
      labels: stats.clusters.map((c) => `Groupe ${c.id}`),
      datasets: [
        {
          data: stats.clusters.map((c) => c.size),
          backgroundColor: [ACCENT, RUST],
          borderWidth: 2,
          borderColor: "#fff",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { position: "bottom" } },
    },
  });

  document.getElementById("clusters").innerHTML = stats.clusters
    .map(
      (cluster) => `
      <article class="cluster-card">
        <h4>Groupe ${cluster.id} — ${cluster.size} lettres</h4>
        <p class="keywords">${cluster.keywords.join(", ")}</p>
      </article>`
    )
    .join("");

  document.getElementById("topics").innerHTML = stats.topics
    .map(
      (topic) => `
      <article class="cluster-card">
        <h4>Thème ${topic.id + 1}</h4>
        <p class="keywords">${topic.keywords.join(", ")}</p>
      </article>`
    )
    .join("");
}

/* ---------- concordancier ---------- */

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function renderKwic(letters, term) {
  const el = document.getElementById("kwic-results");
  const query = term.trim().toLowerCase();
  if (query.length < 3) {
    el.innerHTML = '<p class="hint">Saisissez au moins 3 caractères.</p>';
    return;
  }
  const regex = new RegExp(escapeRegExp(query), "gi");
  const rows = [];
  let total = 0;
  for (const letter of letters) {
    const text = letter.letter_text;
    let match;
    let count = 0;
    while ((match = regex.exec(text)) !== null) {
      total += 1;
      if (count >= 3 || rows.length >= 50) continue;
      const start = Math.max(0, match.index - 60);
      const end = Math.min(text.length, match.index + query.length + 60);
      const left = (start > 0 ? "…" : "") + text.slice(start, match.index);
      const hit = text.slice(match.index, match.index + query.length);
      const right = text.slice(match.index + query.length, end) + (end < text.length ? "…" : "");
      rows.push(
        `<div class="kwic-row"><span class="kwic-name">${letter.person_name}</span>` +
          `<span class="kwic-ctx">${left.replace(/\n/g, " ")}<mark>${hit}</mark>${right.replace(/\n/g, " ")}</span></div>`
      );
      count += 1;
    }
  }
  el.innerHTML = rows.length
    ? `<p class="hint">${total} occurrence${total > 1 ? "s" : ""}${rows.length < total ? ` — ${rows.length} affichées` : ""}</p>` + rows.join("")
    : `<p class="hint">Aucune occurrence pour « ${query} ».</p>`;
}

/* ---------- table des lettres ---------- */

const tableState = { sortKey: "person_name", sortDir: 1, query: "", group: "" };

function renderTable(letters) {
  const tbody = document.querySelector("#corpus-table tbody");
  const query = tableState.query.trim().toLowerCase();

  let filtered = letters.filter((row) => {
    if (tableState.group && !row.groups.includes(tableState.group)) return false;
    if (!query) return true;
    return (
      row.person_name.toLowerCase().includes(query) ||
      row.letter_text.toLowerCase().includes(query) ||
      (row.exec_place || "").toLowerCase().includes(query) ||
      (row.bio || "").toLowerCase().includes(query)
    );
  });

  const key = tableState.sortKey;
  filtered = filtered.slice().sort((a, b) => {
    const va = a[key] ?? (typeof a[key] === "number" ? 0 : "");
    const vb = b[key] ?? (typeof b[key] === "number" ? 0 : "");
    if (va === null || va === "") return 1;
    if (vb === null || vb === "") return -1;
    if (typeof va === "number") return (va - vb) * tableState.sortDir;
    return String(va).localeCompare(String(vb), "fr") * tableState.sortDir;
  });

  document.getElementById("corpus-hint").textContent =
    `${filtered.length} lettre${filtered.length > 1 ? "s" : ""} — cliquer sur une ligne pour lire la lettre et la notice`;

  tbody.innerHTML = filtered
    .map(
      (row) => `
      <tr data-index="${letters.indexOf(row)}">
        <td>${row.person_name}</td>
        <td>${row.age ?? "—"}</td>
        <td>${formatExecDate(row.exec_date)}</td>
        <td>${row.exec_place || "—"}</td>
        <td class="groups-cell">${row.groups.join(", ") || "—"}</td>
        <td>${row.word_count}</td>
      </tr>`
    )
    .join("");
}

function openLetter(letters, index) {
  const row = letters[index];
  const dialog = document.getElementById("letter-dialog");
  document.getElementById("dialog-name").textContent = row.person_name;
  document.getElementById("dialog-meta").textContent = [
    row.age ? `${row.age} ans` : null,
    row.exec_date ? `exécuté le ${formatExecDate(row.exec_date)}` : null,
    row.exec_place || null,
    `${row.word_count} mots`,
  ]
    .filter(Boolean)
    .join(" · ");
  document.getElementById("dialog-bio").textContent = row.bio || "";
  document.getElementById("dialog-text").textContent = row.letter_text;
  document.getElementById("dialog-url").href = row.person_url;
  dialog.showModal();
  dialog.scrollTop = 0;
}

function setupTable(letters, stats) {
  const select = document.getElementById("filter-group");
  stats.group_counts.forEach((g) => {
    const option = document.createElement("option");
    option.value = g.group;
    option.textContent = `${g.group} (${g.count})`;
    select.appendChild(option);
  });
  select.addEventListener("change", () => {
    tableState.group = select.value;
    renderTable(letters);
  });

  document.getElementById("search").addEventListener("input", (event) => {
    tableState.query = event.target.value;
    renderTable(letters);
  });

  document.querySelectorAll("#corpus-table th[data-sort]").forEach((th) => {
    th.addEventListener("click", () => {
      const key = th.dataset.sort;
      if (tableState.sortKey === key) {
        tableState.sortDir *= -1;
      } else {
        tableState.sortKey = key;
        tableState.sortDir = 1;
      }
      renderTable(letters);
    });
  });

  document.querySelector("#corpus-table tbody").addEventListener("click", (event) => {
    const row = event.target.closest("tr");
    if (!row) return;
    openLetter(letters, Number(row.dataset.index));
  });
}

/* ---------- onglets ---------- */

function setupTabGroup(dataAttr, prefix) {
  document.querySelectorAll(`.tab[data-${dataAttr}]`).forEach((button) => {
    button.addEventListener("click", () => {
      const value = button.dataset[dataAttr];
      const group = button.closest(".panel");
      group.querySelectorAll(`.tab[data-${dataAttr}]`).forEach((b) => b.classList.remove("active"));
      group.querySelectorAll(".tab-panel").forEach((p) => p.classList.remove("active"));
      button.classList.add("active");
      document.getElementById(`${prefix}-${value}`).classList.add("active");
    });
  });
}

/* ---------- init ---------- */

async function main() {
  const { letters, stats } = await loadData();
  renderSummary(stats);
  renderLengths(stats);
  renderTimeline(stats);
  renderMap(stats);
  renderProfiles(stats);
  renderLexicon(stats);
  renderEntities(stats);
  renderFigures(stats);
  renderComparison(stats);
  renderThemes(stats);
  renderKwic(letters, "");
  renderTable(letters);
  setupTable(letters, stats);
  setupTabGroup("tab", "tab");
  setupTabGroup("etab", "etab");

  document.getElementById("kwic-input").addEventListener("input", (event) => {
    renderKwic(letters, event.target.value);
  });
}

main().catch((error) => {
  document.querySelector("main").innerHTML = `<p>Erreur de chargement : ${error.message}</p>`;
  console.error(error);
});
