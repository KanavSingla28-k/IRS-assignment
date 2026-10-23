"""Optional workbench regression test. Requires agent-browser and the workbench JS.

Run with .venv/bin/python tests/browser_smoke.py. All documents and uploads live
in a temporary directory; the application's production collection is never used.
"""

import json
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

from werkzeug.serving import make_server

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import create_app


def run():
    # Load the installed CLI's workflow before issuing browser commands.
    subprocess.run(['agent-browser', 'skills', 'get', 'core'],
                   check=True, capture_output=True, text=True, timeout=30)
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        server = make_server('127.0.0.1', 0, create_app(root / 'documents.json'), threaded=True)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        session = 'workbench-' + root.name

        def browser(*args, timeout=30):
            result = subprocess.run(['agent-browser', '--session', session, *args],
                                    capture_output=True, text=True, timeout=timeout)
            if result.returncode:
                raise AssertionError(f'agent-browser {args!r}\n{result.stdout}{result.stderr}')
            return result.stdout.strip()

        def check(*expressions):
            assertions = ''.join(
                f'if (!({expression})) throw new Error({json.dumps("Browser assertion failed: " + expression)});'
                for expression in expressions
            )
            browser('eval', f'(() => {{ {assertions} return "PASS"; }})()')

        def wait(expression):
            browser('wait', '--fn', expression)

        needs_snapshot = True
        current_route = None

        def snapshot():
            nonlocal needs_snapshot
            if needs_snapshot:
                browser('snapshot', '-i')
                needs_snapshot = False

        def action(command, selector, *args):
            nonlocal needs_snapshot
            # Reuse the snapshot while filling a form; take a fresh one after
            # navigation, filtering, or other UI changes. CLI actions themselves
            # wait for actionability; do not force-click or click through eval.
            snapshot()
            browser(command, selector, *args)
            needs_snapshot = command != 'fill' or selector == '#library-filter'

        def press(key):
            nonlocal needs_snapshot
            snapshot()
            browser('press', key)
            needs_snapshot = True

        def route(name):
            nonlocal current_route
            if current_route == name:
                return
            action('click', f'.main-nav [data-route="{name}"]')
            views = ' && '.join(
                f'document.querySelector("#{view}-view").hidden === {str(view != name).lower()}'
                for view in ('search', 'library', 'compare')
            )
            wait(f'location.hash === "#{name}" && {views} && '
                 f'document.querySelector(\'.main-nav [data-route="{name}"]\').getAttribute("aria-current") === "page"')
            current_route = name

        def status(message):
            wait(f'document.querySelector("#status").textContent.trim() === {json.dumps(message)}')

        def search(query):
            route('search')
            action('fill', '#query', query)
            browser('eval', 'window.smokeBefore = window.smokeSearches')
            action('click', '#search-submit')
            wait('window.smokeSearches === window.smokeBefore + 1 && window.smokePending === 0 && '
                 f'document.querySelector("#status").textContent.trim() === {json.dumps(f"Compared both indexes for “{query}”.")}')

        def ledger(queries):
            expected = json.dumps(sorted(queries))
            check(
                f'JSON.stringify([...document.querySelectorAll("#benchmark-body .query-link")].map(n => n.textContent.trim()).sort()) === JSON.stringify({expected})',
                f'document.querySelectorAll("#benchmark-body tr").length === {len(queries)}',
                'document.querySelectorAll("#coverage-query option").length === document.querySelectorAll("#benchmark-body tr").length',
            )

        def select_coverage(query):
            # The workbench's option.value is the query itself.
            action('select', '#coverage-query', query)
            wait(f'document.querySelector("#coverage-query").selectedOptions[0].textContent.trim() === {json.dumps(query)}')

        def frequency(title, exact, partial):
            check('(() => { const row = [...document.querySelectorAll("#coverage-body tr")].find('
                  f'n => n.cells[0].textContent.trim() === {json.dumps(title)}); '
                  f'return row && row.cells[1].textContent.trim() === "{exact}" '
                  f'&& row.cells[2].textContent.trim() === "{partial}"; }})()')

        def open_add():
            action('click', '.masthead [data-open-add]')
            check('document.querySelector("#add-dialog").matches(":modal")')

        def mutation_done(message, count, draft):
            wait(f'document.querySelector("#status").textContent.trim() === {json.dumps(message)} '
                 f'&& !document.querySelector("#add-dialog").open && window.smokePending === 0 '
                 f'&& document.querySelector("#document-count").textContent.trim() === "{count}"')
            check(
                f'document.querySelector("#query").value === {json.dumps(draft)}',
                f'document.querySelector("#partial-count").textContent.trim() === "{count - 2}"',
                'document.querySelector("#exact-count").textContent.trim() === "0"',
            )
            route('compare')
            ledger(['compu'])
            select_coverage('compu')

        try:
            browser('open', f'http://127.0.0.1:{server.server_port}')
            browser('set', 'viewport', '1440', '1000')
            browser('snapshot', '-i')
            wait('document.querySelector("#document-count").textContent.trim() === "0"')
            check(
                '!document.querySelector("#search-view").hidden',
                'document.querySelector("#library-view").hidden && document.querySelector("#compare-view").hidden',
                'document.querySelector(\'[data-mode="inverted"]\').getAttribute("aria-pressed") === "true"',
            )
            route('library')
            check('document.querySelectorAll("#library-grid .library-card").length === 0')
            route('compare')
            check('!document.querySelector("#benchmark-empty").hidden')
            route('search')

            # Observe real fetches; the optional response gate makes the draft
            # race deterministic rather than depending on subprocess timing.
            browser('eval', '''(() => {
                const original = window.fetch.bind(window);
                window.smokeSearches = 0;
                window.smokePending = 0;
                window.fetch = async (...args) => {
                    const url = new URL(args[0] instanceof Request ? args[0].url : args[0], location.href);
                    const search = url.pathname === '/api/search';
                    if (search) { window.smokeSearches++; window.smokePending++; }
                    try {
                        const response = await original(...args);
                        if (search && window.smokeHold) {
                            await new Promise(resolve => { window.smokeRelease = resolve; });
                        }
                        return response;
                    } finally { if (search) window.smokePending--; }
                };
            })()''')
            action('click', '#load-samples')
            status('Example collection ready.')
            wait('document.querySelector("#document-count").textContent.trim() === "4"')
            action('click', '#load-samples')
            status('Example collection ready.')
            wait('!document.querySelector("#load-samples").disabled')
            route('library')
            check('document.querySelectorAll("#library-grid .library-card").length === 4')
            action('fill', '#library-filter', 'COMPUTER SCIENCE')
            wait('document.querySelectorAll("#library-grid .library-card").length === 1')
            action('click', '#library-grid .library-card')
            check('document.querySelector("#reader-dialog").matches(":modal")')
            check('document.querySelector("#document-content").textContent === "Computer science studies computers and computation. Computer systems use algorithms to process information. Computing connects mathematics and engineering."')
            action('click', '[data-close="reader-dialog"]')
            check('!document.querySelector("#reader-dialog").open')
            action('fill', '#library-filter', 'no-such-source')
            wait('document.querySelectorAll("#library-grid .library-card").length === 0')
            action('fill', '#library-filter', '')
            wait('document.querySelectorAll("#library-grid .library-card").length === 4')

            route('search')
            action('click', '[data-query="compu"]')
            status('Compared both indexes for “compu”.')
            check(
                'document.querySelector("#exact-count").textContent.trim() === "0"',
                'document.querySelector("#partial-count").textContent.trim() === "2"',
                'document.querySelectorAll("#results .source-link").length === 0',
            )
            browser('eval', 'window.smokeModeRequests = window.smokeSearches')
            action('click', '[data-mode="ngram"]')
            check(
                'document.querySelectorAll("#results .source-link").length === 2',
                'document.querySelector(\'[data-mode="ngram"]\').getAttribute("aria-pressed") === "true"',
            )
            action('click', '#results .source-link')
            check('document.querySelector("#reader-dialog").matches(":modal")')
            check('document.querySelector("#document-content").textContent.includes("Computer science")')
            press('Escape')
            check('!document.querySelector("#reader-dialog").open')
            action('click', '[data-mode="inverted"]')
            check(
                'document.querySelectorAll("#results .source-link").length === 0',
                'window.smokeSearches === window.smokeModeRequests',
            )
            route('compare')
            ledger(['compu'])
            select_coverage('compu')
            check('document.querySelectorAll("#coverage-body tr").length === 2')
            frequency('01 · Computer science', 0, 5)
            frequency('04 · Partial word retrieval', 0, 2)

            for query in ('computer', 'search engine', 'compu'):
                search(query)
            check(
                'document.querySelectorAll(".recent-query").length === 3',
                'new Set([...document.querySelectorAll(".recent-query")].map(n => n.textContent.trim())).size === 3',
            )
            search('computer')
            action('click', '[data-mode="inverted"]')
            check('document.querySelectorAll("#results .source-link").length === 2')
            route('compare')
            ledger(['compu', 'computer', 'search engine'])
            select_coverage('compu')
            frequency('01 · Computer science', 0, 5)
            select_coverage('computer')
            frequency('01 · Computer science', 5, 3)
            frequency('04 · Partial word retrieval', 2, 1)
            browser('eval', 'window.smokeBefore = window.smokeSearches; window.smokeRerunQuery = document.querySelector("#benchmark-body .query-link").textContent.trim()')
            action('click', '#benchmark-body .query-link')
            wait('location.hash === "#search" && !document.querySelector("#search-view").hidden && window.smokeSearches === window.smokeBefore + 1 && window.smokePending === 0 '
                 '&& document.querySelector("#status").textContent.trim() === `Compared both indexes for “${window.smokeRerunQuery}”.`')
            current_route = 'search'
            check(
                'document.querySelector("#query").value === window.smokeRerunQuery',
                'document.activeElement === document.querySelector("#query")',
                'document.querySelectorAll(".recent-query").length === 3',
            )

            # A collection mutation must discard older measurements, rerun the
            # active query (not the input draft), and render source strings safely.
            search('compu')
            draft = 'An unfinished draft'
            action('fill', '#query', draft)
            open_add()
            action('click', '[data-close="add-dialog"]')
            check('!document.querySelector("#add-dialog").open')
            open_add()
            action('fill', '#title', 'Rejected source')
            action('fill', '#text', '   ')
            action('click', '#add-form button[type="submit"]')
            wait('document.querySelector("#dialog-status").textContent.includes("Document text cannot be empty")')
            check('document.querySelector("#add-dialog").matches(":modal")')
            check('document.querySelector("#document-count").textContent.trim() === "4"')
            title = 'New source <img src=x onerror="window.smokeXSS=true">'
            text = 'Computers computers. <img src=x onerror="window.smokeXSS=true"> ' + 'Full source text. ' * 25
            action('fill', '#title', title)
            action('fill', '#text', text)
            browser('eval', 'window.smokeHold = true; window.smokeRelease = null')
            action('click', '#add-form button[type="submit"]')
            wait('typeof window.smokeRelease === "function"')
            check('document.querySelectorAll("#benchmark-body tr").length === 0')
            check(f'document.querySelector("#query").value === {json.dumps(draft)}')
            browser('eval', 'window.smokeHold = false; window.smokeRelease()')
            mutation_done('Document added.', 5, draft)
            frequency(title, 0, 2)
            route('library')
            check('document.querySelectorAll("#library-grid .library-card").length === 5')
            action('fill', '#library-filter', 'New source')
            action('click', '#library-grid .library-card')
            check(
                f'document.querySelector("#document-title").textContent === {json.dumps(title)}',
                f'document.querySelector("#document-content").textContent === {json.dumps(text.strip())}',
                '!document.querySelector("#reader-dialog img") && !window.smokeXSS',
            )
            press('Escape')
            action('fill', '#library-filter', '')
            route('search')
            action('click', '[data-mode="ngram"]')
            check(
                'document.querySelectorAll("#results .source-link").length === 3',
                f'[...document.querySelectorAll("#results .source-link")].some(n => n.textContent === {json.dumps(title)})',
                '!document.querySelector("#results img") && !document.querySelector("#library-grid img") && !window.smokeXSS',
            )

            search('search engine')
            search('compu')
            upload_draft = 'Keep this upload draft'
            action('fill', '#query', upload_draft)
            upload = root / 'notes.txt'
            upload.write_text('Computers computers computers. Search engine retrieval notes', encoding='utf-8')
            open_add()
            action('upload', '#files', str(upload))
            browser('eval', 'window.smokeHold = true; window.smokeRelease = null')
            action('click', '#upload-form button[type="submit"]')
            wait('typeof window.smokeRelease === "function"')
            check('document.querySelectorAll("#benchmark-body tr").length === 0')
            browser('eval', 'window.smokeHold = false; window.smokeRelease()')
            mutation_done('Documents uploaded.', 6, upload_draft)
            frequency('notes.txt', 0, 3)
            route('library')
            check('document.querySelectorAll("#library-grid .library-card").length === 6')
            action('fill', '#library-filter', 'notes.txt')
            action('click', '#library-grid .library-card')
            check('document.querySelector("#document-content").textContent === "Computers computers computers. Search engine retrieval notes"')
            press('Escape')
            action('fill', '#library-filter', '')

            invalid = root / 'bad.txt'
            invalid.write_bytes(b'\xff')
            open_add()
            action('upload', '#files', str(invalid))
            action('click', '#upload-form button[type="submit"]')
            wait('document.querySelector("#dialog-status").textContent.includes("not valid UTF-8")')
            check('document.querySelector("#add-dialog").matches(":modal")')
            check('document.querySelectorAll("#library-grid .library-card").length === 6')
            press('Escape')
            check('!document.querySelector("#add-dialog").open')
            route('compare')
            ledger(['compu'])

            search('indexing')
            route('search')
            browser('eval', 'window.smokeHold = true; window.smokeRelease = null')
            action('fill', '#query', 'retrieval')
            action('click', '#search-submit')
            wait('typeof window.smokeRelease === "function"')
            action('fill', '#query', 'My next query draft')
            check(
                'window.smokePending === 1',
                'document.querySelectorAll("[data-mode]").length === 2 && '
                '[...document.querySelectorAll("[data-mode]")].every(button => button.disabled)',
            )
            browser('eval', 'window.smokeHold = false; window.smokeRelease()')
            status('Compared both indexes for “retrieval”.')
            check(
                'document.querySelector("#query").value === "My next query draft"',
                '[...document.querySelectorAll("[data-mode]")].every(button => !button.disabled)',
            )

            # Keep each CDP evaluation short: the CLI can disconnect during
            # long awaited evaluations. Submit real forms, then wait separately.
            needs_snapshot = True
            snapshot()
            for number in range(21):
                query = f'ledgerprobe{number:02d}'
                browser('eval', f'document.querySelector("#query").value = {json.dumps(query)}; document.querySelector("#search-form").requestSubmit()')
                status(f'Compared both indexes for “{query}”.')
            needs_snapshot = True
            route('compare')
            ledger([f'ledgerprobe{number:02d}' for number in range(1, 21)])
            search('ledgerprobe10')
            route('compare')
            ledger([f'ledgerprobe{number:02d}' for number in range(1, 21)])
            select_coverage('ledgerprobe10')
            check('document.querySelector("#coverage-body").textContent.includes("Neither index retrieved any documents.")')
            route('search')
            browser('eval', 'window.smokeBefore = window.smokeSearches; window.smokeRerunQuery = document.querySelector(".recent-query").textContent.trim()')
            action('click', '.recent-query')
            wait('window.smokeSearches === window.smokeBefore + 1 && window.smokePending === 0 '
                 '&& document.querySelector("#status").textContent.trim() === `Compared both indexes for “${window.smokeRerunQuery}”.`')
            check('document.querySelector("#query").value === window.smokeRerunQuery')
            check('new Set([...document.querySelectorAll(".recent-query")].map(n => n.textContent.trim())).size === document.querySelectorAll(".recent-query").length')

            # Simulate another tab writing to the shared backend, without
            # invoking this page's mutation handler or changing earlier fixtures.
            browser('eval', '''(async () => {
                window.smokeOldStats = ['stem-count', 'word-count', 'gram-count'].map(
                    id => Number(document.getElementById(id).textContent.replaceAll(',', '')));
                const response = await fetch('/api/documents', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ title: 'External source', text: 'externalsource computers' })
                });
                if (response.status !== 201) {
                    throw new Error(`External add failed: ${response.status} ${await response.text()}`);
                }
                const data = await response.json();
                if (data.document.title !== 'External source') throw new Error('Unexpected external document');
                return 'PASS: external document added';
            })()''')
            search('externalsource')
            check(
                'document.querySelector("#document-count").textContent.trim() === "7"',
                'document.querySelector("#nav-count").textContent.trim() === "7"',
                'document.querySelectorAll("#library-grid .library-card").length === 7',
                '["stem-count", "word-count", "gram-count"].every((id, index) => '
                'Number(document.getElementById(id).textContent.replaceAll(",", "")) > window.smokeOldStats[index])',
                'document.querySelector("#exact-count").textContent.trim() === "1"',
                'document.querySelector("#partial-count").textContent.trim() === "1"',
            )
            route('compare')
            ledger(['externalsource'])
            select_coverage('externalsource')
            frequency('External source', 1, 1)
            route('search')
            action('click', '[data-mode="inverted"]')
            check('document.querySelectorAll("#results .source-link").length === 1 && '
                  'document.querySelector("#results .source-link").textContent === "External source"')
            action('click', '#results .source-link')
            check(
                'document.querySelector("#reader-dialog").matches(":modal")',
                'document.querySelector("#document-title").textContent === "External source"',
                'document.querySelector("#document-content").textContent === "externalsource computers"',
            )
            press('Escape')
            route('library')
            action('fill', '#library-filter', 'External source')
            wait('document.querySelectorAll("#library-grid .library-card").length === 1')
            action('fill', '#library-filter', '')
            wait('document.querySelectorAll("#library-grid .library-card").length === 7')

            # The skip link must focus main content without replacing the hash
            # route. Focus it first so the off-screen keyboard link is visible.
            action('focus', '.skip-link')
            action('click', '.skip-link')
            wait('document.activeElement === document.querySelector("#main-content") && location.hash === "#library"')
            check(
                '!document.querySelector("#library-view").hidden',
                'document.querySelector("#search-view").hidden && document.querySelector("#compare-view").hidden',
            )

            browser('set', 'viewport', '390', '844')
            for view in ('search', 'library', 'compare'):
                route(view)
                check('document.documentElement.scrollWidth <= innerWidth')
            route('library')
            check('document.querySelectorAll("#library-grid .library-card").length === 7')
            action('click', '#library-grid .library-card')
            check(
                'document.querySelector("#reader-dialog").matches(":modal")',
                'document.documentElement.scrollWidth <= innerWidth',
                'document.querySelector("#reader-dialog").getBoundingClientRect().right <= innerWidth',
                'document.querySelector("#reader-dialog").getBoundingClientRect().left >= 0',
            )
            press('Escape')
            check('!document.querySelector("#reader-dialog").open')
            check('!window.smokeXSS')
            errors = browser('errors')
            assert not errors, errors
            print('Browser smoke passed: workbench routes, samples, library, reader, modes, '
                  'frequencies, ledger, history, safe rendering, mutation refresh, drafts, '
                  'uploads, native errors, external collection sync, focus and mobile overflow.')
        finally:
            try:
                browser('close')
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)


if __name__ == '__main__':
    run()
