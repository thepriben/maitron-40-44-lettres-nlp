async function loadData() {
  const [letters, stats] = await Promise.all([
    fetch("data/letters.json").then((r) => r.json()),
    fetch("data/stats.json").then((r) => r.json()),
  ]);
  return { letters, stats };
}

function formatDate(iso) {
  return new Date(iso).toLocaleString("fr-FR", {
    dateStyle: "long",
    timeStyle: "short",
  });
}

function renderSummary(stats) {
  const grid = document.getElementById("stats-grid");
  const items = [
    ["Fiches", stats.summary.total_persons],
    ["Avec lettre", stats.summary.with_letter],
    ["Sans lettre", stats.summary.without_letter],
    ["Mots total", stats.summary.total_words.toLocaleString("fr-FR")],
    ["Moyenne / lettre", stats.summary.avg_words],
    ["Maximum", stats.summary.max_words],
  ];
  grid.innerHTML = items
    .map(
      ([label, value]) => `
      <div class="stat-card">
        <span class="stat-value">${value}</span>
        <span class="stat-label">${label}</span>
      </div>`
    )
    .join("");
  document.getElementById("meta-date").textContent =
    `Données générées le ${formatDate(stats.generated_at)}`;
}

function renderLetterChart(stats) {
  const chart = document.getElementById("letter-chart");
  const max = Math.max(...stats.by_letter.map((x) => x.total), 1);
  chart.innerHTML = stats.by_letter
    .map((row) => {
      const width = (row.total / max) * 100;
      return `
        <div class="bar-row">
          <span>${row.letter}</span>
          <div class="bar-track"><div class="bar-fill" style="width:${width}%"></div></div>
          <span>${row.with_letter}/${row.total}</span>
        </div>`;
    })
    .join("");
}

function renderFreqList(containerId, items, label = "occurrences") {
  const el = document.getElementById(containerId);
  el.innerHTML = `<ul class="freq-list">${items
    .map(
      (item) => `
      <li>
        <span>${item.word || item.phrase}</span>
        <span class="count">${item.count ?? item.occurrences} ${label}</span>
      </li>`
    )
    .join("")}</ul>`;
}

function renderPhraseStats(stats) {
  const el = document.getElementById("tab-phrases");
  el.innerHTML = `<ul class="freq-list">${stats.phrase_stats
    .map(
      (item) => `
      <li>
        <span>« ${item.phrase} »</span>
        <span class="count">${item.documents} lettres (${item.percentage} %)</span>
      </li>`
    )
    .join("")}</ul>`;
}

function renderClusters(stats) {
  const el = document.getElementById("clusters");
  el.innerHTML = stats.clusters
    .map(
      (cluster) => `
      <article class="cluster-card">
        <h3>Groupe ${cluster.id} — ${cluster.size} lettres</h3>
        <p class="keywords">${cluster.keywords.join(", ")}</p>
      </article>`
    )
    .join("");
}

function renderTopics(stats) {
  const el = document.getElementById("topics");
  if (!stats.topics || !stats.topics.length) {
    el.innerHTML = '<p class="hint">Corpus insuffisant pour la modélisation thématique.</p>';
    return;
  }
  el.innerHTML = stats.topics
    .map(
      (topic) => `
      <article class="cluster-card">
        <h3>Thème ${topic.id + 1}</h3>
        <p class="keywords">${topic.keywords.join(", ")}</p>
      </article>`
    )
    .join("");
}

function renderEntities(stats) {
  const groups = ["locations", "persons", "organisations"];
  groups.forEach((group) => {
    renderFreqList(`etab-${group}`, stats.entities[group], "mentions");
  });
}

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
  for (const letter of letters) {
    if (!letter.has_letter) continue;
    const text = letter.letter_text;
    let match;
    let count = 0;
    while ((match = regex.exec(text)) !== null && count < 3) {
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
    if (rows.length >= 40) break;
  }
  el.innerHTML = rows.length
    ? rows.join("")
    : `<p class="hint">Aucune occurrence pour « ${query} ».</p>`;
}

function renderTable(letters, filter = "") {
  const tbody = document.querySelector("#corpus-table tbody");
  const query = filter.trim().toLowerCase();
  const filtered = letters.filter((row) => {
    if (!query) return true;
    return (
      row.person_name.toLowerCase().includes(query) ||
      row.letter_text.toLowerCase().includes(query)
    );
  });

  document.getElementById("corpus-hint").textContent =
    `${filtered.length} fiche${filtered.length > 1 ? "s" : ""} affichée${filtered.length > 1 ? "s" : ""}`;

  tbody.innerHTML = filtered
    .map((row, index) => {
      const hasLetter = row.has_letter;
      return `
        <tr data-index="${letters.indexOf(row)}" class="${hasLetter ? "" : "no-letter"}">
          <td>${row.person_name}</td>
          <td>${row.first_letter}</td>
          <td>${hasLetter ? row.word_count : "—"}</td>
          <td>${hasLetter ? `<span class="badge">${row.cluster}</span>` : '<span class="badge empty">—</span>'}</td>
          <td>${hasLetter ? "oui" : "non"}</td>
        </tr>`;
    })
    .join("");
}

function openLetter(letters, index) {
  const row = letters[index];
  const dialog = document.getElementById("letter-dialog");
  document.getElementById("dialog-name").textContent = row.person_name;
  document.getElementById("dialog-meta").textContent = [
    `Initiale ${row.first_letter}`,
    row.has_letter ? `${row.word_count} mots` : "Pas de lettre disponible",
    row.has_letter ? `Groupe ${row.cluster}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
  document.getElementById("dialog-text").textContent = row.has_letter
    ? row.letter_text
    : "Aucune lettre n'a pu être extraite de cette fiche.";
  document.getElementById("dialog-url").href = row.person_url;
  dialog.showModal();
}

function setupTabGroup(dataAttr, prefix) {
  const buttons = document.querySelectorAll(`.tab[data-${dataAttr}]`);
  buttons.forEach((button) => {
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

function setupTabs() {
  setupTabGroup("tab", "tab");
  setupTabGroup("etab", "etab");
}

async function main() {
  const { letters, stats } = await loadData();
  renderSummary(stats);
  renderLetterChart(stats);
  renderFreqList("tab-words", stats.top_words);
  renderFreqList("tab-nouns", stats.top_nouns);
  renderFreqList("tab-verbs", stats.top_verbs);
  renderFreqList("tab-adjectives", stats.top_adjectives);
  renderPhraseStats(stats);
  renderEntities(stats);
  renderTopics(stats);
  renderClusters(stats);
  renderTable(letters);
  renderKwic(letters, "");

  document.getElementById("search").addEventListener("input", (event) => {
    renderTable(letters, event.target.value);
  });

  document.getElementById("kwic-input").addEventListener("input", (event) => {
    renderKwic(letters, event.target.value);
  });

  document.querySelector("#corpus-table tbody").addEventListener("click", (event) => {
    const row = event.target.closest("tr");
    if (!row) return;
    openLetter(letters, Number(row.dataset.index));
  });

  setupTabs();
}

main().catch((error) => {
  document.body.innerHTML = `<main class="wrap"><p>Erreur de chargement : ${error.message}</p></main>`;
});
