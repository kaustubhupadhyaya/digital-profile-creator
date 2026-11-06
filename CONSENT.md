# Consent

Ingest only material you have the right to use. The tool cannot check consent
for you.

## Minimum checklist

- The records are your own writing, or every person with a reasonable claim to
  them has agreed to this use.
- You are not importing a private conversation from someone who expected it to
  stay private.
- Names, handles, phone numbers, addresses, health details, and employer
  secrets have been removed or marked `restricted`.
- The purpose is clear: local retrieval and style measurement for a personal
  profile, not publication of another person's words.
- You know how to revoke access and delete the database.

## Messages and chats

For a conversation, the safest rule is to keep only your own messages. If the
other side's messages are needed as context, get consent first and redact
anything that is not necessary. A screenshot is not consent. A public post is
not blanket consent to republish.

## Work material

Do not ingest employer-confidential documents, customer data, internal
credentials, or anything covered by an NDA unless you have explicit permission.
A personal writing sample is not a licence to copy work material into a
personal corpus.

## Minors

Do not ingest material about or from minors without the consent of a parent or
guardian and a clear, limited purpose.

## Recording consent

Keep a short local note for each non-public source:

```text
source:
owner:
permission:
scope:
date:
expiry or review date:
```

Store that note with your own records, not in this repository.

## Withdrawal

If someone withdraws consent, remove their material from the source folder,
delete the database, and re-ingest the remaining records. Because v0.1 has no
per-record delete command, a full rebuild is the reliable path.
