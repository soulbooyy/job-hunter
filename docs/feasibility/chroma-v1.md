# Chroma Feasibility Report v1

## Decision

**Admission: admitted with constraints.**

ChromaDB 1.5.9 is feasible as an opt-in, rebuildable local derivative of the authoritative SQLite Evidence graph for the later formal Slice 6. This decision does not admit Chroma into the default runtime, does not select an embedding provider, and does not establish semantic retrieval quality.

The machine-readable benchmark artifact is `evals/reports/chroma-feasibility-v1.json`. The reproducible entry point is `./scripts/chroma-spike`.

## Frozen Boundary

The spike exercised only an isolated package under `backend/spikes/chroma_feasibility`. Production `job_hunter` modules do not import Chroma or the spike package. Chroma is pinned in the non-default `chroma-spike` uv dependency group and is absent from `project.dependencies`.

SQLite remains authoritative. The Chroma record ID is the immutable `EvidenceVersionId`; record metadata contains `EvidenceItemId`, `EvidenceVersionId`, Evidence type, sensitivity, validity, index version, and chunk-policy version. Only each EvidenceItem's active version is projected during reconciliation. Historical versions remain in SQLite and stale index records are removed.

The collection manifest freezes:

- schema: `chroma-feasibility-v1`
- embedding provider: `job-hunter-synthetic`
- embedding model: `deterministic-hash-v1`
- dimension: 64
- chunk policy: `whole-evidence-spike-v1`
- index version: `chroma-index-spike-v1`
- distance metric: cosine

The explicit embeddings are deterministic test vectors, not semantic embeddings. Candidate content is not stored in Chroma's `documents` field. Collection and record data are runtime-validated when read, and a manifest, identity, metadata, dimension, or rebuild mismatch fails closed through a stable redacted Job Hunter dependency error.

## Evidence

The isolated contract suite contains 10 tests covering:

- exact opt-in dependency pinning and production-import isolation;
- deterministic 64-dimensional explicit embeddings with no model download;
- write-process exit followed by read-process reopen;
- eligibility metadata filtering for validity and allowed sensitivity;
- add, update, upsert, and delete behavior;
- collection-manifest mismatch rejection;
- redacted third-party failure translation;
- complete rebuild from a migrated temporary SQLite Evidence graph;
- active-version replacement and stale-record removal;
- deterministic synthetic benchmark schema, identity/metadata correctness, content exclusion, and path exclusion.

The default benchmark used 256 active records, 50 fixed queries, 32 active-version replacements, and 32 deletions on Darwin arm64 with Python 3.12.13 and ChromaDB 1.5.9.

| Measurement | Result | Ceiling | Outcome |
|---|---:|---:|---|
| Cold index | 1,280.525 ms | 15,000 ms | Pass |
| Query p95 | 1.624 ms | 250 ms | Pass |
| Process reopen plus first query | 49.348 ms | 3,000 ms | Pass |
| Reconcile | 87.415 ms | 5,000 ms | Pass |
| Full rebuild | 49.625 ms | 15,000 ms | Pass |

Identity and metadata matched after reconcile and rebuild, process reopen succeeded, documents were absent, and the socket guard observed no attempted network access. These are bounded local mechanics results, not service-level objectives or production capacity claims.

## Package Impact

The exact `chromadb==1.5.9` opt-in group adds 64 packages to the lock graph relative to the existing baseline. Notable dependencies include ONNX Runtime, tokenizers, Hugging Face Hub, OpenTelemetry, gRPC, and the Kubernetes client. The installed Chroma distribution measured 55,379,332 bytes; this excludes the remainder of the transitive environment.

Chroma 1.5.9 supports Python 3.12 in the tested locked environment. The package publishes platform wheels, but this spike executed only on Darwin arm64. Linux, Windows, Intel macOS, installer size, startup cost on slower machines, and release packaging remain unverified.

The Chroma documentation describes `PersistentClient` as intended for local development and testing and recommends a server-backed client for production. Job Hunter's local-first design can continue evaluating the embedded client only as a constrained derivative index; this spike does not override that upstream operational guidance. See the [Chroma Persistent Client reference](https://docs.trychroma.com/reference/python/client) and [ChromaDB package metadata](https://pypi.org/project/chromadb/).

## Admission Constraints

- Chroma must remain opt-in until formal Slice 6 establishes production ports, lifecycle ownership, rebuild/fallback behavior, and release packaging.
- SQLite must remain the sole authority for Candidate Evidence, active pointers, and lineage. Chroma loss or corruption must be recoverable by full rebuild.
- A real embedding provider/model, dimension, chunk-policy version, and index version must be explicitly selected and recorded before production use.
- Candidate content must remain absent from logs, exceptions, reports, and diagnostic output. Whether production embeddings and any required document storage are acceptable needs a separate privacy review.
- The spike proves only the currently implemented validity-and-sensitivity eligibility subset. Candidate scope, permission, and task-specific redaction required by REQ-RAG-004 remain unimplemented.
- The synthetic workload does not satisfy AC-DATA-001 and establishes no AC-RAG-001/002 retrieval-quality promotion result.
- Formal Slice 6 must retain deterministic fallback to Full Context or Lexical/Metadata whenever semantic/hybrid retrieval is unavailable, incompatible, or below promotion thresholds.

## Rejection Triggers for Formal Slice 6

Admission must be revisited if the production implementation cannot preserve manifest compatibility, exact active-version reconciliation, stale-record deletion, redacted failures, offline startup, default dependency isolation, or rebuild from SQLite. Chroma must not become a default strategy if curated Development and Frozen Holdout evaluation fails the applicable AC-RAG promotion thresholds.

## Deliberately Not Implemented

This spike adds no production semantic adapter, HybridRetriever, fusion, automatic RetrievalPolicy, ContextBuilder/ContextPackage, Retrieval HTTP endpoint, migration, Domain/Application contract, frontend behavior, real embedding integration, or Candidate dataset. It creates no generic vector-store plugin framework and no unused production port.
