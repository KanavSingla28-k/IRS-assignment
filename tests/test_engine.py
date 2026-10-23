import tempfile
import unittest
from pathlib import Path

from search_engine import SearchEngine, preprocess


class SearchEngineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / 'documents.json'
        self.engine = SearchEngine(self.path)

    def test_preprocessing_tokenizes_removes_stopwords_and_stems(self):
        self.assertEqual(preprocess('The runners were RUNNING, and cats!'),
                         ['runner', 'run', 'cat'])

    def test_inverted_index_tracks_frequency_and_ranks_documents(self):
        first = self.engine.add_document('First', 'Cats cats running.')
        second = self.engine.add_document('Second', 'A cat sleeps.')
        results = self.engine.search('cats', 'inverted')
        self.assertEqual([r['id'] for r in results], [first['id'], second['id']])
        self.assertEqual(results[0]['frequencies'], {'cat': 2})
        self.assertEqual(self.engine.inverted_index['cat'][first['id']], 2)

    def test_partial_search_matches_substrings_not_only_shared_grams(self):
        doc = self.engine.add_document('Computing', 'Computer computers computing compute.')
        self.engine.add_document('False positive', 'comxx ompxx mput')
        self.assertEqual(self.engine.search('compu', 'inverted'), [])
        results = self.engine.search('compu', 'ngram')
        self.assertEqual([r['id'] for r in results], [doc['id']])
        self.assertEqual(results[0]['frequencies'], {'compu': 4})

    def test_short_partial_words_use_indexed_unigrams_and_bigrams(self):
        self.engine.add_document('Short', 'Indexing text')
        self.assertEqual(self.engine.search('ex', 'ngram')[0]['score'], 2)
        self.assertEqual(self.engine.search('x', 'ngram')[0]['score'], 2)

    def test_multi_term_search_uses_or_and_deduplicates_query_terms(self):
        self.engine.add_document('Animals', 'Cats cats dogs')
        self.engine.add_document('Other', 'Birds')
        result = self.engine.search('cats cat dogs missing', 'inverted')[0]
        self.assertEqual(result['frequencies'], {'cat': 2, 'dog': 1, 'miss': 0})
        self.assertEqual(result['score'], 3)

    def test_new_documents_are_immediately_searchable_and_persisted(self):
        self.engine.add_document('One', 'Searchable material')
        second = self.engine.add_document('Two', 'Searchable searchable')
        restored = SearchEngine(self.path)
        self.assertEqual(restored.search('searchable', 'inverted')[0]['id'], second['id'])
        self.assertEqual(len(restored.search('search', 'ngram')), 2)

    def test_empty_and_stopword_queries_return_no_matches(self):
        self.engine.add_document('One', 'Some text')
        for mode in ('inverted', 'ngram'):
            for query in ('', '!!!'):
                self.assertEqual(self.engine.search(query, mode), [])

    def test_partial_fragments_are_not_discarded_as_stopwords(self):
        self.engine.add_document('One', 'Indexing forest theory')
        for fragment in ('in', 'or', 'the'):
            self.assertTrue(self.engine.search(fragment, 'ngram'))
        self.assertEqual(self.engine.search('the and is', 'inverted'), [])

    def test_validation_rejects_invalid_documents_and_modes(self):
        for title, text in [('', 'text'), ('Title', ' '), (' ', 'text')]:
            with self.assertRaises(ValueError):
                self.engine.add_document(title, text)
        with self.assertRaises(ValueError):
            self.engine.search('text', 'unknown')

    def test_comparison_reports_both_results_and_nonnegative_timings(self):
        self.engine.add_document('One', 'Computers compute')
        report = self.engine.compare('compu', repeats=3)
        self.assertEqual(report['inverted']['results'], [])
        self.assertEqual(len(report['ngram']['results']), 1)
        for mode in ('inverted', 'ngram'):
            self.assertGreaterEqual(report[mode]['time_ms'], 0)
        self.assertEqual(report['repeats'], 3)

    def test_corrupt_storage_is_reported_without_overwriting(self):
        self.path.write_text('not json', encoding='utf-8')
        with self.assertRaises(ValueError):
            SearchEngine(self.path)
        self.assertEqual(self.path.read_text(), 'not json')


if __name__ == '__main__':
    unittest.main()
