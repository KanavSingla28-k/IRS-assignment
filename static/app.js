const $ = (selector) => document.querySelector(selector);
let documents = [];
let activeReport = null;
let reports = [];
let recentQueries = [];
let currentQuery = '';
let coverageQuery = '';
let mode = 'inverted';
let searchVersion = 0;
let collectionVersion = 0;
let collectionSignature = null;
let collectionRequest = 0;
let mutating = false;
const samples = [
  { title: '01 · Computer science', text: 'Computer science studies computers and computation. Computer systems use algorithms to process information. Computing connects mathematics and engineering.' },
  { title: '02 · Search engines', text: 'A search engine retrieves relevant documents. Search engines build an inverted index for fast keyword search. Document indexing stores term frequencies for ranking.' },
  { title: '03 · Text processing', text: 'Text processing includes tokenization, stop word removal and stemming. Running, runs and runner are related words. Processing documents improves information retrieval.' },
  { title: '04 · Partial word retrieval', text: 'Character n-grams support partial word search. Computer and computing share character sequences. A search index maps each sequence to candidate words.' }
];

function element(tag, text, className) {
  const node = document.createElement(tag);
  node.textContent = text;
  if (className) node.className = className;
  return node;
}

function status(message, error = false) {
  for (const selector of ['#status', '#dialog-status']) {
    $(selector).textContent = message;
    $(selector).classList.toggle('error', error);
  }
}

async function api(url, options) {
  const response = await fetch(url, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || 'Request failed. Please try again.');
  return data;
}

function route() {
  const requested = location.hash.slice(1);
  const view = ['search', 'library', 'compare'].includes(requested) ? requested : 'search';
  for (const name of ['search', 'library', 'compare']) {
    $(`#${name}-view`).hidden = name !== view;
    const link = $(`[data-route="${name}"]`);
    if (name === view) link.setAttribute('aria-current', 'page');
    else link.removeAttribute('aria-current');
  }
}

function goToSearch() {
  if (location.hash !== '#search') location.hash = 'search';
  route();
  $('#query').focus({ preventScroll: true });
}

function setSearchBusy(busy) {
  $('#search-submit').disabled = busy;
  $('#search-form').setAttribute('aria-busy', String(busy));
  for (const button of document.querySelectorAll('[data-mode]')) button.disabled = busy;
}

function openDocument(id) {
  const doc = documents.find((item) => item.id === id);
  if (!doc) return;
  $('#document-title').textContent = doc.title;
  $('#document-meta').textContent = `${doc.text.length.toLocaleString()} characters · Text document · Indexed locally`;
  $('#document-content').textContent = doc.text;
  $('#reader-dialog').showModal();
  $('#reader-dialog').scrollTop = 0;
}

function renderLibrary() {
  const query = $('#library-filter').value.trim().toLowerCase();
  const filtered = documents.filter((doc) => doc.title.toLowerCase().includes(query));
  $('#library-count').textContent = `${filtered.length} of ${documents.length} documents`;
  $('#library-empty').hidden = documents.length > 0;
  const grid = $('#library-grid');
  grid.replaceChildren();
  if (documents.length && !filtered.length) {
    grid.append(element('p', 'No titles match this filter. Clear it to see all documents.', 'empty-results'));
  }
  for (const doc of filtered) {
    const card = element('button', '', 'library-card');
    card.setAttribute('aria-label', `Open ${doc.title}`);
    card.append(element('span', 'TXT / SOURCE', 'file-label'), element('h3', doc.title),
      element('p', doc.text.slice(0, 180), 'library-preview'),
      element('span', `${doc.text.length.toLocaleString()} characters ↗`, 'file-meta'));
    card.addEventListener('click', () => openDocument(doc.id));
    grid.append(card);
  }
}

function renderRecent() {
  const container = $('#recent-queries');
  const focusedQuery = container.contains(document.activeElement) ? document.activeElement.textContent : null;
  container.replaceChildren();
  if (!recentQueries.length) container.append(element('span', 'Your searches will appear here.', 'muted'));
  for (const query of recentQueries) {
    const button = element('button', query, 'recent-query');
    button.addEventListener('click', () => search(query, { populate: true }));
    container.append(button);
    if (query === focusedQuery) button.focus({ preventScroll: true });
  }
}

function renderResults() {
  const report = activeReport;
  $('#search-empty').hidden = Boolean(report);
  $('#results').hidden = !report;
  $('#result-note').hidden = !report;
  for (const button of document.querySelectorAll('[data-mode]')) {
    button.setAttribute('aria-pressed', String(button.dataset.mode === mode));
  }
  if (!report) {
    $('#results').replaceChildren();
    $('#results-heading').textContent = 'The results live here.';
    $('#result-total').textContent = 'Ready';
    $('#snapshot-query').textContent = 'Waiting for your first query';
    for (const selector of ['#exact-count', '#partial-count', '#exact-time', '#partial-time']) $(selector).textContent = '—';
    return;
  }
  $('#results-heading').textContent = `Results for “${report.query}”`;
  $('#snapshot-query').textContent = `Query / ${report.query}`;
  for (const [index, prefix] of [['inverted', 'exact'], ['ngram', 'partial']]) {
    $(`#${prefix}-count`).textContent = report[index].results.length;
    $(`#${prefix}-time`).textContent = `${report[index].time_ms.toFixed(4)} ms`;
  }
  const results = report[mode].results;
  $('#result-total').textContent = `${results.length} ${results.length === 1 ? 'match' : 'matches'}`;
  const container = $('#results');
  container.replaceChildren();
  if (!results.length) container.append(element('p', 'No matches in this index. Try the other index, a shorter fragment, or a different keyword.', 'empty-results'));
  results.forEach((result, position) => {
    const card = element('article', '', 'result-card');
    const body = element('div', '', 'result-content');
    const heading = element('h3', '');
    const source = element('button', result.title, 'source-link');
    source.addEventListener('click', () => openDocument(result.id));
    heading.append(source);
    const terms = element('div', '', 'term-list');
    for (const [term, frequency] of Object.entries(result.frequencies)) terms.append(element('span', `${term}: ${frequency}`, 'term'));
    body.append(heading, element('p', result.preview, 'result-preview'), terms);
    card.append(element('span', String(position + 1).padStart(2, '0'), 'result-number'), body,
      element('span', `Total frequency ${result.score}`, 'score'));
    container.append(card);
  });
}

function renderCoverage() {
  const report = reports.find((entry) => entry.query === coverageQuery) || reports[0];
  $('#coverage-body').replaceChildren();
  if (!report) return;
  coverageQuery = report.query;
  $('#coverage-heading').textContent = `Coverage for “${report.query}”`;
  const exact = new Map(report.inverted.results.map((result) => [result.id, result]));
  const partial = new Map(report.ngram.results.map((result) => [result.id, result]));
  const merged = new Map([...exact, ...partial]);
  for (const [id, result] of merged) {
    const row = element('tr', '');
    const name = element('th', '');
    name.scope = 'row';
    const link = element('button', result.title, 'coverage-link');
    link.addEventListener('click', () => openDocument(id));
    name.append(link);
    row.append(name, element('td', exact.has(id) ? String(exact.get(id).score) : '0'),
      element('td', partial.has(id) ? String(partial.get(id).score) : '0'));
    $('#coverage-body').append(row);
  }
  if (!merged.size) {
    const row = element('tr', '');
    const cell = element('td', 'Neither index retrieved any documents.');
    cell.colSpan = 3;
    row.append(cell);
    $('#coverage-body').append(row);
  }
}

function renderBenchmarks() {
  $('#benchmark-empty').hidden = reports.length > 0;
  $('#benchmark-report').hidden = reports.length === 0;
  $('#benchmark-body').replaceChildren();
  $('#coverage-query').replaceChildren();
  for (const report of reports) {
    const row = element('tr', '');
    const name = element('th', '');
    name.scope = 'row';
    const link = element('button', report.query, 'query-link');
    link.addEventListener('click', () => search(report.query, { populate: true }));
    name.append(link);
    const partialIds = new Set(report.ngram.results.map((result) => result.id));
    const shared = report.inverted.results.filter((result) => partialIds.has(result.id)).length;
    row.append(name, ...[report.inverted.results.length, report.ngram.results.length,
      `${report.inverted.time_ms.toFixed(4)} ms`, `${report.ngram.time_ms.toFixed(4)} ms`, shared]
      .map((value) => element('td', String(value))));
    $('#benchmark-body').append(row);
    const option = element('option', report.query);
    option.value = report.query;
    $('#coverage-query').append(option);
  }
  if (!reports.some((report) => report.query === coverageQuery)) coverageQuery = reports[0]?.query || '';
  $('#coverage-query').value = coverageQuery;
  renderCoverage();
}

async function refreshCollection({ invalidateSearch = true } = {}) {
  const request = ++collectionRequest;
  const data = await api('/api/documents');
  if (request !== collectionRequest) return;
  documents = data.documents;
  const signature = documents.map((doc) => doc.id).sort().join(',');
  if (collectionSignature !== null && collectionSignature !== signature) {
    // A ledger must not silently compare timings from different collection sizes.
    collectionVersion += 1;
    if (invalidateSearch) searchVersion += 1;
    reports = [];
    activeReport = null;
    if (invalidateSearch) setSearchBusy(false);
    renderResults();
    renderBenchmarks();
  }
  collectionSignature = signature;
  $('#nav-count').textContent = data.stats.documents;
  for (const [id, key] of [['document-count', 'documents'], ['stem-count', 'stems'], ['word-count', 'words'], ['gram-count', 'grams']]) {
    $(`#${id}`).textContent = data.stats[key].toLocaleString();
  }
  renderLibrary();
}

async function search(query, { refresh = false, populate = false } = {}) {
  query = query.trim();
  if (!query) { $('#query').focus(); return false; }
  const version = ++searchVersion;
  let collection = collectionVersion;
  currentQuery = query;
  if (populate) $('#query').value = query;
  if (!refresh) goToSearch();
  setSearchBusy(true);
  $('#results').hidden = true;
  $('#search-empty').hidden = true;
  $('#results-heading').textContent = 'Searching both indexes…';
  status('Running your query through both indexes…');
  try {
    const report = await api(`/api/search?q=${encodeURIComponent(query)}`);
    if (version !== searchVersion || collection !== collectionVersion) return false;
    if (report.collection_ids.join(',') !== collectionSignature) {
      await refreshCollection({ invalidateSearch: false });
      if (version !== searchVersion) return false;
      collection = collectionVersion;
      if (report.collection_ids.join(',') !== collectionSignature) {
        throw new Error('The collection changed during this search. Run the query again.');
      }
    }
    activeReport = report;
    reports = [report, ...reports.filter((entry) => entry.query !== query)].slice(0, 20);
    recentQueries = [query, ...recentQueries.filter((entry) => entry !== query)].slice(0, 20);
    renderResults();
    renderBenchmarks();
    renderRecent();
    status(`Compared both indexes for “${query}”.`);
    return true;
  } catch (error) {
    if (version === searchVersion) {
      currentQuery = activeReport?.query || '';
      renderResults();
      status(error.message, true);
    }
    return false;
  } finally {
    if (version === searchVersion) {
      setSearchBusy(false);
    }
  }
}

async function mutate(action, message) {
  if (mutating) return;
  mutating = true;
  const controls = [...document.querySelectorAll('[data-mutation], #add-dialog input, #add-dialog textarea')];
  controls.forEach((control) => { control.disabled = true; });
  status('Saving sources and updating indexes…');
  try {
    await action();
    await refreshCollection();
    const refreshed = !currentQuery || await search(currentQuery, { refresh: true });
    $('#add-dialog').close();
    if (refreshed) status(message);
  } catch (error) {
    await refreshCollection().catch(() => {});
    status(error.message, true);
  } finally {
    controls.forEach((control) => { control.disabled = false; });
    mutating = false;
  }
}

function addDocument(doc) {
  return api('/api/documents', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(doc) });
}

window.addEventListener('hashchange', route);
$('.skip-link').addEventListener('click', (event) => {
  event.preventDefault();
  $('#main-content').focus();
});
$('#search-form').addEventListener('submit', (event) => { event.preventDefault(); search($('#query').value); });
$('#library-filter').addEventListener('input', renderLibrary);
$('#coverage-query').addEventListener('change', (event) => { coverageQuery = event.target.value; renderCoverage(); });
for (const button of document.querySelectorAll('[data-mode]')) {
  button.addEventListener('click', () => { mode = button.dataset.mode; renderResults(); });
}
for (const button of document.querySelectorAll('[data-query]')) {
  button.addEventListener('click', () => search(button.dataset.query, { populate: true }));
}
for (const button of document.querySelectorAll('[data-open-add]')) {
  button.addEventListener('click', () => { $('#dialog-status').textContent = ''; $('#add-dialog').showModal(); });
}
for (const button of document.querySelectorAll('[data-close]')) {
  button.addEventListener('click', () => $(`#${button.dataset.close}`).close());
}
$('#add-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const doc = { title: $('#title').value, text: $('#text').value };
  mutate(async () => { await addDocument(doc); event.target.reset(); }, 'Document added.');
});
$('#upload-form').addEventListener('submit', (event) => {
  event.preventDefault();
  const files = new FormData(event.target);
  mutate(async () => { await api('/api/upload', { method: 'POST', body: files }); event.target.reset(); }, 'Documents uploaded.');
});
$('#load-samples').addEventListener('click', () => {
  mutate(async () => {
    const data = await api('/api/documents');
    const titles = new Set(data.documents.map((doc) => doc.title));
    for (const doc of samples) if (!titles.has(doc.title)) await addDocument(doc);
  }, 'Example collection ready.');
});
document.addEventListener('keydown', (event) => {
  if ($('#add-dialog').open || $('#reader-dialog').open) return;
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault();
    goToSearch();
    $('#query').focus();
  }
});

route();
refreshCollection().catch((error) => status(error.message, true));
