# Retrieval Desk — Assignment 1 workbench variation

**Branch:** `variation/retrieval-workbench` · The original project/chat interface remains on `main`.

This variation replaces the sidebar-and-conversation layout with a top-navigation retrieval workbench, a filterable document library, and a dedicated comparison ledger. Search algorithms, preprocessing, upload validation, ranking, and local storage remain compatible with the original app.

A local Python/Flask application implementing both Q1 and Q2. The browser interface lets you add documents, upload several text files, inspect term frequencies, and compare exact and partial-word retrieval side by side.

## Run

Requires Python 3.10+.

```sh
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Open **http://127.0.0.1:5000**. On macOS, if port 5000 is occupied (for example by AirPlay Receiver), use:

```sh
python -m flask --app 'app:create_app()' run --host 127.0.0.1 --port 5001
```

No API key, database service, or NLTK corpus download is needed. Dependencies are Flask and NLTK; the stop-word list is embedded and only NLTK's PorterStemmer is used.

## Demonstration

1. Click **Load example collection** in Search to add four short documents. Repeating this button before your first search does not duplicate the examples. Browse them in **Library** or open a result title to read a source.
2. Search **computer**: the exact index uses the stem `comput`; the N-gram index matches the literal substring `computer`. Both retrieve relevant documents, but frequencies can differ because exact mode also counts `computing`.
3. Search **compu**: the inverted index finds no exact stem, while the N-gram index retrieves documents containing `computer`, `computers`, or `computing`.
4. Search **search engine**: both indexes use OR matching across distinct query terms. Every result shows each processed query term's frequency, including zeros, and its total frequency score.
5. Search **in**: partial mode can find `indexing` and `information`; exact mode removes this stop word. Partial query fragments are deliberately not stop-word filtered.
6. Add a document or upload multiple UTF-8 `.txt` files, then repeat your query. Both indexes update immediately; any current results are refreshed automatically.

### The workbench

- **Search:** a prominent query console, live collection statistics, ranked results, and an index timing snapshot. Use the **Inverted index** and **N-gram index** controls to switch result sets without rerunning the query. The default is Inverted, so `compu` initially shows no matches; switch to N-gram to see its partial matches.
- **Library:** filter documents by title (case-insensitive), inspect previews, and open the full-text source reader. Documents are added with the **Add documents** dialog, through pasted text or multiple uploads.
- **Compare:** the latest real measurement for each of up to 20 distinct queries in this page session. Compare result counts, median times, and the number of shared documents. Select a query to inspect document-by-document total frequencies; zero means the index did not retrieve that document. Click a query to rerun it.
- **Collection consistency:** adding sources clears the benchmark ledger before refreshing the active query, so one ledger does not mix measurements from different document sets. Search responses carry the collection IDs captured with the measurement. If another tab adds sources, the next search synchronizes the library and statistics and resets stale measurements. If the collection changes again during synchronization, rerun the query.
- **Recent queries:** up to 20 distinct searches, kept for the page session. Rerun one with a click. Both recent queries and benchmark rows reset on reload; persisted documents do not.
- **Keyboard:** Enter submits the search, Cmd/Ctrl + K focuses the query console, and Escape closes the native document reader or add dialog. Inputs preserve query drafts during background refreshes.

Top navigation uses `#search`, `#library`, and `#compare`, including browser Back/Forward navigation. Views reflow on mobile, and wide comparison tables scroll inside their own containers. This is one shared local collection, not separate projects, an AI chatbot, or a semantic search service.

Optional real-browser regression test, using an installed `agent-browser` CLI:

```sh
python tests/browser_smoke.py
```

The browser test starts a temporary server and document store, exercises all three views, index switching, library filtering, uploads, full-text reading, safe rendering, benchmark coverage, collection synchronization, draft preservation, and mobile behavior, then shuts down. It does not modify your collection. The 21-query ledger-cap check can take several minutes in a background browser.

### Comparing query types

Run the examples below and record the live comparison table for each. Timings depend on your machine and collection; the app does not use fabricated benchmark values.

| Query type | Example | What to compare |
| --- | --- | --- |
| Exact keyword | `computer` | Retrieved titles and stemmed vs literal frequencies |
| Partial word | `compu` | Exact-mode miss vs partial-mode matches |
| Multiple terms | `search engine` | OR matches, per-term frequencies and total score |
| Short fragment | `ex` | Bigram retrieval vs exact lookup |
| Missing word | `xyznotfound` | Empty results and lookup time |

The interface reports median milliseconds over **50 warmed searches per index** using `perf_counter_ns()`. Each measured search includes query preprocessing, candidate lookup, frequency aggregation, result construction and sorting. Network, rendering, disk writes, index construction and the initial warm-up are excluded. These are warm in-process microbenchmarks, not end-to-end latency measurements. The inverted index is measured first; very small timing differences are noise, not proof that one method is always faster. Use a larger representative collection for meaningful performance conclusions.

## Implementation

### Q1: inverted index

1. Lowercase and tokenize Unicode alphanumeric words; punctuation and underscores split tokens.
2. Remove common English stop words.
3. Apply the Porter stemming algorithm (e.g. `cats → cat`, `running → run`).
4. Count stem occurrences per document.
5. Store `stem → {document_id: frequency}`.

Query preprocessing follows the same pipeline. Results match **any** term (OR), repeated processed query terms count once, and ranking is descending total frequency with title and ID tie-breaks. Only document bodies are indexed, not titles. This is term-frequency ranking, not TF-IDF or semantic search. A stem such as `comput` can itself match in exact mode: “exact” means exact *processed term*, not a literal word comparison.

### Q2: N-gram index

Retain unstemmed, non-stopword document tokens in a word-to-document frequency index. Build character-trigram postings `gram → set(words)`. Also index unigrams and bigrams for fragments shorter than three characters.

For each query fragment:

1. Lowercase and tokenize, but do **not** stem or remove stop words from query fragments. Otherwise valid fragments such as `in` or `the` would be lost.
2. Generate trigrams (or smaller grams for short fragments).
3. Intersect their word postings to obtain candidate words.
4. Verify `fragment in candidate_word` to reject words sharing grams in the wrong order or position.
5. Aggregate candidate word frequencies by document.

This implements contiguous substring search, not fuzzy/spelling-tolerant or phrase search. A matching word contributes its occurrence frequency once per fragment, regardless of how often the fragment occurs inside that word. A word matching two different fragments contributes to both fragment counts. Stop words are omitted from the document vocabulary in both indexes, so standalone stopwords are not retrievable.

### Persistence and limits

Documents are saved in `data/documents.json` (created on first addition); indexes are rebuilt at startup. Each addition writes a temporary file then atomically replaces the JSON store. A corrupt store causes an actionable startup error rather than silently discarding documents. Stop the app and move or remove the JSON file to reset the collection.

This is a **single-process educational application**. Run only one instance against a given JSON file; do not use multiple WSGI workers or overlapping processes. Thread locking coordinates one process, not independent writers. Multi-process deployment would require transactional storage such as SQLite. The development server is local-only, has no accounts or authentication, and must not be exposed publicly.

Uploads accept 1–30 UTF-8 `.txt` files, including UTF-8 BOM, with a 5 MB request limit. Every file is validated before any are added; disk failures during a multi-file upload can still leave earlier files saved. Names are display labels, never filesystem paths. User content is rendered using DOM `textContent`; cross-origin mutation requests are rejected. Query length is limited to 500 characters. JSON read access is intended for local use only.

## Files

```text
app.py                  Flask routes, upload validation and local server
search_engine.py        Preprocessing, indexes, ranking, persistence and timing
templates/index.html    Accessible search and comparison interface
static/app.js           Upload/add/search workflows and safe result rendering
static/style.css        Responsive interface styling
tests/test_engine.py    Engine and persistence tests
tests/test_app.py       API, uploads, HTML structure and request validation tests
requirements.txt        Python dependencies
```

## Tests

```sh
python -m unittest discover -s tests -v
python -m compileall -q app.py search_engine.py tests
```

Optional JavaScript syntax check (requires Node.js):

```sh
node --check static/app.js
```

Tests use temporary storage and never change the user's collection. Coverage includes stemming, stop words, exact/partial retrieval, short fragments, false-positive filtering, ranking, frequencies, duplicate query terms, immediate updates, persistence, corrupt storage, timing shape, uploads, size limits, malformed input, cross-origin writes, and HTML nesting.

## API

- `GET /api/documents` — collection and index statistics.
- `POST /api/documents` — JSON `{ "title": "Title", "text": "Document body" }`.
- `POST /api/upload` — multipart form with one or more `files` fields.
- `GET /api/search?q=compu` — both result sets and measured timings.

Each result includes document ID, title, a preview, processed query-term frequencies, and total frequency score. API validation errors return JSON with an `error` field.
