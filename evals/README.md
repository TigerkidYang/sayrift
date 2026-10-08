# Evaluation sets

Default unit tests are offline and do not need audio fixtures or a model key.
Model benchmarks and desktop E2E are opt-in and make billable API calls.

## Speech recognition

The public source snapshot contains reference text, **not recordings**. Previously generated
Edge TTS clips are excluded because redistribution permission was not established. Do not
upload personal speech, or treat third-party TTS output as automatically licensed for redistribution.

To evaluate with your own recordings:

1. Create a private directory outside the repository, for example `../sayrift-eval/`.
2. Create `samples.tsv` with `id<TAB>voice<TAB>reference text`; set voice to `human` for your recordings.
3. Put recordings in `audio/<id>.ogg` underneath that directory. Use 16 kHz mono OGG/Opus, 24 kbps.
4. Choose models and a small sample count deliberately. The following calls the real API:

```powershell
uv run tools/bench_asr.py --samples-dir ../sayrift-eval --models openai/gpt-transcribe --repeat 1
```

If conversion is needed, use your own licensed encoder installation, for example:

```sh
ffmpeg -i your-recording.wav -ar 16000 -ac 1 -c:a libopus -b:a 24k audio/example.ogg
```

The reference text in `asr/samples.tsv` may be read aloud for your own tests. Its original `voice`
column records an old synthesis preset, not a claim that human recordings are bundled.

Desktop `tools/e2e_dictation.py` expects `zh_disfluent.ogg`, and with `--ask` also
`zh_ask_formal.ogg` and `zh_ask_question.ogg`, under `evals/asr/audio/` using the matching reference text.
That audio directory is ignored by Git. Missing clips are rejected before taking desktop focus.
Coordinate before running E2E while someone is typing; it backs up and restores the clipboard.
For Android mock testing, set `SAYRIFT_TEST_AUDIO` to your own clip before running the emulator helper.
The mock returns fixed sample text and does not assess recognition quality.

## Text evaluation

`polish/cases.jsonl` and `ask/cases.jsonl` contain synthetic text cases. These are part of the MIT-licensed
project. `transcript` is input data, `context` is optional, `expect` is human guidance. Automated
checks use fields such as `must`, `must_any`, `must_not`, `max_ratio`, `max_chars` and `min_lines`.

```powershell
uv run python tools/bench_polish.py --repeat 3
uv run python tools/bench_ask.py --repeat 3
```

These commands cost money. Add a reproducing case before changing prompts, then compare the primary
and fallback models. Avoid overfitting checks to a single valid phrasing. Keep concurrency at six
or below. Model availability, cost and latency can change; historical tables are not current guarantees.

`polish/typeless-2026-10-08.json` preserves eight synthetic inputs with observed official Typeless
outputs and Sayrift comparisons. It is an observation record, not an exact-match gold standard:
official recognition mistakes and missing constraints must not become desired behavior. See
[the history-scenario report](../docs/typeless-history-comparison-2026-10-08.md) for provenance,
audio-versus-text comparison boundaries, regression results and remaining gaps. Personal history
and generated audio stay outside the repository.
