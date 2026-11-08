# Method

This document describes the method behind the study in [results.md](results.md).
The study ran on one person's private corpus. This repository publishes the
method and the aggregate results, not the corpus, the trained weights, or the
audio.

## 1. Data classes

| Class | Examples | Handling |
|---|---|---|
| public | Code notes, public writing, published posts | May be published |
| private | Identity, projects, everyday messages, agent prompts | Local only; reviewed before any external use |
| restricted | Health, sexual content, third-party personal data, one-to-one chats | Local only; excluded from external training and never published |
| secret | Passwords, tokens, keys, cookies, card numbers, one-time codes | Never stored in the corpus, never logged, never sent |

The corpus is one row per message: source, date, register, privacy class, text,
and context. Registers separate typed prompts to coding agents, cleaned
dictations, raw speech transcripts, dating messages, and messages to friends.
The positive class is the author's own text. The negative class is assistant
text from the same coding-agent sessions, or the other person's messages in a
chat.

Aggregate size: 8,004 author records and 168,735 author words. The comparison
class has 6,122 assistant text blocks, 459 dating-chat messages, and 4,227
friend messages. Speech data: 18.71 hours in 2,259 recordings.

## 2. Grouped 80/20 split

A record-level random split leaks. Messages from one session, chat, or day land
on both sides and the model learns the occasion instead of the author.

Groups:

- one coding-agent session, with the author's prompts and the assistant's
  replies sharing one key
- one dictation day
- one dating chat
- one day of a friend thread
- a near-duplicate cluster, so the same utterance kept twice (199 clusters)
  cannot straddle the split

The split is fixed by hashing the group id. Groups whose hash falls in the
bottom 20% of the range go to test. New data does not move an existing group,
so the test set stays stable across rebuilds. No group appears on both sides.
Validation uses five-fold grouped cross-validation inside the training side
only.

A second, forward-in-time split takes the latest 20% of each source by date. It
answers a different question: does a model trained on old messages hold on
newer ones.

| Task | Train, positive / negative | Test, positive / negative | Test groups |
|---|---:|---:|---:|
| Author or assistant text | 2,875 / 2,875 | 802 / 802 | 67 |
| Author or dating-chat match | 300 / 337 | 107 / 122 | 11 chats |
| Author or friend | 3,150 / 3,372 | 761 / 855 | 56 days |
| Dictated or typed | 142 / 608 | 24 / 144 | 30 sessions |

## 3. Leakage controls

- Grouped split. On the same data, a random split scores dictated against typed
  at 1.000; the grouped split scores 0.946. 104 of 156 sessions hold only typed
  or only dictated prompts, which is why the random split can recognise the
  session's topic.
- Shared group key. In a coding-agent session the author's prompt and the
  assistant's reply share a group. A random split would separate a prompt from
  its own reply.
- Near-duplicate clusters. The same utterance kept as a dictation and as a
  prompt is one group.
- Label-free context only. An earlier scorer used reply-context features built
  from the other side's last message. That message is selected using the label,
  so the features reveal whose turn it is. With them, dating-chat AUC was 0.859;
  with the previous message of either side, 0.816, the same as text alone at
  0.817. The ranking path never used reply context, and the feature set was
  corrected.
- Frozen test set. Settings and the epoch were chosen on validation, never on
  test. Learning curves change only the amount of training data and score the
  same fixed test split.
- Privacy passes before any external step. A term screen, a model review of
  every candidate record, and a hand read of every flag. Restricted records
  stayed local. The cloud fine-tune received only the reviewed private-scope
  pairs.

## 4. Authorship classifier

Features: hashed character n-grams, hashed word n-grams, masked style n-grams,
and 88 numeric style features (length, casing, punctuation, emoji, spacing,
spelling habits, question rate).

Model: logistic regression. It was chosen over a character CNN trained from
scratch because the data is small. The CNN trails the linear model on all four
tasks and comes closest only on the friend register, the one task with more than
1,500 training samples per median word.

Learning curves: train on a share of the training groups, three draws for the
linear model, and score the same test split. A curve counts as flat when
doubling the data from 50% to 100% adds less than 0.01 AUC.

## 5. LoRA fine-tune

Pairs: one neutral task sentence mapped to the author's real message, plus a
register tag. The task sentence was written by a model from the message, with
the message itself as the only content. Pairs came from the reviewed
private-scope text only.

Splits: 2,646 training pairs, 131 held out to choose the epoch, 787 held-out
test pairs on the fixed grouped split.

Model and training:

- base: Qwen3-1.7B
- adapter: LoRA rank 32, alpha 32, on every linear layer
- learning rate 2e-4, 3 epochs
- loss on the reply tokens only, prompt masked
- thinking mode off
- one Kaggle Tesla T4, fp16, 33.5 minutes for the whole run

Epoch 2 was kept. Epoch 3 was worse on validation and test, the first sign of
memorising training replies.

Serving: the adapter was merged and quantized to a 4-bit GGUF of 1,056 MB, then
served by llama.cpp on a laptop CPU. This repository does not include the
adapter or the quantized file.

## 6. Voice-clone setup

Goal: speak a draft in the author's voice, locally, without sending audio off
the PC.

Data: 18.71 hours across 2,259 recordings, all from the author's own dictation
app. Restricted and held recordings were removed before selection. Clips were
screened for duration, language, speech rate, clipping, silence, pauses, and
high-frequency energy, then ranked by transcription confidence,
signal-to-noise ratio, quiet share, and noise floor.

Approach: zero-shot cloning from one short reference clip. A voice fine-tune was
not run. It needs a GPU and would send the author's audio to another machine.

Candidates tested:

- Pocket TTS 100M, a fast CPU model
- ZipVoice-Distill 123M, an ONNX model that needs a prompt clip and its
  transcript

Fifteen settings across the two models, 135 generated clips. Variables were the
model, the reference clip, prompt length, int8 versus fp32, 2 versus 4 threads,
and 4 versus 8 steps.

Scoring:

- speaker similarity: cosine between WavLM x-vectors of a generated clip and
  the centroid of six real hold-out clips
- anchors: ceiling 0.983, the mean real clip against the centroid of the other
  five; floor 0.483, a stock voice
- normalised score: (similarity - floor) / (ceiling - floor)
- intelligibility: faster-whisper small, int8, greedy English, word error rate
  against the input text

The automatic score only screens. The choice was made by a blind listening
test: the four best-scoring setups, three sentences, shuffled and
loudness-matched. The listener picked the version closest to the real voice.

## 7. Evaluation design

Three separate questions, three separate tests:

1. Does the classifier separate author from non-author? Fixed grouped test, ROC
   AUC, plus learning curves to show whether more data of the same kind would
   help.
2. Does the generator write like the author? Blind A/B: a held-out real message
   and a draft, listener picks which one the author wrote. Chance is 50%.
3. Does one system beat another? Blind head-to-head: the same held-out task
   drafted by two systems, listener picks the one closer to the author. Each
   real message appears once per system in this design.

Reported uncertainty: exact binomial or Wilson intervals, not just a
percentage. A small panel can show parity but cannot rank two close systems.
The head-to-head with 12 pairs per system is a tie; a 20-point gap would need
about 95 pairs per system.

Voice uses the same logic: automatic similarity for screening, blind listening
for the decision.

The public `twin.py eval` demo is a plumbing check on synthetic records. It is
described in [synthetic-eval.md](synthetic-eval.md) and is not a reproduction of
the private study.
