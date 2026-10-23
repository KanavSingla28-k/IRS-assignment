"""Run with: .venv/bin/python app.py"""

from pathlib import Path

from flask import Flask, jsonify, render_template, request
from urllib.parse import urlsplit
from werkzeug.exceptions import RequestEntityTooLarge

from search_engine import SearchEngine


def create_app(storage_path=None):
    app = Flask(__name__)
    app.config['MAX_CONTENT_LENGTH'] = 5 * 1024 * 1024
    engine = SearchEngine(storage_path if storage_path is not None
                          else Path(__file__).parent / 'data' / 'documents.json')

    @app.before_request
    def reject_cross_origin_writes():
        if request.method not in ('POST', 'PUT', 'PATCH', 'DELETE'):
            return None
        origin = request.headers.get('Origin')
        expected = urlsplit(request.host_url)
        actual = urlsplit(origin) if origin else None
        if (request.headers.get('Sec-Fetch-Site') == 'cross-site'
                or (actual and (actual.scheme, actual.netloc) != (expected.scheme, expected.netloc))):
            return jsonify(error='Cross-origin document changes are not allowed.'), 403
        return None

    @app.errorhandler(ValueError)
    def invalid_input(error):
        return jsonify(error=str(error)), 400

    @app.errorhandler(RequestEntityTooLarge)
    def too_large(error):
        return jsonify(error='Request exceeds the 5 MB upload limit.'), 413

    @app.get('/')
    def home():
        return render_template('index.html')

    @app.get('/api/documents')
    def documents():
        return jsonify(documents=engine.list_documents(), stats=engine.stats())

    @app.post('/api/documents')
    def add_document():
        data = request.get_json(silent=True)
        if not isinstance(data, dict):
            raise ValueError('Send a JSON object with title and text.')
        doc = engine.add_document(data.get('title'), data.get('text'))
        return jsonify(document=doc), 201

    @app.post('/api/upload')
    def upload():
        files = request.files.getlist('files')
        if not files or len(files) > 30:
            raise ValueError('Select between 1 and 30 UTF-8 .txt files.')
        pending = []
        # Validate the entire upload before adding any document.
        for file in files:
            name = (file.filename or '').replace('\\', '/').rsplit('/', 1)[-1]
            if not name.lower().endswith('.txt'):
                raise ValueError('Only .txt files are supported.')
            try:
                text = file.read().decode('utf-8-sig')
            except UnicodeDecodeError as error:
                raise ValueError(f'{name} is not valid UTF-8 text.') from error
            if not text.strip():
                raise ValueError(f'{name} is empty.')
            pending.append((name, text))
        added = [engine.add_document(name, text) for name, text in pending]
        return jsonify(documents=added), 201

    @app.get('/api/search')
    def search():
        query = request.args.get('q', '')
        if len(query) > 500:
            raise ValueError('Use a query of at most 500 characters.')
        with engine.lock:
            report = engine.compare(query)
            report['collection_ids'] = sorted(engine.documents)
        return jsonify(report)

    return app


if __name__ == '__main__':
    create_app().run(host='127.0.0.1', port=5000, debug=False)
