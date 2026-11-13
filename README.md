# Storeless

## Long video transcription

The worker reads the temporary mono 16 kHz WAV in short windows, rather than
loading the full recording into memory. Audio, voice detection and model feature
buffers are bounded by window duration; only transcript text accumulates. The
original MP4 is streamed to disk on upload and is retained after processing.

Optional settings in `backend/.env` (defaults shown):

```dotenv
WHISPER_CHUNK_SECONDS=60
WHISPER_CPU_THREADS=2
```

Chunk duration must be 1–120 seconds. Windows include up to two seconds of context
on either side, and transcript timestamps are shifted back to the original
recording. The model is reused, with one inference worker and two CPU threads by
default; FFmpeg decoding uses one thread. Larger or longer recordings take more
time without requiring whole-recording audio/feature buffers in RAM.

Completed windows produce `transcription_progress` log entries with the job ID,
actual processed milliseconds, and total milliseconds. No transcript text is
written to logs. A job is completed only after all windows have been transcribed
and its transcript has been saved atomically.

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
