"""Persistent document collection with stemmed postings and character n-gram search."""

import json
import re
import statistics
import threading
from collections import Counter, defaultdict
from pathlib import Path
from time import perf_counter_ns
from uuid import uuid4

from nltk.stem import PorterStemmer

# Embedded to keep preprocessing reproducible without downloading NLTK corpora.
STOP_WORDS = frozenset('''a an the and or but if while of at by for with about against
between into through during before after above below to from up down in out on off
over under again further then once here there when where why how all any both each
few more most other some such no nor not only own same so than too very can will
just should now i me my myself we our ours ourselves you your yours yourself
yourselves he him his himself she her hers herself it its itself they them their
theirs themselves what which who whom this that these those am is are was were be
been being have has had having do does did doing would could shall may might must
s t don doesn didn isn aren wasn weren won wouldn couldn shouldn ll ve re d m'''.split())
STEMMER = PorterStemmer()


def tokenize(text, remove_stopwords=True):
    """Lowercase Unicode alphanumeric words, splitting punctuation and underscores."""
    return [word for word in re.findall(r'[^\W_]+', text.lower()) if not remove_stopwords or word not in STOP_WORDS]


def preprocess(text):
    return [STEMMER.stem(word) for word in tokenize(text)]


def grams(word, size):
    return {word[i:i + size] for i in range(len(word) - size + 1)}


class SearchEngine:
    def __init__(self, storage_path):
        self.storage_path = Path(storage_path)
        self.lock = threading.RLock()
        self.documents = {}
        self.inverted_index = defaultdict(dict)
        self.word_index = defaultdict(dict)
        self.ngram_index = defaultdict(set)
        if self.storage_path.exists():
            try:
                documents = json.loads(self.storage_path.read_text(encoding='utf-8'))
                if not isinstance(documents, list):
                    raise ValueError('Expected a document list')
                for doc in documents:
                    if (not isinstance(doc, dict)
                            or any(not isinstance(doc.get(key), str) or not doc[key].strip()
                                   for key in ('id', 'title', 'text'))
                            or doc['id'] in self.documents):
                        raise ValueError('Invalid or duplicate document')
                    self._index(doc)
            except (ValueError, TypeError) as error:
                raise ValueError(f'Invalid document store: {self.storage_path}. '
                                 'Restore or move the file before restarting.') from error

    def _index(self, doc):
        self.documents[doc['id']] = doc
        for term, frequency in Counter(preprocess(doc['text'])).items():
            self.inverted_index[term][doc['id']] = frequency
        for word, frequency in Counter(tokenize(doc['text'])).items():
            self.word_index[word][doc['id']] = frequency
            # Smaller grams support one- and two-character fragments as well.
            for size in range(1, min(3, len(word)) + 1):
                for gram in grams(word, size):
                    self.ngram_index[gram].add(word)

    def add_document(self, title, text):
        if not isinstance(title, str) or not title.strip():
            raise ValueError('A document title is required.')
        if not isinstance(text, str) or not text.strip():
            raise ValueError('Document text cannot be empty.')
        doc = {'id': uuid4().hex, 'title': title.strip(), 'text': text.strip()}
        with self.lock:
            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.storage_path.with_suffix('.tmp')
            temporary.write_text(json.dumps([*self.documents.values(), doc],
                                            ensure_ascii=False, indent=2), encoding='utf-8')
            temporary.replace(self.storage_path)
            self._index(doc)
        return dict(doc)

    def list_documents(self):
        with self.lock:
            return [dict(doc) for doc in self.documents.values()]

    def _partial_postings(self, fragment):
        fragment_grams = grams(fragment, min(3, len(fragment)))
        buckets = [self.ngram_index.get(gram, set()) for gram in fragment_grams]
        candidates = set.intersection(*buckets) if buckets else set()
        postings = Counter()
        for word in candidates:
            # Shared grams need not be contiguous or ordered in a candidate.
            if fragment in word:
                postings.update(self.word_index[word])
        return postings

    def search(self, query, mode='inverted'):
        if mode not in ('inverted', 'ngram'):
            raise ValueError('Search mode must be inverted or ngram.')
        with self.lock:
            terms = list(dict.fromkeys(preprocess(query) if mode == 'inverted' else tokenize(query, remove_stopwords=False)))
            postings = {term: self.inverted_index.get(term, {}) if mode == 'inverted'
                        else self._partial_postings(term) for term in terms}
            ids = {doc_id for posting in postings.values() for doc_id in posting}
            results = []
            for doc_id in ids:
                doc = self.documents[doc_id]
                frequencies = {term: posting.get(doc_id, 0) for term, posting in postings.items()}
                results.append({'id': doc_id, 'title': doc['title'],
                                'preview': doc['text'][:220], 'frequencies': frequencies,
                                'score': sum(frequencies.values())})
            return sorted(results, key=lambda row: (-row['score'], row['title'].lower(), row['id']))

    def compare(self, query, repeats=50):
        if not 1 <= repeats <= 1000:
            raise ValueError('Repeats must be between 1 and 1000.')
        report = {'query': query, 'repeats': repeats}
        with self.lock:
            for mode in ('inverted', 'ngram'):
                self.search(query, mode)  # Warm up before measurement.
                durations = []
                for _ in range(repeats):
                    start = perf_counter_ns()
                    results = self.search(query, mode)
                    durations.append((perf_counter_ns() - start) / 1_000_000)
                report[mode] = {'results': results, 'time_ms': statistics.median(durations)}
        return report

    def stats(self):
        with self.lock:
            return {'documents': len(self.documents), 'stems': len(self.inverted_index),
                    'words': len(self.word_index), 'grams': len(self.ngram_index)}
