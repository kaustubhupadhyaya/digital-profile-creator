# digital-profile-creator

A small, local pipeline for turning a folder of first-person writing into an
evidence-grounded digital profile. It ingests Markdown, TXT, and JSONL, builds
a SQLite FTS5 index with privacy scopes, measures writing style, and prints a
persona prompt tied to retrieved evidence.

It makes no network calls, uses no model API, and depends only on the Python
standard library.

## Status

v0.1 is a working skeleton, not a research pipeline. It covers ingest, index,
style measurement, retrieval, prompt assembly, and a self-check. It does not
include model calls, fine-tuning, embeddings, voice cloning, or a web UI.

## Documentation

- [docs/method.md](docs/method.md): data classes, grouped 80/20 split, leakage
  controls, LoRA fine-tune, voice-clone setup, and evaluation design.
- [docs/results.md](docs/results.md): the measured classifier, fine-tune, voice,
  and blind-test results, with the 4-of-12 tie stated as a tie.
- [docs/limitations.md](docs/limitations.md): corpus and register limits, voice
  limits, and what is not reproduced.
- [docs/synthetic-eval.md](docs/synthetic-eval.md): the public `twin.py eval`
  check on the fictional demo corpus.

## Requirements

- Python 3.10 or newer
- SQLite with FTS5 (included in normal CPython builds)

## Quickstart

```bash
python twin.py init
python twin.py ingest demo/
python twin.py index
python twin.py fingerprint
python twin.py draft "How would I tell a friend I need a quiet weekend?"
python twin.py eval
```

`draft` prints a prompt. It does not generate the draft. Feed the prompt to a
model of your choice if you want a completion.

Every demo record is synthetic and describes a fictional person. The demo is
safe to publish and is not based on a real person's messages.

## Commands

| Command | What it does |
|---|---|
| `python twin.py init` | Create the local SQLite database. |
| `python twin.py ingest <folder>` | Read `.md`, `.markdown`, `.txt`, and `.jsonl` records. |
| `python twin.py index` | Rebuild the FTS5 index from the records table. |
| `python twin.py fingerprint` | Measure style metrics overall and per register. |
| `python twin.py draft "<text>"` | Retrieve evidence and print a persona prompt. |
| `python twin.py eval` | Check schema, index, fingerprint, and privacy scopes. |

Optional flags:

- `--db PATH` goes before the command. The default is `.twin/twin.db`, or
  `TWIN_DB` when that environment variable is set.
- `ingest` accepts `--source`, `--author`, `--privacy`, and `--register` as
  defaults for records that do not set them.
- `draft` accepts `--limit N`, `--scope general|private|all`, and
  `--register NAME`.
- `fingerprint` and `eval` accept `--json`.

## Record formats

### Markdown

Use a small frontmatter block at the top of the file. One file is one record.

```markdown
---
source: notes
date: 2026-01-18
author: Maya Chen
privacy: private
register: note
title: Optional title
---
The body of the record. Keep the author's own words here.
```

### TXT

Use a short header of `# key: value` lines before the body. One file is one
record.

```text
# source: journal
# date: 2026-02-05
# author: Maya Chen
# privacy: private
# register: journal
# title: February note

The body of the record.
```

### JSONL

One JSON object per line. `text` is required. The other fields are optional
and override any command-line defaults.

```json
{"source": "messages", "date": "2026-02-08", "author": "Maya Chen", "privacy": "private", "register": "chat", "text": "Coffee at eleven?"}
```

Metadata precedence is record field, then command-line default, then a built-in
default. The built-in privacy default is `private`, the register default is
`note`, and the source default is the folder name.

Dates use `YYYY-MM-DD` or `YYYY-MM-DD HH:MM`. Registers are short slugs such as
`note`, `chat`, `email`, `journal`, `spoken`, or `profile`.

## Privacy scopes

Every record has one privacy level:

| Level | Default scope | Meaning |
|---|---|---|
| `public` | `general` and above | Safe to publish or share. |
| `private` | `private` and above | Personal, but used locally. |
| `restricted` | `all` only | Sensitive. Never retrieved by default. |

`draft` uses `private` by default, which includes `public` and `private`.
Use `--scope general` for public-only retrieval or `--scope all` to include
restricted records after an explicit decision.

Scopes are a retrieval filter, not encryption. The SQLite file is plaintext.
See `PRIVACY.md` before ingesting sensitive material.

## How it works

1. `ingest` reads records into a `records` table and marks the index stale.
2. `index` rebuilds an external-content FTS5 table and keeps the privacy
   column on the source records.
3. `fingerprint` computes generic metrics: length, sentence size, type-token
   ratio, lowercase starts, question and exclamation rates, punctuation per
   100 words, emoji per 100 words, and top unigrams and bigrams.
4. `draft` tokenizes the request, retrieves ranked evidence with `bm25`, applies
   the privacy scope, and prints a system prompt with measured style and
   cited evidence.
5. `eval` checks that the schema exists, the index and fingerprint are current,
   records are well formed, and restricted or private records do not leak into
   narrower scopes.

## Known limitations

- `ingest` upserts by `source`, `path`, and `line`. It does not prune records
  for files deleted from the ingest folder. Delete `.twin/twin.db` and
  re-ingest for a clean rebuild.
- Indexing is a full rebuild. This is fine for thousands of records.
- There is no multi-user isolation. Run one local database per person.
- The style metrics are descriptive. They are not a authorship classifier.
- `eval` checks plumbing and scope behavior. It does not score writing quality.

## License

MIT. See `LICENSE`.
