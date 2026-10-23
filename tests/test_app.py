import io
from html.parser import HTMLParser
import tempfile
import unittest
from pathlib import Path

from app import create_app


class AppTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.app = create_app(Path(self.temp.name) / 'documents.json')
        self.client = self.app.test_client()

    def test_home_and_empty_collection(self):
        self.assertEqual(self.client.get('/').status_code, 200)
        data = self.client.get('/api/documents').get_json()
        self.assertEqual(data['documents'], [])
        self.assertEqual(data['stats']['documents'], 0)

    def test_add_search_and_compare(self):
        response = self.client.post('/api/documents', json={
            'title': 'Computing', 'text': 'Computer computers'})
        self.assertEqual(response.status_code, 201)
        data = self.client.get('/api/search?q=compu').get_json()
        self.assertEqual(data['inverted']['results'], [])
        self.assertEqual(data['ngram']['results'][0]['score'], 2)
        self.assertEqual(self.client.get('/api/documents').get_json()['stats']['documents'], 1)

    def test_multiple_uploads_update_index(self):
        response = self.client.post('/api/upload', data={'files': [
            (io.BytesIO(b'Cats cats'), 'cats.txt'),
            (io.BytesIO(b'Dogs and cats'), 'dogs.txt')]})
        self.assertEqual(response.status_code, 201)
        data = self.client.get('/api/search?q=cats').get_json()
        self.assertEqual(len(data['inverted']['results']), 2)

    def test_upload_validation_is_atomic(self):
        for content, filename in [(b'\xff', 'bad.txt'), (b'hello', 'bad.pdf'), (b' ', 'empty.txt')]:
            response = self.client.post('/api/upload', data={'files': [
                (io.BytesIO(b'Good text'), 'good.txt'), (io.BytesIO(content), filename)]})
            self.assertEqual(response.status_code, 400)
            self.assertEqual(self.client.get('/api/documents').get_json()['documents'], [])

    def test_bad_requests_return_json_errors(self):
        for body in ({}, [], {'title': 123, 'text': 'word'}, {'title': 'One', 'text': ''}):
            response = self.client.post('/api/documents', json=body)
            self.assertEqual(response.status_code, 400)
            self.assertIn('error', response.get_json())
        self.assertEqual(self.client.post('/api/upload').status_code, 400)
        self.assertEqual(self.client.get('/api/search?q=' + 'a' * 501).status_code, 400)

    def test_cross_origin_mutations_are_rejected(self):
        response = self.client.post('/api/documents',
                                    json={'title': 'Bad', 'text': 'Text'},
                                    headers={'Origin': 'https://untrusted.example'})
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.client.get('/api/documents').get_json()['documents'], [])

    def test_html_elements_are_properly_nested(self):
        class NestingParser(HTMLParser):
            def __init__(self):
                super().__init__()
                self.stack = []

            def handle_starttag(self, tag, attrs):
                if tag not in {'meta', 'link', 'input', 'br'}:
                    self.stack.append(tag)

            def handle_endtag(self, tag):
                if not self.stack or self.stack.pop() != tag:
                    raise AssertionError(f'Invalid closing tag: {tag}')

        parser = NestingParser()
        parser.feed(self.client.get('/').get_data(as_text=True))
        self.assertEqual(parser.stack, [])

    def test_workbench_has_search_library_comparison_and_accessible_viewers(self):
        html = self.client.get('/').get_data(as_text=True)
        for component in ('id="search-view"', 'id="library-view"', 'id="compare-view"',
                          'id="library-filter"', 'id="benchmark-body"',
                          'id="document-content"', 'id="add-dialog"',
                          'id="reader-dialog"', 'aria-label="Workbench navigation"',
                          'aria-label="Search documents"'):
            self.assertIn(component, html)
        self.assertNotIn('id="sidebar"', html)
        self.assertNotIn('id="conversation"', html)

    def test_search_includes_collection_ids_for_cross_tab_consistency(self):
        first = self.client.post('/api/documents', json={'title': 'One', 'text': 'Computers'}).get_json()['document']
        self.assertEqual(self.client.get('/api/search?q=computers').get_json()['collection_ids'], [first['id']])
        second = self.client.post('/api/documents', json={'title': 'Two', 'text': 'Computers'}).get_json()['document']
        report = self.client.get('/api/search?q=computers').get_json()
        self.assertEqual(report['collection_ids'], sorted([first['id'], second['id']]))
        self.assertEqual(len(report['inverted']['results']), 2)

    def test_size_limit_returns_json(self):
        self.app.config['MAX_CONTENT_LENGTH'] = 100
        response = self.client.post('/api/documents', json={'title': 'Big', 'text': 'a' * 200})
        self.assertEqual(response.status_code, 413)
        self.assertIn('error', response.get_json())


if __name__ == '__main__':
    unittest.main()
