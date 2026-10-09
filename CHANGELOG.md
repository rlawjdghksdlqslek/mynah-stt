# Changelog

All notable changes to this project are documented here.

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).
While the major version is 0, a breaking change raises the minor version.

## [0.4.2] - 2026-10-09

### Fixed

- **A broken decode is now retried through the beam-search path.** Whisper's
  tokenizer splits hangul across byte-level tokens whose boundaries do not
  line up with the characters: `물리적` is four tokens, the second of which
  straddles two syllables. One mis-sampled token therefore corrupts several
  characters at once. On a 91-minute meeting that was 80% silence, 6 of 81
  chunks came back carrying U+FFFD together with fragments of Arabic, Greek
  and Chinese. `has_loop()` only detects repetition, so nothing retried them
  and the garbage reached the transcript. U+FFFD is never valid output, so it
  now triggers the same WhisperX retry a repetition loop does — the beam path
  recovered the same chunk cleanly where MLX, which has no beam search, did
  not. Unlike a loop it does not mark a gap, because the rest of the text is
  usually intact. Across every session recorded so far this affects 9 of 375
  chunks, about 2.4%.
- **The waiting overlay no longer promises a duration.** It claimed the final
  chunk takes "usually under 15s". Decode time tracks the number of tokens
  generated, not the length of the audio: over twelve consecutive 60-second
  chunks of one real meeting the same engine ran between 1.9x and 11.6x
  realtime, and predicting from the running median was off by 100% at the
  median and 1849% at worst. It now shows elapsed time only.

### Changed

- **The documentation no longer claims VAD is always on.** pyannote VAD runs
  only inside `transcribe()`, which since 0.3.0 is reached only with
  `--diarize`; the chunk path and `transcribe_wav()` have none. This is left
  as it is on purpose: enabling faster-whisper's VAD on a 60-second chunk of
  the near-silent meeting above discarded every word in it. CLAUDE.md now
  records that measurement so the setting is not "fixed" back.

## [0.4.1] - 2026-10-08

### Fixed

- **Stopping a recording twice finalized the same session twice.** The guard
  only checked that a recorder object existed, and stopping does not clear it,
  so a second press ran the whole path again: a second progress screen, a
  second `finalize_session`, and a tail that could be transcribed and appended
  to the transcript twice. A modal overlay now covers the record screen while
  the last chunk is transcribed, blocking every key and click, with an
  explicit guard behind it for a press queued before the overlay mounts.
- **The record screen no longer offers controls that do nothing.** While the
  final chunk was transcribing, `Pause` stayed clickable and relabelled itself
  as though recording had resumed, the level meter kept drawing, and the
  footer still advertised `Space` and `S` — on a recording that had already
  ended. The overlay replaces the dots animation added in 0.4.0 and shows how
  long the wait has run.

## [0.4.0] - 2026-10-08

The glossary and the term-review screen are gone. Both were measured against
this project's own recordings and both were doing more harm than good.

### Breaking changes

- **The glossary is removed**, along with `--edit-glossary`, the Glossary tab
  and `glossary.txt`. Terms are no longer passed to Whisper as an
  `initial_prompt`. Across 49 of this project's own transcripts the glossary
  term "Slack" appeared 154 times, of which 149 were fabricated: 9 inside the
  echoed prompt sentence and 140 inside repetition runs, in meetings where the
  word was never spoken. Whisper treats `initial_prompt` as text that preceded
  the audio, so on an unclear stretch it continues that text instead of
  transcribing. Measured on one 90-second clip, dropping it took the
  transcript from 258 to 379 characters. An existing `glossary.txt` is ignored
  and can be deleted.
- **Term review is removed**, along with `--suggest-replacements`,
  `--scan-dir`, the Analyze tab, the "Review terms" badge and the `T` key. It
  scanned `~/Documents/mynah-output`, which recorded sessions never write to,
  so it reported nothing for two releases. Pointed at the right folder it
  produced 209 clusters whose largest entries merged ordinary distinct words
  (시간/시작/기준/기존/기본, 기능/가능, AI/API/UI). Jamo edit distance is too
  coarse for two-syllable Korean.
- **Dependencies `jamo` and `kiwipiepy` are dropped**; they existed only for
  that clustering.
- The term screen is now a single Replacements screen (`G`), and
  `--edit-replacements` opens it.

### Fixed

- **Replacement rules no longer match inside a word.** An `ok -> OK` rule had
  turned "looked" into "loOKed" and "booking" into "boOKing" in already
  shipped transcripts. ASCII rules now require that no other ASCII letter or
  digit touches the term, so `ok입니다` is still corrected while `looked` is
  left alone. `\b` is deliberately not used: it is Unicode-aware, so hangul
  counts as a word character and every rule would stop firing next to a
  Korean particle.
- **The recording screen no longer looks frozen after Stop.** The elapsed
  clock used to be stopped before the final chunk was awaited, leaving one
  static line on screen for as long as that chunk took. It now animates. The
  Stop button additionally ran that wait on the screen's own message pump,
  which blocked every repaint; it is scheduled off the pump now.
- **`--diarize` output is guarded against repetition loops.** The loop guard
  had only been wired into the non-diarize path, so the same audio produced a
  gap marker on one path and a wall of repeated words on the other.
- A malformed WAV header can no longer abort a run: the audio-length figure in
  the progress line is cosmetic and now falls back to nothing.

### Added

- The progress screen reports how much audio it is about to transcribe, which
  gives the elapsed clock a scale.

### Changed

- Documentation now gives the real config directory on macOS
  (`~/Library/Application Support/mynah/`); it had said `~/.config/mynah/`,
  which is not where `platformdirs` puts it on this platform.

## [0.3.0] - 2026-09-17

A UI/UX pass over the whole app, plus GPU transcription for file input.
Read the **Breaking changes** section before upgrading.

### Breaking changes

- **Python 3.10 is no longer accepted.** The supported range is now 3.11–3.13
  (`requires-python = ">=3.11,<3.14"`). The floor moved because
  `config/settings.py` imports `tomllib`, which is stdlib only from 3.11 —
  3.10 never actually worked. The ceiling is whisperx, which declares
  `Requires-Python <3.14` in every published version.
- **Python 3.13 is now supported.** `audioop` left the stdlib in 3.13; the new
  `audioop-lts` dependency restores it on 3.13 and later.
- **Recorded sessions write `<session-id>.txt`, not `meeting.txt`.** Every
  recording used to produce a file with the same name, so they were
  indistinguishable outside their folders. Scripts that read `meeting.txt`
  need updating. The archived audio is still `meeting.wav`.
- **The failed-chunk marker is English.** A chunk that cannot be transcribed
  now reads `[00:01:05-00:02:05 transcription failed: repetition loop]`
  instead of the previous Korean text. Anything grepping the old string needs
  updating.
- **File input without `--diarize` runs on MLX instead of WhisperX.** Same
  model, different engine, so wording may differ slightly between runs made
  before and after this release. `--diarize` is unchanged.
- **The `chunk_seconds` setting was removed.** Nothing ever read it; chunk
  length comes from constants in `core/record.py`. An existing
  `config.toml` containing it still loads, and the key is ignored.

### Fixed

- **`Esc` while recording no longer deletes the recording.** It used to remove
  the session folder with no confirmation, so one reflexive keypress during a
  meeting destroyed the only copy of it. `Esc` now leaves the screen with the
  session intact; the main screen's recovery banner offers finish, resume or
  discard, and discard still needs two presses.
- **The first-run download warning checked the wrong model.** The cache probe
  only knew the WhisperX repository, so MLX users — the default on Apple
  Silicon — were told a 3 GB download was pending when it was not, and told
  the model was cached when it was not. `--doctor` reported the same error.
- **The progress screen's "Cancel" did nothing.** It logged a cancellation
  message and kept running. The binding is now `Back` and is inert until the
  run finishes, which is what actually happens.
- **"New recording" on the result screen returns to the main screen instead of
  starting a recording.** It now starts one.
- **The recording screen showed the placeholder text `Saving to: session
  folder`.** It shows the real session path.
- **`--doctor` rejected Python 3.13** although the package allowed it,
  printing a failure and returning exit code 1 on a healthy install.

### Added

- **No-input warning while recording.** If the level stays near silence for
  about five seconds, the status line warns that the microphone may be muted
  or the wrong input device selected. A dead microphone used to be discovered
  only after the meeting.
- **First-chunk hint.** The live pane explains that the first lines appear
  after about a minute, instead of sitting empty and looking hung.
- **Elapsed clock on the progress screen**, so a long run is visibly alive.
- **`O` opens the recordings folder** in Finder from the main screen.
- **The file picker lists only audio.** Folders and decodable extensions are
  shown; everything else is hidden, including dotfiles. Picking an
  undecodable file used to fail only after the pipeline had started.
- **The main screen responds to mouse clicks** on its entries.

### Changed

- **Settings save as you change them.** The Save and Cancel buttons are gone.
  At 80x24 the screen was taller than the terminal and the Save button sat
  below the fold; six toggles did not justify a commit step.
- **Interface text and transcript markers are English throughout.** Korean
  strings had crept into an otherwise English interface, and one of them
  reached the transcript itself.
- **Muted text contrast raised** from `#595959` to `#8C8C8C` on the dark
  background, which moves it from roughly 2.5:1 to above the 4.5:1 minimum.

### Removed

- **`tui/screens/editor.py`.** It duplicated the glossary and replacement
  editors that the term manager already provides. `--edit-glossary` and
  `--edit-replacements` open the term manager's matching tab.

### Performance

- **File input transcribes on the GPU.** WhisperX is CPU-only and measures
  0.86x realtime, so an hour of audio took over an hour. Everything except
  `--diarize`, which needs WhisperX word alignment for speaker assignment,
  now uses the MLX path the live recorder already used. Measured: 90 s of
  meeting audio in 26 s including the model load. Hallucination loops are
  caught per segment and replaced with a gap marker rather than retried over
  the whole file.
- **The faster-whisper model is cached between calls.** The loop-retry path
  rebuilt it from disk — about 1.5 GB — once per bad chunk.

## [0.2.0] - 2026-08-21

- Live transcription during recording, in 60–90 s chunks cut at silence.
- Crash-safe sessions: headerless PCM plus a JSONL transcript, recoverable
  from the main screen after an unclean exit.
- MLX backend for Apple Silicon GPUs, with automatic fallback to WhisperX.
- Automatic gain correction, the largest single cause of hallucination loops.
- Term manager: glossary, replacements, and phonetic clustering of
  misrecognized terms across past transcripts.
- `mynah --doctor` health check.

## [0.1.0] - 2026-05-09

- First release: audio file in, transcript out, with optional speaker
  diarization, timestamps, and denoising.

[0.4.2]: https://github.com/rlawjdghksdlqslek/mynah-stt/compare/v0.4.1...v0.4.2
[0.4.1]: https://github.com/rlawjdghksdlqslek/mynah-stt/compare/v0.4.0...v0.4.1
[0.4.0]: https://github.com/rlawjdghksdlqslek/mynah-stt/compare/v0.3.0...v0.4.0
[0.3.0]: https://github.com/rlawjdghksdlqslek/mynah-stt/compare/v0.2.0...v0.3.0
[0.2.0]: https://github.com/rlawjdghksdlqslek/mynah-stt/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/rlawjdghksdlqslek/mynah-stt/releases/tag/v0.1.0
