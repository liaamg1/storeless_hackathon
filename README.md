# Storeless

## Long video transcription

The worker extracts one clean mono 16 kHz WAV, then transcribes the whole file in a
single faster-whisper call so the model keeps full context. The language is pinned
to `en` by default (`WHISPER_LANGUAGE=auto` re-enables detection), VAD is on and
`condition_on_previous_text` is off to avoid hallucination loops. Speaker labels
are added afterwards by a read-only pass over the finished WAV; they never change
the text. Faster-whisper decodes the file in memory, so multi-hour recordings need
roughly 250 MB of RAM per hour of audio plus the model.

Optional settings in `backend/.env` (defaults shown):

```dotenv
WHISPER_LANGUAGE=en
WHISPER_CPU_THREADS=2
SPEAKER_IDENTIFICATION=true
```

`transcription_progress` log entries report processed and total milliseconds as
segments are produced. No transcript text is written to logs. A job is completed
only after transcription and its atomic save.

Apply backend changes or environment changes with:

```sh
docker compose up -d --build
```

Follow real processing progress with:

```sh
docker compose logs -f backend
```

The existing startup recovery marks jobs interrupted by a shutdown as failed;
restarting a container alone does not mark an incomplete transcript successful.
