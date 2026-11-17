# Evaluation and measured results

Historical BGE CPU results below do not measure the deployed Gemini-embedding profile. All relevance labels remain drafts until reviewed by hand.

## Deployed-lite profile

<!-- ASKREPO:DEPLOYED:EVAL:START -->
**November 17, 2026: quota-blocked, measurements pending.** A real Gemini run
cached 45 query and 64 document embeddings before HTTP 429. The provider reported
1,000 embedding inputs/day for this project and a reset about 22 hours away.
The user chose to keep the free-tier run pending. No complete paired retrieval
table, AST improvement claim, or 20-answer Gemini faithfulness score exists yet.
See the [attempt record](../backend/eval/results/2026-11-17-deployed-lite-attempt.json).
<!-- ASKREPO:DEPLOYED:EVAL:END -->

This profile calls actual Gemini embeddings with 768 output dimensions, disables
reranking, and uses isolated local Qdrant snapshots. It never opens or changes
production collections. It compares fixed and AST chunking under BM25, vector,
and hybrid retrieval, plus an evaluation-only AST context experiment adding up
to 800 characters of imports/class headers to embedding and keyword text. Source
code and citable ranges stay unchanged. No experiment is promoted to application
defaults without completed comparative measurements.

Fresh source snapshots were fetched for this attempt. All 45 draft path/symbol
labels resolve, but that is not human relevance review. The completed report will
record model names, source SHAs, implementation/question hashes, dimensions,
chunk budgets, library versions, per-question rankings and chunk distributions.
`eval.diagnose_lite` prints every fixed-over-AST Recall@10/MRR case, including
labels and both top-ten lists. It explicitly notes how broad path/overlap labels
can favor large fixed windows. It checks tiny/large chunks and missing path text.

Resume from `backend`, preserving the same source and data directories:

```powershell
# Required keys stay in ignored backend/.env. Wait for available embedding quota.
..\.venv\Scripts\python.exe -m eval.run_eval --profile deployed-lite --sources data/eval-sources-2026-11-17 --data-dir data/lite-eval-2026-11-17 --validate-only
..\.venv\Scripts\python.exe -m eval.run_eval --profile deployed-lite --sources data/eval-sources-2026-11-17 --data-dir data/lite-eval-2026-11-17
# After a completed report exists:
..\.venv\Scripts\python.exe -m eval.diagnose_lite eval/results/YYYY-MM-DD-deployed-lite.json
```

The runner preserves exact model/task/text embeddings and matching vector-batch
checkpoints, stops on quota failure, and refuses to overwrite a completed report.
The date above describes the attempt, not a promise that quota is available now.
Both production bootstrap and this offline run share the project's quota; allow
the demos to finish first rather than competing with them for the same allowance.
The full three-variant experiment needs more inputs than initial demo indexing.

Query embeddings are prepared once and shared across modes. Reported warm local
retrieval milliseconds **exclude Gemini embedding preparation and quota waits**;
they must not be presented as Render response latency. Preparation and total
wall time are recorded separately. The seeded 20-question answer audit uses
actual Gemini generation, checks each citation against source bounds and retrieved
evidence, and requests a same-family automated 0–4 rubric score with 20-second
pauses. Failed/abstaining answers do not receive invented rubric scores. The
answer plus judge share the configured provider-attempt cap. This is automated
evidence, not human-validated faithfulness.

## Evaluation and manual review

The harness compares fixed versus AST chunking against BM25, vector, hybrid RRF, and hybrid + rerank: **8 configurations, 45 draft questions, 3 public repository snapshots**. Embeddings and reranking use the actual BGE models on CPU. Each result includes per-question rankings, metrics, model/library versions, source revisions, question hashes, precision/batch settings, and index stats.

**Every draft label still needs your review:** `seekr-01` through `seekr-15`, `codenest-01` through `codenest-15`, and `dptrace-01` through `dptrace-15`. Verify the expected paths and symbols, add other relevant targets where needed, remove ambiguous questions, then set `reviewed:true` in each JSONL row. Path-only labels deserve special scrutiny because they accept any chunk from that file. See [evaluation instructions](../backend/eval/README.md) and [the review checklist](../backend/eval/REVIEW.md). Draft baseline numbers are not a human-validated benchmark.

From `backend`:

```powershell
..\.venv\Scripts\python.exe -m eval.prepare
..\.venv\Scripts\python.exe -m eval.run_eval --validate-only
..\.venv\Scripts\python.exe -m eval.run_eval
# After reviewing all 45 rows:
..\.venv\Scripts\python.exe -m eval.run_eval --require-reviewed
$latestRun = Get-ChildItem eval/results -Filter "????-??-??.json" | Sort-Object Name -Descending | Select-Object -First 1
..\.venv\Scripts\python.exe -m eval.faithfulness --results $latestRun.FullName
```

Recall counts unique relevant path/symbol targets, using line overlap resolved independently with AST labels so fixed chunks are scored fairly. MRR is evaluated within the returned top ten, explicitly shown as MRR@10. Hit rate@10 means at least one relevant result. Mean query latency includes retrieval and enabled reranking; model loading and indexing are recorded separately. A seeded 20-answer citation spot-check reports both coverage and structural citation validity. It does not establish semantic entailment or answer correctness; its default extractive provider makes no Gemini call.

This first run is a single pass on an interactive development laptop, sharing CPU and memory with other applications and local checks. Timings describe that observed environment. Use an idle host and repeated runs before making production performance claims.

<!-- ASKREPO:EVAL:START -->
Ground truth: **draft—human review required**. Actual CPU run: `2026-11-02.json`.

| Chunking | Retrieval | Recall@1 | Recall@5 | Recall@10 | MRR@10 | Hit rate@10 | Avg ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fixed | bm25 | 0.2667 | 0.4000 | 0.5556 | 0.3380 | 0.5556 | 6.63 |
| fixed | vector | 0.2667 | 0.6000 | 0.7333 | 0.4226 | 0.7333 | 146.79 |
| fixed | hybrid | 0.3111 | 0.6444 | 0.7333 | 0.4332 | 0.7333 | 176.36 |
| fixed | hybrid + rerank | 0.2444 | 0.6000 | 0.7778 | 0.4120 | 0.7778 | 38022.03 |
| ast | bm25 | 0.1556 | 0.3111 | 0.4889 | 0.2214 | 0.4889 | 17.33 |
| ast | vector | 0.2222 | 0.5778 | 0.7111 | 0.3687 | 0.7111 | 152.82 |
| ast | hybrid | 0.2000 | 0.5333 | 0.6000 | 0.3128 | 0.6000 | 217.68 |
| ast | hybrid + rerank | 0.1778 | 0.4667 | 0.6667 | 0.3174 | 0.6667 | 29106.79 |
<!-- ASKREPO:EVAL:END -->

In the recorded draft/128-token run, fixed-window hybrid + rerank had the highest Recall@10 (**0.7778**). Fixed-window hybrid without reranking had the highest MRR@10 (**0.4332**) at **176.36 ms** average observed query latency. AST chunking did not improve the aggregate retrieval-quality metrics in this run. Reranking cost about **38.0 s** per fixed-window query and **29.1 s** per AST query on this development machine. These are measured baseline findings, not evidence that the defaults are optimal. Review the labels and repeat with the intended model profile before tuning.

The seeded extractive citation audit sampled **20 answers**, all of which contained citations, and checked **60 citations: 60 valid (100%)**, with no not-found answers in that sample. This establishes file/range validity only, not semantic faithfulness or Gemini answer quality. See [the complete retrieval report](../backend/eval/results/2026-11-02.json) and [the citation audit](../backend/eval/results/2026-11-02-citation-audit.json).


## Streaming, memory, and agentic evaluation

<!-- ASKREPO:ADVANCED:EVAL:START -->
Actual run: `2026-11-03-advanced.json`. Ground truth: **draft—human review required**. Provider: **extractive**.

Paired modes share a freshly measured initial search. Latency is that measured stage plus each measured continuation; the initial model work is not executed twice.

| Suite | Mode | N | Recall@1 | Recall@5 | Recall@10 | MRR@10 | Avg measured ms | Avg LLM calls | Retry rate | Answer rate |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| standalone | single-pass hybrid + rerank | 45 | 0.1778 | 0.4667 | 0.6667 | 0.3174 | 44942.31 | 0.00 | 0.0000 | 0.7111 |
| standalone | agentic retrieval | 45 | 0.1778 | 0.4444 | 0.6222 | 0.3060 | 70620.53 | 0.00 | 0.6889 | 0.3111 |
| follow-up | rewrite off | 15 | 0.1333 | 0.1333 | 0.2000 | 0.1400 | 143.56 | 0.00 | 0.0000 | 1.0000 |
| follow-up | rewrite on | 15 | 0.4000 | 0.8000 | 0.8667 | 0.5806 | 187.47 | 0.00 | 0.0000 | 1.0000 |

Agentic retrieval did not improve Recall@10 in this run. It remains opt-in in the UI.

Follow-up reranking: **False** in both rewrite modes. Answer caching is disabled. LLM calls count actual provider attempts, including retries.

**No Gemini key was used.** Rewriting uses prior identifiers and agentic retries use ranking rules and lexical query variants. These are real CPU/no-key results, not measured Gemini rewrite/grader quality or free-tier Gemini cost.

<!-- ASKREPO:ADVANCED:EVAL:END -->

The advanced run saved 120 question/mode records. A separate check verified all 227 saved citation ranges against both the source-file bounds and the currently retrieved spans. This establishes structural validity, not semantic answer faithfulness. The CPU run used 128-token, embedding-int8 BGE indexes; the report records the full model profile and source revisions. Review the 60 draft cases in [the relevance review checklist](../backend/eval/REVIEW.md) before treating these measurements as validated benchmark claims.

