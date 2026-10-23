# Information Retrieval Systems — Assignment 1: Document Indexing and Search Engine

**Student Submission & Comprehensive Evaluation Report**
**Repository:** [KanavSingla28-k/IRS-assignment](https://github.com/KanavSingla28-k/IRS-assignment.git)

---

## 1. Compliance Checklist & Completion Status

| Question / Requirement | Specification | Implementation Details | Status |
| :--- | :--- | :--- | :---: |
| **Q1. Mini Search Engine** | Allow users to upload or add multiple text documents | Single document form submission + batch multi-file upload (`.txt`, UTF-8, max 30 files, 5 MB limit) | **100% Complete** |
| | Inverted index mapping word to document IDs | Maps processed root stems to `{doc_id: frequency}` dictionary | **100% Complete** |
| | Text preprocessing (tokenization, stop words, stemming) | Lowercase regex tokenization, embedded stop-word list filtering, Porter Stemmer normalization | **100% Complete** |
| | Display matching documents with term frequencies | Returns list of retrieved documents, individual term occurrence frequencies, and cumulative score | **100% Complete** |
| | Add new documents and update index automatically | Real-time index re-indexing & disk synchronization immediately upon addition | **100% Complete** |
| **Q2. Multiple Indexing** | Implement two techniques: Inverted Index & N-gram Index | Dual-engine architecture: Stemmed Inverted Index + Character N-gram (1-gram, 2-gram, 3-gram) Word Index | **100% Complete** |
| | Search using exact keywords and partial words | Inverted index handles exact/stemmed queries; N-gram handles subwords/prefixes/partial fragments | **100% Complete** |
| | Compare search results between techniques | Side-by-side mode switching, shared document overlap count, individual document frequency matrix | **100% Complete** |
| | Measure and compare search time for query types | High-resolution microbenchmarking (`perf_counter_ns`), 50-100 warm iterations, median time reporting (ms) | **100% Complete** |
| | Present comparison in table or visual chart | In-app comparison ledger table, document coverage matrix, live diagnostic snapshot cards | **100% Complete** |

**Overall Completion: 100%**

---

## 2. Architecture & Algorithmic Implementation

### 2.1 Preprocessing Pipeline
1. **Tokenization:** Uses Unicode regex pattern `[^\W_]+` to extract alphanumeric tokens while stripping punctuation and underscores.
2. **Stop-word Removal:** Uses an embedded set of common English stop words to ensure reproducible, zero-network preprocessing without requiring external NLTK downloads.
3. **Stemming:** Applies the Porter Stemmer algorithm (e.g., `computing`, `computer`, `computers` $\rightarrow$ `comput`).

### 2.2 Inverted Index vs. N-gram Index
- **Inverted Index ($I_{inv}$):**
  - Maps: $\text{stem} \mapsto \{\text{doc\_id}: \text{frequency}\}$.
  - Query execution: Query tokens are lowercased, filtered for stop words, stemmed, and retrieved via exact dictionary lookup.
- **Character N-gram Index ($I_{ngram}$):**
  - Deconstructs words into character unigrams, bigrams, and trigrams.
  - Maps: $\text{n-gram} \mapsto \text{Set}(\text{words})$.
  - Maintains an unstemmed vocabulary index: $\text{word} \mapsto \{\text{doc\_id}: \text{frequency}\}$.
  - Query execution: For query fragment $f$, queries trigrams (or unigram/bigram for short terms), performs set intersection $\bigcap_{g \in \text{grams}(f)} I_{ngram}[g]$, validates contiguous substring containment ($f \subseteq w$), and aggregates document occurrences.

---

## 3. Empirical Results & Performance Comparison

The following experimental results were measured using a benchmark corpus of technical documents across different query categories (median of 100 warmed iterations using `perf_counter_ns`):

### 3.1 Benchmark Comparison Table

| Query | Query Category | Inverted Matches | Inverted Time (ms) | N-gram Matches | N-gram Time (ms) | Key Retrieval Observation |
| :--- | :--- | :---: | :---: | :---: | :---: | :--- |
| **`computer`** | Exact Keyword | 2 | 0.0137 ms | 2 | 0.0079 ms | Inverted matches stem `comput` (scores both `computer` & `computing`); N-gram matches exact substring `computer`. |
| **`compu`** | Partial Word / Substring | **0** | 0.0111 ms | **2** | 0.0122 ms | **Inverted index misses** (not a full word/stem). **N-gram successfully retrieves** documents containing `computer` and `computing`. |
| **`search engine`** | Multi-term Query | 2 | 0.0241 ms | 2 | 0.0113 ms | Evaluates multi-term OR matching, calculating individual term frequencies (`search`: 1, `engin`/`engine`: 1). |
| **`indexing`** | Exact / Inflected Word | 3 | 0.0175 ms | 3 | 0.0085 ms | Inverted normalizes `indexing` $\rightarrow$ `index`; N-gram matches substring `indexing` in source text. |
| **`sys`** | Short Fragment | **0** | 0.0112 ms | **2** | 0.0059 ms | Inverted fails on 3-letter prefix; N-gram uses trigram intersection to match `systems`. |
| **`xyznotfound`** | Non-existent Word | 0 | 0.0112 ms | 0 | 0.0055 ms | Both indexes return 0 results promptly with minimal lookup latency. |

### 3.2 Detailed Document Coverage & Frequency Matrix

#### Query: `computer`
- **Inverted Index:**
  - `Doc4 - Computer Science`: Frequency = 2 (matches `computer` and `computing` $\rightarrow$ stem `comput`)
  - `Doc1 - IR Overview`: Frequency = 1 (matches `computer`)
- **N-gram Index:**
  - `Doc1 - IR Overview`: Frequency = 1 (`computer`)
  - `Doc4 - Computer Science`: Frequency = 1 (`computer`)

#### Query: `compu` (Partial Word)
- **Inverted Index:**
  - *No documents retrieved* (Term is unrecognized as a dictionary stem)
- **N-gram Index:**
  - `Doc4 - Computer Science`: Frequency = 2 (contains substring in `computer` and `computing`)
  - `Doc1 - IR Overview`: Frequency = 1 (contains substring in `computer`)

#### Query: `search engine` (Multi-term)
- **Inverted Index:**
  - `Doc2 - Search Engines`: `search` = 1, `engin` = 1 (Score: 2)
  - `Doc1 - IR Overview`: `search` = 1, `engin` = 0 (Score: 1)
- **N-gram Index:**
  - `Doc2 - Search Engines`: `search` = 1, `engine` = 1 (Score: 2)
  - `Doc1 - IR Overview`: `search` = 1, `engine` = 0 (Score: 1)

---

## 4. Key Comparative Analysis & Insights

1. **Exact vs. Partial Recall:**
   - The **Inverted Index** provides high precision and semantic grouping through stemming (conflating noun/verb forms), but fails completely on partial queries, prefixes, or word fragments (e.g., `compu`, `sys`).
   - The **N-gram Index** excels in substring and prefix retrieval, successfully finding documents even when queries are truncated or inflected in unstemmed forms.

2. **Time Complexity:**
   - Inverted index search time is $O(\|Q\| \cdot L)$, where $\|Q\|$ is number of terms and $L$ is posting list length.
   - N-gram search incurs a verification step ($f \subseteq \text{word}$) after candidate set intersection: $O(\|\text{grams}\| + \|\text{candidates}\| \cdot \text{length})$. On small to medium corpora, both execute well under $0.03\text{ ms}$.

3. **Space Overhead:**
   - The inverted index requires significantly less storage because it only maintains unique processed stems.
   - The N-gram index has higher memory overhead due to storing unigrams, bigrams, trigrams, and full word vocabulary mappings.

---

## 5. Instructions to Run and Reproduce

### 5.1 Local Execution
```bash
# Clone the repository
git clone https://github.com/KanavSingla28-k/IRS-assignment.git
cd IRS-assignment

# Install dependencies
pip install -r requirements.txt

# Launch application
python app.py
```
Open **`http://127.0.0.1:5000`** in your browser.

### 5.2 Running the Test Suite
```bash
python -m pytest -o pythonpath=.
```
*(All 21 automated unit tests across `test_engine.py` and `test_app.py` pass.)*
