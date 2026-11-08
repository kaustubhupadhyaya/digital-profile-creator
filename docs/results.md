# Results

All numbers come from one private corpus. The corpus, the trained adapter, the
voice reference clips, the retrieval index, and the run logs are not published.
This repository carries the method and these aggregate results only.

## Headline

| Measure | Result |
|---|---|
| Author vs assistant text, test ROC AUC | 0.997 |
| LoRA fine-tune, held-out perplexity | 439.2 to 7.86 on 787 pairs |
| Fine-tune wall time | 33.5 minutes on one Kaggle Tesla T4 |
| Voice similarity | 0.960 |
| Blind head-to-head, author's writing | 4 of 12 for each system, a tie |

The 4 of 12 is a tie with the Claude-based twin, not a win for the fine-tuned
model. See the head-to-head section below.

## Authorship classifiers

Fixed grouped 80/20 split.

| Task | Test ROC AUC | Reading |
|---|---:|---|
| Author or assistant text | 0.997 | Flat: 0.992 with 5% of the training data, 0.997 from 50% on |
| Author or friend | 0.981 | Flat |
| Author or dating-chat match | 0.817 | Still rising: 0.774 at 50% of the training data, 0.817 at 100% |
| Dictated or typed | 0.946 | Flat from 10% of the data |

Forward-time holdout: author vs friend drops from 0.981 to 0.914 when trained on
messages before a cutoff and tested after it. Later messages differ from earlier
ones, so a texting model needs recent messages.

The dating register is the one place where more data would pay. Its curve rises
0.042 AUC when training data doubles from 50% to 100%.

## Leakage checks

- Random split, dictated vs typed: 1.000. Grouped split: 0.946. The difference is
  the size of the leak, not a model improvement.
- Reply-context features: 0.859 dating-chat AUC with them, 0.816 with a
  label-free previous message, 0.817 with text only. The gain was a label leak
  and was removed.

## LoRA fine-tune

Qwen3-1.7B with LoRA, 2,646 training pairs, 131 validation pairs, 787 held-out
pairs, three epochs, one T4 at fp16.

| Model | Validation perplexity | Test perplexity | Test nats per word |
|---|---:|---:|---:|
| Base, no tuning | 495.9 | 439.2 | 7.173 |
| Epoch 1 | 7.55 | 7.99 | 2.450 |
| Epoch 2, kept | 7.24 | 7.86 | 2.431 |
| Epoch 3 | 7.64 | 8.42 | 2.511 |

On 120 held-out tasks, typed drafts match the author's median length of 19.5
words, start lowercase 94% of the time against 85% for the real messages, and
never open with an assistant preamble. The base model opens with one 96% of the
time. The weak spot is copying: tuned drafts reuse 0.21 to 0.35 of the task's
word trigrams, against 0.11 to 0.14 for the author's real messages.

Serving: 4-bit GGUF, 1,056 MB, 14.3 to 14.6 tokens per second on a laptop CPU,
about 49 seconds for the first reply including model load and 1.9 seconds for
the next.

## Blind head-to-head

Twelve held-out tasks, each drafted by the fine-tuned model and by the
Claude-based retrieval twin.

| Register | Fine-tuned | Claude-based twin |
|---|---:|---:|
| Typed | 3 of 8 | 3 of 8 |
| Spoken | 1 of 4 | 1 of 4 |
| All | 4 of 12 | 4 of 12 |

This is a tie. The 95% Wilson interval for 4 of 12 is 14% to 61%, so the test
shows parity, not a ranking. Each real message appeared twice, once per system,
which lets a reader spot it; the run is not comparable with the earlier 14-of-22
test.

The earlier blind A/B tests put the Claude-based twin's draft as the author's
own in 14 of 22 pairs (typed 11 of 15, spoken 3 of 7). That shows the drafts
pass for the author's writing; with 22 pairs, an exact two-sided binomial p of
0.29 does not show that it beats chance.

## Voice

Fifteen settings, 135 clips.

| Measure | Result |
|---|---:|
| Top speaker similarity | 0.960 |
| Real clips against each other | 0.983 |
| Stock voice | 0.483 |
| Normalised similarity | 0.95 |
| Real word errors in the winning setup | 0 |
| Real-time factor on a quiet laptop CPU | 1.21 |
| Startup per call | about 68 seconds |

The winning setup is ZipVoice-Distill, int8, 4 steps, conditioned on an 8.89
second prompt. In the blind listening test the listener picked a long-prompt
ZipVoice version for all three sentences; Pocket TTS and the short-prompt
ZipVoice version were never picked.

Similarity is channel-sensitive. WavLM x-vectors respond to the microphone and
room as well as the voice, so the listening test, not the score, decides whether
the clone sounds like the person.

## What is not claimed

- The corpus is private and small. No result here says how the method behaves on
  another writer.
- The 4 of 12 is a tie, not a win.
- Voice similarity is one listener's picks on three sentences in English.
- This repository does not reproduce the fine-tune, the voice clone, or the
  private evaluation. See [limitations.md](limitations.md).
