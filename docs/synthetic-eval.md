# Synthetic evaluation

This is the public, synthetic check that ships with the repository. It exercises
the same `twin.py eval` path described in the README on the fictional demo
corpus. It does not measure authorship accuracy, perplexity, or voice quality.
Those results live in [results.md](results.md) and depend on a private corpus.

## What the demo contains

The `demo/` folder has 26 synthetic records for a fictional person:

| Privacy | Registers |
|---|---|
| public: 2 | profile: 2 |
| private: 20 | note: 7, chat: 10, email: 1, journal: 1, spoken: 1 |
| restricted: 4 | note: 2, chat: 2 |

Every record is written for the demo. No record comes from a real person.

## Run it

```bash
python twin.py --db .twin/demo.db init
python twin.py --db .twin/demo.db ingest demo
python twin.py --db .twin/demo.db index
python twin.py --db .twin/demo.db fingerprint
python twin.py --db .twin/demo.db eval
```

The database path is relative to the repository root. `.twin/` is gitignored,
so the run leaves no tracked file behind.

## Expected output

The first four commands report 26 ingested records, an index of 26 records
(public 2, private 20, restricted 4), and a fingerprint over 746 words. The
`eval` command prints:

```text
PASS database (.twin/demo.db)
PASS schema (records, records_fts, meta)
PASS records present (26 record(s))
PASS full-text index (fts=26 records=26)
PASS index current (index_stale=0)
PASS record fields (0 invalid record(s))
PASS register format (6 register(s))
PASS style fingerprint (fingerprint records=26 fresh=True)
PASS privacy scope: restricted excluded (probe all=2 private=0 restricted_hits=0)
PASS privacy scope: general is public only (probe private=1 general=0 non_public_hits=0)

records: 26
privacy: public=2, private=20, restricted=4
registers: chat=12, email=1, journal=1, note=9, profile=2, spoken=1

eval: 10/10 checks passed
```

On Windows the database path prints with backslashes. The checks and counts are
the same.

## What each check means

| Check | What it verifies |
|---|---|
| database | The SQLite file opens and the schema is created. |
| schema | The `records`, `records_fts`, and `meta` tables exist. |
| records present | The database is not empty. |
| full-text index | The FTS row count matches the record count. |
| index current | No ingest happened after the last index build. |
| record fields | No empty text, empty register, or invalid privacy level. |
| register format | Every register is a short slug. |
| style fingerprint | The stored fingerprint covers every record and is fresh. |
| privacy scope: restricted excluded | A probe term from a restricted record is not returned by the default scope. |
| privacy scope: general is public only | A probe term from a private record is not returned by the public scope. |

A failure means the plumbing or the scope filter is broken. Fix the data or the
index and rerun the command. Do not treat a pass as evidence that the profile
writes like anyone: the demo is small, synthetic, and deliberately generic.

## What it does not cover

- authorship ROC AUC, learning curves, or calibration
- LoRA fine-tuning, perplexity, or generation quality
- voice cloning, speaker similarity, or intelligibility
- the private corpus, the private splits, or the blind evaluation

The real study's design is in [method.md](method.md). Its limits are in
[limitations.md](limitations.md).
