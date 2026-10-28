# Conversation processor

Standalone, configuration-driven ingestion of **new** assistant conversations.
The only downstream interface is `memory-candidate/v1` JSONL. No persona loader,
personality engine, Git writes, memory routing, model lifecycle operations or
scheduler is imported or invoked.

Persona hashes are provenance, not an eligibility filter. The default marker is
`[persona sha256=<8 lowercase hex digits>]`, optionally with the loader's
` 字数=<digits>` before `]`. Any valid hash is accepted and recorded. Preset,
cwd/model, human-message and effective-prompt checks still apply. A configured
legacy `persona_hash` fallback is supported, but is unnecessary when the actual
prompt provides a marker. No identity-specific hash is built into this package.

## Install and configure

Use a dedicated Python 3.11+ environment (tested on Python 3.13 on Windows):

```text
python -m venv /path/to/dedicated-environment
/path/to/dedicated-python -m pip install -r requirements.lock.txt
```

`requirements.txt` pins direct dependencies; `requirements.lock.txt` pins the
tested full environment. `config/processor.example.yaml` contains no deployment
identities. Copy it to your chosen configuration location and edit **all** paths,
source selectors, local model identifier, trait names and privacy keywords.
Relative paths resolve against the configuration file's directory.

The deployment config must stay outside a separately published generic package.
All source entries in the example are deliberately disabled. `check-config`
does not open source conversations or create a cursor database.

```text
python -B processor.py --config /path/to/processor.yaml check-config
```

## CLI and T0

Enable the desired sources only after reviewing configuration and registering
the intended activation. The following is an operator action, **not** an
installation/test step:

```text
python -B processor.py --config /path/to/processor.yaml baseline --confirm
python -B processor.py --config /path/to/processor.yaml collect
python -B processor.py --config /path/to/processor.yaml extract --limit 20
python -B processor.py --config /path/to/processor.yaml run --limit 20
python -B processor.py --config /path/to/processor.yaml status
```

- `baseline` records source enable times and per-session complete-record
  watermarks. It never enqueues historical turns or invokes the model. It refuses
  to reset a source that already has a baseline. New source IDs can be registered
  separately in a config containing only those newly enabled sources.
- A human turn already in progress at baseline is skipped in its entirety,
  including a partially written line/frame completed later.
- `collect` admits completed eligible turns into the SQLite retry queue. It
  requires an explicit baseline. New sessions must have post-enable provenance.
- `extract` processes only enabled sources' queued turns. Unavailable local
  service leaves them queued and stops this batch. Invalid model output is
  rejected, with an enum diagnostic and source hash only. `category=none` is a
  successful no-output result.
- `run` combines collect and extract; `--limit` caps new extraction requests,
  not pending outbox recovery. Exit 0 means this batch completed; 2 means there
  are active-source pending items/source errors; 1 means invalid configuration,
  missing baseline, lock contention or state failure. Output is a JSON summary
  containing counts only, never dialogue or model error bodies.

No automatic activation, environment mutation or service startup is performed.
An OS advisory lock prevents scheduled and manual workers from overlapping;
the lock file remains on disk and is automatically unlocked on process death.

## Source semantics

All selectors below are configuration values, not hard-coded deployment names.
Source files are opened read-only.

| Adapter | Acceptance and identity |
|---|---|
| `dsh` | Released v4 multi-frame Zstandard JSONL. Replay preset selections; accept configured preset and genuine `source.kind=user`. Skip seeded prefixes, reasoning, tool calls, system context and incomplete turns. Final non-tool text is paired at `turn/end`. Refs use event seq; cursor includes complete frame offset. An incomplete tail is retained for a later scan. |
| `lmstudio` | Configured preset identifiers; an extra marker requirement is opt-in. Missing hash is recorded as null. Read selected versions only. Exclude thinking/tool/debug/status, and text preceding the last tool boundary. A final visible content block must have `genInfo.stats`; otherwise leave the turn pending. Source time is null. Refs contain slots and selected-version fingerprints. |
| `cc` | Configured cwd and local model, plus actual effective prompt-snapshot marker. Follow the latest main message's parentUuid chain; exclude sidechains, meta messages, tool-result user carriers, thinking and tool calls. Combine assistant fragments by message.id, and require end_turn plus visible text. Refs use human uuid + assistant message.id so late duplicate fragments do not create another candidate. |
| `sim` | Synthetic complete newline-terminated turn-unit JSONL, with `source.kind=sim`. Used for tests and controlled simulations. Never point it at raw source logs. |

For correctness the current adapters replay a bounded complete source snapshot
to reconstruct branch/preset context. Acceptance and cursor advancement are
incremental; this is **not** a byte-tail performance implementation. Default
source file cap is 64 MiB (overridable per source with `max_file_bytes`). DSH
frame offsets and CC line offsets are recorded for future optimized readers.
No truncated tail is repaired or rewritten by the processor.

DSH sources accept `max_window_size` in bytes (default 2147483648, 2 GiB).
The permitted range is 1024..2147483648; the decoder uses the frame's declared
window rather than preallocating the ceiling. This does not raise the separate
64 MiB default file limit or the existing decompressed-frame output limit.
`python -B check_sources.py --config <path>` exercises both adapter scan paths
without opening a cursor database, calling a model, or printing message bodies.
It reports file/frame/record counts, preset distributions and incomplete tails;
an incomplete live tail is reported separately and never silently called complete.

LM snapshots have no universal user message ID or per-message wall clock. Old
baseline slots and already accepted assistant slots are never reinterpreted as
new turns after a version switch. Entering an eligible preset/marker advances
past previously observed ineligible slots. Deletion/reordering of old slots,
transient versions that never reach disk, and post-emission source edits cannot
be perfectly reconstructed from a snapshot. Start a new marked conversation at
activation for strict provenance. This interface emits no retraction events;
downstream correction/retraction support is a separate extension.

Clock timestamps are an additional conservative post-T0 check for event-log
human inputs and newly discovered snapshots. Broken/skewed timestamps can cause
conservative omission; they never authorize a historical backfill. Missing seed
length on a seeded DSH session fails closed. Unknown/new source schemas are
reported without printing contents.

## Candidate contract and atomic delivery

`conversation_processor/schema.json` is Draft 2020-12. The processor owns schema,
id, source and persona_hash. The model returns extraction fields only; unknown
fields and unknown configured traits are rejected. Quotes must be exact source
substrings with no more than two sentences; expressions must occur in the
assistant's text. Length limits are Unicode code points. Importance is 1..5;
trait direction is -1 or +1. `none` is not published.

Expression scope is owner-only, friendly direct conversation. Optional source
`audience` is owner/group/third_party/unknown; non-owner/unknown blocks expressions.
DSH, LM Studio and CC preserve explicit transport audience/chatType/isGroup/groupId
metadata when available; source configuration can also supply that metadata.
Absent metadata keeps the existing eligible owner-interface assumption; this is
not identity authentication. `expressions.non_owner_markers` scans the human
message and expression; `aggressive_keywords` scans the saying (NFKC/casefold).
Both vocabularies are configured, never embedded in generic code. A forbidden
expression candidate is rejected without weakening quote/schema checks.

`praise.keywords` and optional `praise.trait_aliases` are deployment policy;
no praise vocabulary or trait names are hardcoded. A human utterance containing
a praise keyword and the name/alias of a positively signaled trait forces the
whole candidate's `praise_only` to true, including praise plus requests for more.
Existing true flags are never cleared. This conservatively excludes mixed
episodes without changing memory-candidate/v1. An omitted policy adds no lexical
fallback (configure it for each deployment). The engine independently excludes
praise episodes when counting evidence and sessions.

A response failing payload-field or JSON Schema checks gets exactly one local
retry with schema path/validator diagnostics only. A second failure is dropped;
network failures, malformed/truncated responses and ungrounded quotes or phrases
are not repaired or relaxed. Expressions must remain exact assistant strings.

Candidate ID is the first 16 hex characters of SHA-256 over compact UTF-8 JSON
`[source.kind, source.session, source.refs]` (object keys sorted where relevant).
Refs are ordered and must be unique. The identity excludes observation time,
model text and output-directory names.

Each candidate is published as `<id>.jsonl`, exactly one JSON line in the
configured output directory. Consumers enumerate **top-level `*.jsonl` only**,
validate schema, and deduplicate by id. A SQLite canonical outbox makes a crash
between publication and marking it delivered safe to retry. Existing candidate
files must match byte-for-byte; conflicts never overwrite existing files.

Publication writes/fsyncs a unique staging file, then atomically hard-links it
to the final name. This requires a local filesystem supporting hard links
(tested on NTFS). `.staging/*.tmp` is retained for audit/no-delete operation and
must not be consumed. The processor performs no automatic deletion or cleanup.
Cursor/outbox/pending turn data and staging files may contain sensitive data:
store state and output on a private local volume outside version control.

SQLite contains `enabled_sources`, `sessions`, `turns`, `outbox`, `events`.
Sessions include all protocol cursor fields. Read progress is committed with
queue admission; extraction progress advances only after a valid emitted file
(or an explicitly valid `none` result), not on transport errors or rejected
responses. Rejected rows remain for status/audit, without automatic re-extraction.
Queued unit contents are operational data, **not** diagnostic logs. The events
table stores only enum codes and hash refs, never exception bodies or text.

## Local extraction and sensitivity

`prompts/extract.txt` is a dedicated generic extraction system prompt. Data is
passed as isolated user/assistant JSON, no tool catalog, persona or history.
Endpoint config accepts literal loopback HTTP only; `localhost` is normalized
to 127.0.0.1. Proxies and redirects are disabled. There is no cloud fallback,
authentication store or shell invocation.

Output must pass schema and grounding checks. Sensitive tags force a normal
candidate to private; configurable keywords inspect both raw turn text and
extraction fields. Levels are ordered normal < unsure < private, and code never
reduces a model's level or removes tags. Keywords alone do not guarantee perfect
semantic detection; ambiguous model results remain unsure for downstream routing.
The processor does not write private/public memory stores or personality files.

## Tests

All fixtures are synthetic and generated at runtime. No real conversation
directory is opened by tests. Set `PROCESSOR_TEST_ROOT` to your preferred local
scratch directory; tests retain all generated fixtures and databases.

```text
python -B -m unittest discover -s tests -v
```

Tests use an ephemeral loopback fake HTTP server and cover preset switches,
concatenated/incomplete frames, selected versions/thinking, message fragments,
tool-result impersonation, other-model exclusion, branches, baseline tails,
queue retries, schemas, monotone sensitivity, idempotence, output recovery,
redirect refusal and concurrent-worker exclusion.
