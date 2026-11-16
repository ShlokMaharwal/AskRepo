# Retrieval evaluation

Run from `backend`. Neural inference is CPU-only. The default models are BAAI/bge-small-en-v1.5 and BAAI/bge-reranker-base; no generation API is called during retrieval benchmarks.

1. Fetch source-only snapshots with `python -m eval.prepare`. This uses the same bounded public GitHub clone routine as the application and never executes repository code.
2. Validate paths and symbols with `python -m eval.run_eval --validate-only`.
3. Review **all** `seekr-01`–`seekr-15`, `codenest-01`–`codenest-15`, and `dptrace-01`–`dptrace-15`. Every ID is listed in [REVIEW.md](REVIEW.md). Edit `questions/*.jsonl` directly; add missing relevant targets, narrow broad path-only targets, and correct ambiguous wording. Mark each corrected row `reviewed:true`.
4. Run `python -m eval.run_eval` for a clearly labeled draft baseline or add `--require-reviewed` to enforce human-reviewed labels. The default runs every question against all eight configurations.
5. Run `python -m eval.faithfulness --results eval/results/YYYY-MM-DD.json` to sample 20 actual answers and check every structured citation against the stored file and retrieved source range. This defaults to source excerpts, so it needs no Gemini key. `--provider configured` uses your configured answer provider.

`draft_questions.py` contains the original question drafts. Do not regenerate over corrected JSONL files. `python -m eval.review` safely refreshes the checklist from the JSONL data.

## Protocol

Two chunkers: 60-line/10-overlap fixed windows and tree-sitter AST. Four retrieval modes for each: BM25-only, vector-only, RRF hybrid, and RRF hybrid + top-20 cross-encoder reranking. BM25/vector candidate depth is 50, RRF k=60, and returned evaluation depth is 10. Neighbor chunks are excluded from ranked metrics; confidence gates do not suppress raw retrieval measurements.

A relevant item is a path, optionally narrowed to a symbol. A hit requires that path and overlap with an AST-resolved symbol range. The resolver is independent of the evaluated chunker, so fixed windows receive credit for overlapping a function even though they have no symbol metadata. Missing targets fail the run. Each relevant item is counted once, even if multiple returned chunks overlap it.

- Recall@1/@5/@10: fraction of relevant targets hit by that rank, averaged across questions.
- MRR@10: reciprocal rank of the first relevant returned chunk, or zero if absent in the first ten.
- Hit rate@10: fraction of questions with any relevant result in ten.
- Average latency: retrieval plus enabled reranking, in milliseconds. Model cold starts and index construction are excluded and recorded separately.

Models warm once before query timing. Question labels are provisional until reviewed. Small, filename/symbol-oriented datasets can overstate general usefulness; add paraphrases, multi-file questions, negative questions and held-out repositories before making broad claims. One draft relevant item per question makes recall and hit rate coincide at that cutoff; add all genuinely required targets during manual review.

The initial run is a single pass on an interactive development laptop, with other applications and local verification work sharing its CPU and memory. Its wall-clock timings are observed desktop measurements, not isolated production throughput or latency guarantees. Use an otherwise idle host and repeated runs for performance comparisons.

## Artifacts and reproducibility

`results/YYYY-MM-DD.json` contains all per-question ranked chunks/metrics, aggregate rows, source commit SHAs, question hashes, implementation hash, library versions, CPU precision/batches/threads and file/chunk counts. The runner prints a Markdown table and updates only the `ASKREPO:EVAL` marker block in the project README. It never invents a result for a failed configuration.

Index snapshots are cached in ignored `data/eval-indexes/{fixed,ast}` directories. IDs incorporate the source commit, implementation fingerprint, chunk budget and embedding model/profile. Use a new `--data-dir` for a fully fresh index build. Keep model configuration and cached source snapshots fixed when comparing repeated runs.

For the approximately 6 GB, two-core local machine, the recorded run uses int8 embedding tables with float matrix layers for both BGE models, 2 CPU threads, embedding batch 4, reranker batch 2, and 128-token model input budgets. All source files and all questions remain in the evaluation. The normal 16 GB full-precision, 512-token defaults remain available. Precision and embedding token-budget profiles have distinct index identifiers and must not be mixed. There is no GPU use. Compare this local profile only against runs with the same settings; the results are not a full-precision 512-token benchmark.

## Citation audit limits

The seeded sample uses actual AnswerService responses. The report gives sampled answers, answered/cited coverage, not-found counts, checked citation count, and citation-validity rate (null if there are no citations). Missing evidence is not counted as a valid citation. Structural range validity is **not semantic faithfulness**; it does not determine whether a claim is entailed by those lines. Gemini-generated-answer auditing requires your API key and a separate configured-provider run; the default extractive audit must not be presented as a Gemini faithfulness result.

## Conversation and agentic evaluation

`python -m eval.run_eval --suite advanced --validate-only` validates all 45 standalone and 15 follow-up targets against saved source snapshots. The follow-up set is `questions/followups.jsonl`: five authored cases for each demo repository. Their histories are drafts, not recorded model responses. Every `followup-seekr-01` through `05`, `followup-codenest-01` through `05`, and `followup-dptrace-01` through `05` needs manual review, in addition to the original 45 questions. `python -m eval.review` lists all 60 IDs and targets in REVIEW.md.

Run `python -m eval.run_eval --suite advanced --provider extractive --share-initial` for the no-key CPU profile. It compares single-pass hybrid + rerank with bounded agentic retrieval on all 45 questions, and rewrite off versus rewrite on on all 15 follow-ups. Follow-up comparisons use hybrid retrieval without reranking in both modes by default; `--followup-rerank` enables it consistently for that pair. Source revisions, model profiles, corpus/question hashes, all rankings, answer/not-found rates, retry rates, latency and actual provider-attempt counts are saved to `results/YYYY-MM-DD-advanced.json`.

The paired option runs one fresh initial search per standalone question, then measures each branch's continuation. Its latency column is the measured initial stage plus the measured continuation. Both components and total execution wall time are retained, so shared computation is explicit. Omit `--share-initial` to execute two independent full pipelines instead. Answer caching is disabled in either protocol. Partial rows are journaled during a run, but the README table is updated only after full success. A failed run never gets a fabricated summary.

No-key mode uses deterministic history context, lexical alternatives and score-based retry decisions, with source excerpts for answers. It does not call a Gemini rewriter/grader and its LLM-call count is zero. To evaluate those Gemini steps, configure a backend key, select auto/gemini generation, and use `--provider configured`. Configured-provider evaluation defaults to 20 seconds of pacing between records to respect conservative demo limits; `--delay-seconds` overrides that pause. Per-question attempt caps and the provider limiter remain active. Quota errors stop the run with its partial journal intact.

A live API owns embedded Qdrant's lock. Keep the app running and use an isolated online-backup snapshot if needed:

    python -m eval.snapshot --output data/eval-copy
    python -m eval.run_eval --suite advanced --share-initial --advanced-data-dir data/eval-copy

The helper copies completed immutable source/chunk/BM25 data and uses SQLite online backup for the registry and vector stores. It does not open a second client on the live Qdrant directory or copy its lock. Metadata records the copy's provenance. Persisted cosine scores can differ from an in-memory calculation by floating-point rounding; the snapshot test checks identical point IDs and equivalent scores within 1e-6.

The runner states plainly whether agentic Recall@10 improved and keeps the frontend setting opt-in. Draft-label results and this compact local CPU profile do not establish broad retrieval improvements, Gemini answer faithfulness, or production throughput. The earlier eight-mode benchmark remains separately available.
