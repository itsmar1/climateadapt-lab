# RAG Retrieval Evaluation (P07)

 dense retrieval: multilingual E5-small + Qdrant local mode, fused with BM25 via RRF.

 Status: **exploratory**. The gold set is small (10 evaluable queries) and its labels
 are **unreviewed** (KI-19 open). All arms score 1.00 on every metric — a ceiling
 effect that proves the pipeline runs end to end but demonstrates **no reliable
 improvement** of any arm over another. Do not cite these numbers as evidence that
 dense or hybrid beats BM25.

## Setup (recorded 2026-10-31)

- Dependencies (`dense` extra, CPU-only on Windows): torch 2.15.0+cpu
  (`cuda_available: False`, no nvidia/triton/cuda packages installed),
  sentence-transformers 6.2.0, qdrant-client 1.20.0, transformers 5.22.1,
  tokenizers 0.23.3, safetensors 0.8.0, huggingface-hub 2.4.0.
- Model: `intfloat/multilingual-e5-small`, revision
  `614241f622f53c4eeff9890bdc4f31cfecc418b3`, dim 384, ~470 MB on disk
  (Hugging Face cache, outside the repo).
- Corpus: 5 documents, 1824 chunks (canonical P06 ingest, default chunking).
- Index: Qdrant local mode at `data/qdrant/` (git-ignored, ~7.2 MB),
  collection `climateadapt-intfloat-multilingual-e5-small-384d-b63c991f`,
  cosine distance, fingerprint sidecar
  `<collection>.fingerprint.json` (model id + revision, dim, device,
  chunking params, corpus sha `194dffccbe14…`, 1824 points).
- Embeddings use the required E5 prefixes (`query: ` / `passage: `),
  L2-normalized; retrieval text rejoins `chunks.jsonl` by `chunk_id`.

## Commands

```powershell
uv sync --extra dev --extra dense
uv run python scripts/rag_index.py --threads 8     # build; re-runs are no-ops when fresh
uv run python scripts/rag_index.py --force          # explicit rebuild
uv run python scripts/rag_eval.py --compare         # bm25 vs dense vs hybrid(k=60)
uv run python scripts/rag_eval.py --k-sweep         # hybrid at k = 10, 30, 60, 100
```

 Index build took 5804 s (~97 min) on this machine's CPU at 8 threads
 (~10–15 GFLOPS effective; a slow laptop CPU, not a code problem);
 re-running a fresh index takes 0.3 s. Eval queries encode in seconds.

## Results (2026-10-31)

10 evaluated (9 en, 1 fr), 5 skipped (q01, q03, q04, q13-fr, q15-ar —
 relevant manuals missing). No page-level annotations exist, so page
 metrics are empty.

 | arm         | n  | hit@1 | hit@3 | hit@5 | hit@10 | MRR  |
 |-------------|----|-------|-------|-------|--------|------|
 | bm25        | 10 | 1.00  | 1.00  | 1.00  | 1.00   | 1.00 |
 | dense       | 10 | 1.00  | 1.00  | 1.00  | 1.00   | 1.00 |
 | hybrid(k=60)| 10 | 1.00  | 1.00  | 1.00  | 1.00   | 1.00 |

Per-language: en (n=9) and fr (n=1) are 1.00 on every metric for every arm.
 No arm has any miss in the top 3.

RRF k sweep (hybrid): k=10, 30, 60, 100 all give hit@1=hit@10=MRR=1.00.
 Default stays k=60 — there is no evidence to prefer any other value.

## Limitations

- Unreviewed document-level labels; no `relevant_pages`; tiny n (10/1 per
  language for fr; ar unevaluable — its queries need missing manuals).
- BM25 was already perfect on this set, so the comparison cannot resolve
  any dense-vs-sparse difference. Harder queries (negation, paraphrase,
  cross-lingual with ingested docs) and owner-reviewed labels are needed
  before any architecture conclusion.
- Dense coverage is limited to the 5 ingested documents; the index refuses
  to serve when the model revision, chunking config, or corpus changes
  (rebuild with `--force`).
