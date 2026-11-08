# Limitations

The results in [results.md](results.md) come from one private corpus. Treat them
as a measured personal system, not as a benchmark result.

## Small private corpus

- One person. Nothing in the study says how the method works on another writer,
  language, or register.
- 168,735 author words and 18.71 hours of speech are enough to fine-tune a small
  model, not enough to pretrain one. Pretraining a language model from scratch
  is out of reach at this size.
- The comparison class is uneven. Assistant text comes from coding-agent
  sessions, not from a system trying to imitate the author. A harder test is the
  author's accept or reject on real drafts.
- The fine-tune's task sentences were written from the author's real messages,
  so they carry the message's specifics. The tuned drafts lean on the task's
  wording more than the author does: 0.21 to 0.35 of the task's word trigrams,
  against 0.11 to 0.14 in the author's real messages.

## Register and data limits

- The dating register is short: 229 test messages from 11 chats, and its
  learning curve is still rising. More chats would raise it.
- The dictated-or-typed test side has 24 dictated prompts. The result is
  directionally useful and not precise.
- The friend register is two long threads covering about three years. It is not
  a sample of all friend conversations.
- Speech transcripts come from automatic recognition. They carry the author's
  words but not the author's punctuation, and they differ from the dictation
  app's own text by about 4.7% on a 383-word check.
- The time holdout shows the friend register losing 0.067 AUC on later messages.
  A model built on old messages is not a model of the author's current texting.
- The blind panel is one listener on a small number of pairs. The 14-of-22 A/B
  result has an exact two-sided binomial p of 0.29, so it shows the drafts pass
  for the author, not that they beat chance.
- The 4-of-12 head-to-head has a 95% Wilson interval of 14% to 61%. It shows
  parity between the fine-tuned model and the Claude-based twin, not a ranking.
  A 20-point gap would need about 95 pairs per system. Each real message
  appeared twice in that run, once per system, so a reader could spot it; the
  run is not comparable with the earlier 14-of-22 test.

## Voice limits

- The similarity floor is a stranger recorded in a studio, while the real clips
  come from one microphone at 16 kHz. WavLM x-vectors respond to the recording
  channel as well as the voice, so the scores mix the two.
- The blind listening test has three sentences and one listener's picks. It
  ranks the setups for that ear, not in general.
- English only. The Hinglish line was not generated.
- ZipVoice's prompt transcript came from Whisper and was not corrected by ear.
  ZipVoice copies a voice through those words.
- One sample per sentence and setup. No voice fine-tune was tested; it would
  need a GPU and would send the author's audio to another machine.
- Similarity 0.960 sits between the real-clip ceiling of 0.983 and the stock
  voice floor of 0.483. It is an anchor-based score, not a probability that the
  clone is the author.

## No public weights or audio

This repository does not include:

- the private corpus, or any text, chat, or transcript from it
- the LoRA adapter, the merged model, or the 4-bit GGUF
- the voice reference clips, generated audio, or the voice model weights
- the retrieval index, the per-record splits, the run logs, or the evaluation
  answer keys
- the private scripts that build the corpus and run the cloud jobs

The public `twin.py` covers ingest, index, style measurement, retrieval, prompt
assembly, and the synthetic `eval` check. It does not call a model, fine-tune,
clone a voice, or reproduce the private study.

## What is not reproduced

- The authorship classifier results, because the corpus and the exact splits are
  private.
- The LoRA fine-tune, because the pairs and the adapter are private.
- The voice comparison, because the audio and the reference clips are private.
- The blind tests, because the real messages and the answer keys are private.
- The privacy screens, because they operate on the private corpus.

The synthetic demo in [synthetic-eval.md](synthetic-eval.md) checks that the
public pipeline still ingests, indexes, fingerprints, and enforces privacy
scopes. It is not a quality benchmark and it uses a fictional person.

## Privacy and consent

The method depends on consent and provenance. Every text and every recording
must belong to the author or be cleared for this use. Third-party messages,
health details, and one-to-one chats belong in the restricted class and stay
local. A voice source needs provenance and the speaker's own confirmation, not
just a similarity score.

Publishing aggregate numbers, docs, and code is not the same as publishing the
corpus. A style fingerprint or a persona prompt can reveal private facts even
when it contains no verbatim quote. Review any derived output before sharing it.
