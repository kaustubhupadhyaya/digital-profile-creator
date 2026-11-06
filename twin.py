#!/usr/bin/env python3
"""digital-profile-creator: a local, no-network digital profile pipeline.

The tool turns a folder of first-person records into a searchable SQLite
index, measures the author's style, and prints a retrieval-grounded persona
prompt. It never calls a model or the network.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sqlite3
import statistics
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterator

VERSION = "0.1.0"
DEFAULT_DB = Path(os.environ.get("TWIN_DB", ".twin/twin.db"))
PRIVACY_LEVELS = ("public", "private", "restricted")
SCOPES = {
    "general": ("public",),
    "private": ("public", "private"),
    "all": PRIVACY_LEVELS,
}
DEFAULT_PRIVACY = "private"
DEFAULT_REGISTER = "note"
SUPPORTED_SUFFIXES = {".md", ".markdown", ".txt", ".jsonl"}
SKIP_PARTS = {".git", ".twin", ".index", ".venv", "__pycache__"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}([T ]\d{2}:\d{2}(:\d{2})?)?$")
REGISTER_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,31}$")
WORD_RE = re.compile(r"[A-Za-z0-9_']+")
QUERY_WORD_RE = re.compile(r"[A-Za-z0-9_]+")
TXT_META_RE = re.compile(r"^\s*#\s*([A-Za-z_]+)\s*:\s*(.*)$")

SCHEMA = """
CREATE TABLE IF NOT EXISTS records (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    path TEXT NOT NULL,
    line INTEGER NOT NULL DEFAULT 0,
    title TEXT NOT NULL DEFAULT '',
    date TEXT NOT NULL DEFAULT '',
    author TEXT NOT NULL DEFAULT '',
    privacy TEXT NOT NULL CHECK (privacy IN ('public', 'private', 'restricted')),
    register TEXT NOT NULL,
    text TEXT NOT NULL,
    ingested_at TEXT NOT NULL,
    UNIQUE (source, path, line)
);
CREATE INDEX IF NOT EXISTS records_register_idx ON records (register);
CREATE INDEX IF NOT EXISTS records_privacy_idx ON records (privacy);
CREATE VIRTUAL TABLE IF NOT EXISTS records_fts USING fts5(
    text,
    title,
    content='records',
    content_rowid='id',
    tokenize="unicode61 remove_diacritics 2"
);
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

UPSERT = """
INSERT INTO records
    (source, path, line, title, date, author, privacy, register, text, ingested_at)
VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
ON CONFLICT (source, path, line) DO UPDATE SET
    title = excluded.title,
    date = excluded.date,
    author = excluded.author,
    privacy = excluded.privacy,
    register = excluded.register,
    text = excluded.text,
    ingested_at = excluded.ingested_at
"""


class TwinError(Exception):
    """A user-facing error."""


def local_now() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def clean(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def unquote(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def open_db(db_path: Path | str) -> sqlite3.Connection:
    path = Path(db_path)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(path)
        db.row_factory = sqlite3.Row
        db.executescript(SCHEMA)
    except sqlite3.OperationalError as exc:
        message = str(exc)
        if "fts5" in message.lower():
            raise TwinError("this SQLite build has no FTS5 support") from exc
        raise TwinError(f"could not open {path}: {message}") from exc
    return db


def set_meta(db: sqlite3.Connection, key: str, value: str) -> None:
    db.execute(
        "INSERT INTO meta (key, value) VALUES (?, ?) "
        "ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (key, value),
    )


def get_meta(db: sqlite3.Connection, key: str) -> str:
    row = db.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return row["value"] if row else ""


def record_count(db: sqlite3.Connection) -> int:
    return int(db.execute("SELECT COUNT(*) FROM records").fetchone()[0])


def validate_date(value: str, where: str) -> str:
    if not value:
        return ""
    if not DATE_RE.match(value):
        raise TwinError(f"{where}: date must be YYYY-MM-DD or YYYY-MM-DD HH:MM, got {value!r}")
    try:
        datetime.fromisoformat(value.replace(" ", "T"))
    except ValueError as exc:
        raise TwinError(f"{where}: invalid date {value!r}") from exc
    return value


def normalize_privacy(value: str, where: str) -> str:
    privacy = (value or DEFAULT_PRIVACY).strip().lower()
    if privacy not in PRIVACY_LEVELS:
        raise TwinError(
            f"{where}: privacy must be one of {', '.join(PRIVACY_LEVELS)}, got {value!r}"
        )
    return privacy


def normalize_register(value: str, where: str) -> str:
    register = (value or DEFAULT_REGISTER).strip().lower().replace(" ", "_")
    if not REGISTER_RE.match(register):
        raise TwinError(
            f"{where}: register must be a short slug like note, chat, or email, got {value!r}"
        )
    return register


def read_text(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError as exc:
        raise TwinError(f"{path}: file is not valid UTF-8") from exc


def parse_pairs(lines: list[str]) -> dict[str, str]:
    meta: dict[str, str] = {}
    for raw in lines:
        line = raw.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, value = line.split(":", 1)
        meta[key.strip().lower()] = unquote(value.strip())
    return meta


def split_frontmatter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text
    for index in range(1, len(lines)):
        if lines[index].strip() == "---":
            return parse_pairs(lines[1:index]), "\n".join(lines[index + 1 :])
    return {}, text


def parse_txt_header(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    meta: dict[str, str] = {}
    index = 0
    while index < len(lines):
        match = TXT_META_RE.match(lines[index])
        if not match:
            break
        meta[match.group(1).lower()] = unquote(match.group(2).strip())
        index += 1
    if index < len(lines) and not lines[index].strip():
        index += 1
    return meta, "\n".join(lines[index:])


def first_heading(body: str) -> str:
    for line in body.splitlines():
        if line.startswith("# "):
            return line[2:].strip()
    return ""


def build_record(
    meta: dict[str, str],
    defaults: dict[str, str],
    source_default: str,
    path: str,
    line: int,
    title_default: str,
    body: str,
) -> dict[str, object]:
    where = f"{path}:{line}" if line else path
    source = clean(meta.get("source")) or defaults.get("source") or source_default
    date = validate_date(clean(meta.get("date")), where)
    author = clean(meta.get("author")) or defaults.get("author", "")
    privacy = normalize_privacy(
        clean(meta.get("privacy")) or defaults.get("privacy", ""), where
    )
    register = normalize_register(
        clean(meta.get("register")) or defaults.get("register", ""), where
    )
    title = clean(meta.get("title")) or title_default
    return {
        "source": source,
        "path": path,
        "line": line,
        "title": title[:200],
        "date": date,
        "author": author[:200],
        "privacy": privacy,
        "register": register,
        "text": body.strip(),
    }


def iter_records(
    folder: Path, defaults: dict[str, str]
) -> Iterator[dict[str, object]]:
    source_default = defaults.get("source") or folder.name or "corpus"
    for path in sorted(folder.rglob("*")):
        if not path.is_file():
            continue
        relative = path.relative_to(folder)
        if any(part in SKIP_PARTS or part.startswith(".") for part in relative.parts):
            continue
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            continue
        where = relative.as_posix()
        text = read_text(path)
        if suffix == ".jsonl":
            for line_number, line in enumerate(text.splitlines(), 1):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError as exc:
                    raise TwinError(f"{where}:{line_number}: invalid JSON ({exc.msg})") from exc
                if not isinstance(row, dict):
                    raise TwinError(f"{where}:{line_number}: each JSONL line must be an object")
                body = row.get("text", "")
                if not isinstance(body, str):
                    raise TwinError(f"{where}:{line_number}: text must be a string")
                meta = {key.lower(): str(row[key]) for key in row if row[key] is not None}
                record = build_record(
                    meta,
                    defaults,
                    source_default,
                    where,
                    line_number,
                    f"{source_default} line {line_number}",
                    body,
                )
                yield record
            continue

        if suffix in {".md", ".markdown"}:
            frontmatter, body = split_frontmatter(text)
            title_default = frontmatter.get("title") or first_heading(body) or path.stem
        else:
            frontmatter, body = parse_txt_header(text)
            title_default = frontmatter.get("title") or path.stem
        yield build_record(
            frontmatter,
            defaults,
            source_default,
            where,
            0,
            clean(title_default) or path.stem,
            body,
        )


def cmd_init(args: argparse.Namespace) -> int:
    db = open_db(args.db)
    count = record_count(db)
    db.commit()
    db.close()
    print(f"initialized {args.db}")
    print(f"records: {count}")
    if count:
        print("next: python twin.py index")
    else:
        print("next: python twin.py ingest demo/")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    folder = Path(args.folder)
    if not folder.is_dir():
        raise TwinError(f"not a folder: {folder}")
    defaults = {
        "source": args.source or "",
        "author": args.author or "",
        "privacy": args.privacy or "",
        "register": args.register or "",
    }
    db = open_db(args.db)
    now = local_now()
    counts: Counter[tuple[str, str]] = Counter()
    ingested = 0
    empty = 0
    for record in iter_records(folder, defaults):
        if not record["text"]:
            empty += 1
            continue
        db.execute(
            UPSERT,
            (
                record["source"],
                record["path"],
                record["line"],
                record["title"],
                record["date"],
                record["author"],
                record["privacy"],
                record["register"],
                record["text"],
                now,
            ),
        )
        counts[(str(record["privacy"]), str(record["register"]))] += 1
        ingested += 1
    set_meta(db, "index_stale", "1")
    set_meta(db, "fingerprint_stale", "1")
    db.commit()
    total = record_count(db)
    db.close()

    print(f"ingested {ingested} record(s) from {folder}")
    if empty:
        print(f"skipped {empty} empty record(s)")
    for (privacy, register), number in sorted(counts.items()):
        print(f"  {privacy:<10} {register:<12} {number}")
    print(f"records in database: {total}")
    print("index stale; next: python twin.py index")
    return 0


def rebuild_index(db: sqlite3.Connection) -> int:
    db.execute("INSERT INTO records_fts (records_fts) VALUES ('rebuild')")
    set_meta(db, "indexed_at", local_now())
    set_meta(db, "index_stale", "0")
    db.commit()
    return record_count(db)


def cmd_index(args: argparse.Namespace) -> int:
    db = open_db(args.db)
    count = rebuild_index(db)
    privacy = {
        row["privacy"]: row["n"]
        for row in db.execute(
            "SELECT privacy, COUNT(*) AS n FROM records GROUP BY privacy"
        )
    }
    db.close()
    breakdown = ", ".join(f"{level}={privacy.get(level, 0)}" for level in PRIVACY_LEVELS)
    print(f"indexed {count} record(s): {breakdown}")
    print(f"database: {args.db}")
    if count == 0:
        print("warning: the index is empty; ingest a folder first")
    return 0


def words(text: str) -> list[str]:
    return [token.lower() for token in WORD_RE.findall(text)]


def emoji_count(text: str) -> int:
    return sum(
        1
        for char in text
        if ord(char) >= 0x1F000 or 0x2600 <= ord(char) <= 0x27BF
    )


def style_metrics(texts: list[str]) -> dict[str, object]:
    texts = [text for text in texts if text and text.strip()]
    word_lists = [words(text) for text in texts]
    lengths = [len(tokens) for tokens in word_lists]
    total_words = sum(lengths)
    total_chars = sum(len(text) for text in texts)
    sentences: list[str] = []
    for text in texts:
        sentences.extend(part for part in re.split(r"[.!?]+", text) if part.strip())
    sentence_lengths = [len(words(sentence)) for sentence in sentences]
    unigrams: Counter[str] = Counter()
    bigrams: Counter[str] = Counter()
    for tokens in word_lists:
        unigrams.update(tokens)
        bigrams.update(" ".join(tokens[index : index + 2]) for index in range(len(tokens) - 1))

    def per_100(count: int) -> float:
        return round(count / total_words * 100, 2) if total_words else 0.0

    def rate(count: int) -> float:
        return round(count / len(texts), 3) if texts else 0.0

    sorted_lengths = sorted(lengths)
    p90 = sorted_lengths[min(len(sorted_lengths) - 1, int(len(sorted_lengths) * 0.9))] if lengths else 0
    punctuation = {
        "period": per_100(sum(text.count(".") for text in texts)),
        "comma": per_100(sum(text.count(",") for text in texts)),
        "question": per_100(sum(text.count("?") for text in texts)),
        "exclamation": per_100(sum(text.count("!") for text in texts)),
        "colon": per_100(sum(text.count(":") for text in texts)),
        "semicolon": per_100(sum(text.count(";") for text in texts)),
    }
    return {
        "records": len(texts),
        "words": total_words,
        "avg_words": round(total_words / len(texts), 1) if texts else 0.0,
        "median_words": round(float(statistics.median(lengths)), 1) if lengths else 0.0,
        "p90_words": p90,
        "chars_per_word": round(total_chars / total_words, 2) if total_words else 0.0,
        "sentences": len(sentences),
        "avg_sentence_words": round(
            sum(sentence_lengths) / len(sentence_lengths), 1
        )
        if sentence_lengths
        else 0.0,
        "type_token_ratio": round(len(unigrams) / total_words, 3) if total_words else 0.0,
        "lowercase_start_rate": rate(sum(1 for text in texts if text[:1].islower())),
        "question_rate": rate(sum(1 for text in texts if "?" in text)),
        "exclamation_rate": rate(sum(1 for text in texts if "!" in text)),
        "ellipsis_rate": rate(sum(1 for text in texts if "..." in text or "\u2026" in text)),
        "emoji_per_100_words": per_100(sum(emoji_count(text) for text in texts)),
        "punctuation_per_100_words": punctuation,
        "top_unigrams": unigrams.most_common(15),
        "top_bigrams": bigrams.most_common(10),
    }


def compute_fingerprint(db: sqlite3.Connection) -> dict[str, object]:
    rows = db.execute("SELECT register, text FROM records ORDER BY register, id").fetchall()
    by_register: dict[str, list[str]] = {}
    for row in rows:
        by_register.setdefault(row["register"], []).append(row["text"])
    return {
        "generated_at": local_now(),
        "overall": style_metrics([row["text"] for row in rows]),
        "registers": {
            name: style_metrics(texts) for name, texts in sorted(by_register.items())
        },
    }


def print_fingerprint(report: dict[str, object]) -> None:
    overall = report["overall"]
    print("style fingerprint")
    print(f"records: {overall['records']}")
    print(f"words: {overall['words']:,}")
    print(f"avg words: {overall['avg_words']}")
    print(f"median words: {overall['median_words']}")
    print(f"p90 words: {overall['p90_words']}")
    print(f"chars per word: {overall['chars_per_word']}")
    print(f"average sentence words: {overall['avg_sentence_words']}")
    print(f"type token ratio: {overall['type_token_ratio']}")
    print(f"lowercase start rate: {overall['lowercase_start_rate']}")
    print(f"question rate: {overall['question_rate']}")
    print(f"exclamation rate: {overall['exclamation_rate']}")
    print(f"ellipsis rate: {overall['ellipsis_rate']}")
    print(f"emoji per 100 words: {overall['emoji_per_100_words']}")
    punctuation = overall["punctuation_per_100_words"]
    print(
        "punctuation per 100 words: "
        + " ".join(f"{name}={value}" for name, value in punctuation.items())
    )
    print(
        "top unigrams: "
        + ", ".join(f"{word} ({count})" for word, count in overall["top_unigrams"])
    )
    print(
        "top bigrams: "
        + ", ".join(f"{phrase} ({count})" for phrase, count in overall["top_bigrams"])
    )

    registers = report["registers"]
    if registers:
        print("")
        print("by register")
        header = (
            f"{'register':<12} {'records':>7} {'words':>7} {'avg':>6} "
            f"{'median':>7} {'p90':>5} {'lower%':>7} {'question%':>10}"
        )
        print(header)
        for name, metrics in registers.items():
            print(
                f"{name:<12} {metrics['records']:>7} {metrics['words']:>7} "
                f"{metrics['avg_words']:>6} {metrics['median_words']:>7} "
                f"{metrics['p90_words']:>5} "
                f"{metrics['lowercase_start_rate'] * 100:>7.1f} "
                f"{metrics['question_rate'] * 100:>10.1f}"
            )


def cmd_fingerprint(args: argparse.Namespace) -> int:
    db = open_db(args.db)
    report = compute_fingerprint(db)
    set_meta(db, "fingerprint", json.dumps(report, ensure_ascii=False))
    set_meta(db, "fingerprint_stale", "0")
    set_meta(db, "fingerprint_at", str(report["generated_at"]))
    db.commit()
    db.close()
    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        print_fingerprint(report)
    return 0


def fts_query(text: str) -> str | None:
    seen: set[str] = set()
    tokens: list[str] = []
    for token in QUERY_WORD_RE.findall(text.lower()):
        if len(token) < 2 or token in seen:
            continue
        seen.add(token)
        tokens.append(token)
        if len(tokens) >= 32:
            break
    if not tokens:
        return None
    return " OR ".join(f'"{token}"' for token in tokens)


def retrieve(
    db: sqlite3.Connection,
    text: str,
    scope: str,
    limit: int = 6,
    register: str | None = None,
) -> list[sqlite3.Row]:
    if scope not in SCOPES:
        raise TwinError(f"unknown scope: {scope}")
    match = fts_query(text)
    if not match:
        return []
    levels = SCOPES[scope]
    placeholders = ", ".join("?" for _ in levels)
    sql = (
        "SELECT r.id, r.source, r.path, r.date, r.title, r.author, r.privacy, "
        "r.register, r.text, bm25(records_fts) AS rank "
        "FROM records_fts JOIN records r ON r.id = records_fts.rowid "
        f"WHERE records_fts MATCH ? AND r.privacy IN ({placeholders})"
    )
    params: list[object] = [match, *levels]
    if register:
        sql += " AND r.register = ?"
        params.append(register)
    sql += " ORDER BY rank LIMIT ?"
    params.append(max(1, int(limit)))
    try:
        return db.execute(sql, params).fetchall()
    except sqlite3.OperationalError as exc:
        raise TwinError(f"search failed: {exc}") from exc


def style_lines(metrics: dict[str, object]) -> list[str]:
    punctuation = metrics["punctuation_per_100_words"]
    return [
        f"records: {metrics['records']}",
        f"avg_words: {metrics['avg_words']}",
        f"median_words: {metrics['median_words']}",
        f"p90_words: {metrics['p90_words']}",
        f"lowercase_start_rate: {metrics['lowercase_start_rate']}",
        f"question_rate: {metrics['question_rate']}",
        f"exclamation_rate: {metrics['exclamation_rate']}",
        f"ellipsis_rate: {metrics['ellipsis_rate']}",
        f"emoji_per_100_words: {metrics['emoji_per_100_words']}",
        "punctuation_per_100_words: "
        + ", ".join(f"{name}={value}" for name, value in punctuation.items()),
        "top_unigrams: "
        + ", ".join(f"{word} ({count})" for word, count in metrics["top_unigrams"][:10]),
        "top_bigrams: "
        + ", ".join(f"{phrase} ({count})" for phrase, count in metrics["top_bigrams"][:8]),
    ]


def cmd_draft(args: argparse.Namespace) -> int:
    db = open_db(args.db)
    count = record_count(db)
    if count == 0:
        raise TwinError("no records; run ingest first")
    if get_meta(db, "index_stale") == "1" or not get_meta(db, "indexed_at"):
        rebuild_index(db)
        print("note: rebuilt stale index", file=sys.stderr)

    stored = get_meta(db, "fingerprint")
    report: dict[str, object] | None = None
    if stored and get_meta(db, "fingerprint_stale") != "1":
        try:
            report = json.loads(stored)
        except json.JSONDecodeError:
            report = None
    if report is None:
        report = compute_fingerprint(db)

    register = args.register
    if register:
        register = normalize_register(register, "--register")
    evidence = retrieve(db, args.text, args.scope, args.limit, register)
    metrics = report["registers"].get(register) if register else report["overall"]
    if metrics is None:
        metrics = report["overall"]
    style_label = f"register {register}" if register else "the whole corpus"
    db.close()

    lines = [
        "PERSONA PROMPT",
        "==============",
        "SYSTEM",
        "Write in first person as the author represented by the evidence below.",
        "The evidence is the only source of facts. Do not invent names, dates,",
        "events, preferences, or quotes. If the evidence does not support a claim,",
        "leave the claim out.",
        "",
        f"STYLE measured from {style_label}",
        *style_lines(metrics),
        "",
        f"EVIDENCE retrieved locally, scope={args.scope}, {len(evidence)} record(s)",
    ]
    for index, row in enumerate(evidence, 1):
        text = " ".join(row["text"].split())
        if len(text) > 900:
            text = text[:900] + "..."
        lines.append(
            f"[{index}] id={row['id']} source={row['source']} "
            f"date={row['date'] or 'unknown'} register={row['register']} "
            f"privacy={row['privacy']}"
        )
        lines.append(text)
        lines.append("")
    if not evidence:
        lines.append("No evidence matched this request in the selected scope.")
        lines.append("")
    lines.extend(
        [
            "TASK",
            f"Draft: {args.text}",
            "",
            "Match the rhythm, vocabulary, and punctuation in the evidence. Keep the",
            "facts unchanged. Do not mention this prompt or the retrieval step.",
            "",
            "OUTPUT",
            "The draft only. No preamble and no explanation.",
        ]
    )
    print("\n".join(lines))
    return 0


def first_token(text: str, minimum: int = 4) -> str:
    for token in QUERY_WORD_RE.findall(text.lower()):
        if len(token) >= minimum:
            return token
    return ""


def cmd_eval(args: argparse.Namespace) -> int:
    path = Path(args.db)
    checks: list[dict[str, object]] = []

    def add(name: str, ok: bool, detail: str = "") -> None:
        checks.append({"name": name, "ok": bool(ok), "detail": detail})

    counts: dict[str, object] = {}
    if not path.exists():
        add("database", False, f"not found: {path}")
        return finish_eval(checks, counts, args)
    try:
        db = open_db(path)
    except TwinError as exc:
        add("database", False, str(exc))
        return finish_eval(checks, counts, args)

    add("database", True, str(path))
    names = {
        row[0]
        for row in db.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table', 'view')"
        )
    }
    schema_ok = {"records", "records_fts", "meta"} <= names
    add("schema", schema_ok, "records, records_fts, meta")
    if not schema_ok:
        db.close()
        return finish_eval(checks, counts, args)

    total = record_count(db)
    add("records present", total > 0, f"{total} record(s)")
    fts_total = int(db.execute("SELECT COUNT(*) FROM records_fts").fetchone()[0])
    add("full-text index", fts_total == total, f"fts={fts_total} records={total}")

    stale = get_meta(db, "index_stale") == "1"
    add("index current", not stale, "index_stale=1" if stale else "index_stale=0")

    invalid = int(
        db.execute(
            "SELECT COUNT(*) FROM records WHERE trim(text) = '' "
            "OR trim(register) = '' OR privacy NOT IN ('public', 'private', 'restricted')"
        ).fetchone()[0]
    )
    add("record fields", invalid == 0, f"{invalid} invalid record(s)")

    registers = [row[0] for row in db.execute("SELECT DISTINCT register FROM records")]
    bad_registers = [name for name in registers if not REGISTER_RE.match(name)]
    add("register format", not bad_registers, f"{len(registers)} register(s)")

    privacy_counts = {
        row["privacy"]: int(row["n"])
        for row in db.execute("SELECT privacy, COUNT(*) AS n FROM records GROUP BY privacy")
    }
    register_counts = {
        row["register"]: int(row["n"])
        for row in db.execute("SELECT register, COUNT(*) AS n FROM records GROUP BY register")
    }
    counts = {
        "records": total,
        "privacy": privacy_counts,
        "registers": register_counts,
    }

    fingerprint_ok = False
    fingerprint_detail = "missing; run fingerprint"
    stored = get_meta(db, "fingerprint")
    if stored:
        try:
            fingerprint = json.loads(stored)
            fp_records = int(fingerprint["overall"]["records"])
            fresh = get_meta(db, "fingerprint_stale") != "1"
            fingerprint_ok = fresh and fp_records == total
            fingerprint_detail = f"fingerprint records={fp_records} fresh={fresh}"
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            fingerprint_detail = "unreadable fingerprint; run fingerprint"
    add("style fingerprint", fingerprint_ok, fingerprint_detail)

    if privacy_counts.get("restricted"):
        row = db.execute("SELECT text FROM records WHERE privacy = 'restricted' LIMIT 1").fetchone()
        token = first_token(row["text"])
        all_hits = retrieve(db, token, "all", 50) if token else []
        private_hits = retrieve(db, token, "private", 50) if token else []
        leaks = [hit for hit in private_hits if hit["privacy"] == "restricted"]
        add(
            "privacy scope: restricted excluded",
            bool(all_hits) and not leaks,
            f"probe all={len(all_hits)} private={len(private_hits)} "
            f"restricted_hits={len(leaks)}",
        )
    else:
        add("privacy scope: restricted excluded", True, "no restricted records")

    if privacy_counts.get("private"):
        row = db.execute("SELECT text FROM records WHERE privacy = 'private' LIMIT 1").fetchone()
        token = first_token(row["text"])
        private_hits = retrieve(db, token, "private", 50) if token else []
        general_hits = retrieve(db, token, "general", 50) if token else []
        leaks = [hit for hit in general_hits if hit["privacy"] != "public"]
        add(
            "privacy scope: general is public only",
            bool(private_hits) and not leaks,
            f"probe private={len(private_hits)} general={len(general_hits)} "
            f"non_public_hits={len(leaks)}",
        )
    else:
        add("privacy scope: general is public only", True, "no private records")

    db.close()
    return finish_eval(checks, counts, args)


def finish_eval(
    checks: list[dict[str, object]], counts: dict[str, object], args: argparse.Namespace
) -> int:
    ok = all(bool(check["ok"]) for check in checks)
    if args.json:
        print(json.dumps({"ok": ok, "checks": checks, "counts": counts}, indent=2))
    else:
        for check in checks:
            status = "PASS" if check["ok"] else "FAIL"
            detail = f" ({check['detail']})" if check["detail"] else ""
            print(f"{status} {check['name']}{detail}")
        if counts:
            privacy = counts["privacy"]
            registers = counts["registers"]
            print("")
            print(f"records: {counts['records']}")
            print(
                "privacy: "
                + ", ".join(f"{level}={privacy.get(level, 0)}" for level in PRIVACY_LEVELS)
            )
            print(
                "registers: "
                + ", ".join(f"{name}={number}" for name, number in sorted(registers.items()))
            )
        passed = sum(1 for check in checks if check["ok"])
        print("")
        print(f"eval: {passed}/{len(checks)} checks passed")
    return 0 if ok else 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="twin.py",
        description=(
            "Build a local, evidence-grounded digital profile: ingest records, "
            "index them with FTS5, measure style, and print a persona prompt."
        ),
    )
    parser.add_argument("--db", default=str(DEFAULT_DB), help=f"SQLite database (default: {DEFAULT_DB})")
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="create the local database")
    init_parser.set_defaults(func=cmd_init)

    ingest_parser = subparsers.add_parser("ingest", help="read a folder of records")
    ingest_parser.add_argument("folder", help="folder containing .md, .txt, or .jsonl files")
    ingest_parser.add_argument("--source", default="", help="default source label")
    ingest_parser.add_argument("--author", default="", help="default author name")
    ingest_parser.add_argument(
        "--privacy", choices=PRIVACY_LEVELS, default=None, help="default privacy level"
    )
    ingest_parser.add_argument("--register", default="", help="default register slug")
    ingest_parser.set_defaults(func=cmd_ingest)

    index_parser = subparsers.add_parser("index", help="rebuild the FTS5 index")
    index_parser.set_defaults(func=cmd_index)

    fingerprint_parser = subparsers.add_parser("fingerprint", help="measure style metrics")
    fingerprint_parser.add_argument("--json", action="store_true", help="print JSON")
    fingerprint_parser.set_defaults(func=cmd_fingerprint)

    draft_parser = subparsers.add_parser("draft", help="print a retrieval-grounded persona prompt")
    draft_parser.add_argument("text", help="what the draft should say")
    draft_parser.add_argument("--limit", type=int, default=6, help="evidence records to retrieve")
    draft_parser.add_argument(
        "--scope",
        choices=list(SCOPES),
        default="private",
        help="privacy scope: general (public), private (default), or all",
    )
    draft_parser.add_argument("--register", default=None, help="restrict evidence to one register")
    draft_parser.set_defaults(func=cmd_draft)

    eval_parser = subparsers.add_parser("eval", help="check index, metadata, and privacy scopes")
    eval_parser.add_argument("--json", action="store_true", help="print JSON")
    eval_parser.set_defaults(func=cmd_eval)

    return parser


def main(argv: list[str] | None = None) -> int:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure:
            try:
                reconfigure(encoding="utf-8", errors="replace")
            except (ValueError, OSError):
                pass
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except TwinError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    except sqlite3.Error as exc:
        print(f"error: sqlite: {exc}", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
