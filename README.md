# Speech Gateway API Tester

Sanitized desktop QA utility based on professional speech-gateway testing work. Python/Tkinter UI, cookie-based session authentication, multipart audio upload, response inspection and bounded repeated requests. QA workflow direction and outcome review were owned by the author; implementation used AI assistance.

## Features

- Login and session-cookie extraction.
- Audio requests with a session bearer token and a separate gateway API key.
- Single requests or a bounded loop stopping on an error.
- Background workers and a UI event queue.
- Local metadata history without explicitly storing passwords or API keys.

The default host is `https://example.invalid`. No real service, audio samples, credentials or request history is included. This client targets the documented gateway contract in `client.py`, not the OpenAI API directly. TLS verification is enabled by default.

## Run

Requires Python 3.11+ with Tkinter. No external Python packages are required.

```sh
python main.py
```

Enter a compatible test-service URL, credentials and an audio file that you are allowed to send. Request bodies are shown in the local UI and may contain sensitive response data. Local `history.jsonl` contains filenames and usage metadata; it is excluded from Git.

## Offline tests

```sh
python -m unittest discover -s tests -v
```

These tests verify client behavior using synthetic data. They do not establish live gateway availability or transcription accuracy. No company service or live pass is claimed.
