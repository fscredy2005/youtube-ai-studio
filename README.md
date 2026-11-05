# YouTube AI Studio — browser-based video analysis

A complete, simple Streamlit application for extracting **accessible public YouTube captions**, summarizing them, navigating timestamps, searching text, asking questions, transcribing authorized uploaded media, comparing videos, and exporting TXT/SRT/Markdown/PDF.

> **Important limitations**: Free mode is **extractive** (selects actual caption passages). It is not generative AI, and it cannot translate captions. Add an optional Gemini API key for genuine generative summaries, bilingual output, and Q&A. Video caption access may fail from hosted server IP addresses, even when captions are visible in a browser. Uploaded media or pasted transcripts are fallback inputs.

## Features

| Feature | Free / no key | With Gemini API key |
|---|---|---|
| YouTube URL / Shorts / youtu.be validation | ✅ | ✅ |
| Metadata (title, channel, thumbnail) | Best effort via oEmbed | Same |
| Original captions / timestamps | ✅ if accessible | Same |
| YouTube-provided translated captions (TXT/SRT) | ✅ if available | Same |
| Summary: five layouts | Extractive source passages | Generative AI summary |
| Automatic long-transcript chunking | Global time-window selection | Two-pass summarization |
| Output in another language | ❌ | ✅ |
| Transcript search | ✅ | ✅ |
| Ask questions | Keyword-based source excerpts | Generative grounded Q&A |
| Suggested timeline | ✅ (not official chapters) | Same |
| Upload and transcribe own audio/video | ✅ CPU Whisper tiny, may be slow | Same |
| Exports TXT / SRT / Markdown / PDF | ✅ | ✅ |
| Session history and side-by-side compare | ✅ (session only) | ✅ |
| Download YouTube audio/video | Off by default; admin opt-in and authorization required | Same |

## Simplest deployment: Streamlit Community Cloud (free tier)

As of November 2026, [Streamlit Community Cloud](https://docs.streamlit.io/deploy/streamlit-community-cloud) offers free hosting with resource limits; plans and limits can change. A free GitHub account is required.

1. Create a new GitHub repository, e.g. `youtube-ai-studio`. **Public** is the easiest way to share the source; use a private repo if you prefer, subject to Cloud eligibility.
2. Upload **all files and folders** in this project. The `app.py`, `requirements.txt`, `studio/`, `.streamlit/config.toml`, and `README.md` must be preserved. Do **not** upload `.env` or `.streamlit/secrets.toml`.
3. Visit **https://share.streamlit.io/** and sign in with GitHub.
4. Select **Create app** → **I have an app** → your repository → branch `main` → main file `app.py`.
5. (Optional) Under Advanced settings → Secrets, add this configuration **without putting it in GitHub**:

   ```toml
   GEMINI_API_KEY = "your-key-from-Google-AI-Studio"
   GEMINI_MODEL = "gemini-2.5-flash-lite"
   ```

6. Deploy. Your app opens on a `*.streamlit.app` address in any browser. Allow it to install dependencies.
7. Paste a public YouTube URL and click **Analyze video**. If YouTube blocks the server, use the **More options** section for pasted text or an authorized media upload.

See: [official deployment walkthrough](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/deploy) and [secrets documentation](https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/secrets-management).


### Transcript Integrity Check

After analyzing a video, the results page automatically checks caption timestamps for:

- gaps of at least 15 seconds between caption intervals,
- out-of-order or invalid timestamps,
- captions that start late or end early **when an independent video duration is available**.

If the video duration is not available, enter the duration displayed in YouTube (e.g. \`26:49\`) into **Video duration shown on YouTube**. The last subtitle timestamp is deliberately **not** treated as an independent video duration. Expand **Inspect timestamps, possible gaps and limitations** for suspicious intervals, which link back to YouTube.

Possible statuses: **No obvious timing issues**, **Review recommended**, **Partial check**, **Cannot assess**. Even a clean check cannot guarantee that every spoken word was captured. Gaps may indicate silence, music or missing captions. This audit runs locally, requires no extra API key and does not consume AI credits.

### Costs, quotas and privacy

- **Application hosting:** free within Community Cloud resource restrictions; cold starts/limited uptime possible. Not a guaranteed always-on production service.
- **Caption extraction:** no API key, but YouTube can block server addresses, captions can be disabled, and YouTube terms apply.
- **Free summarization:** open-source, deterministic extractive implementation; no inference API cost. No translation.
- **Whisper audio transcription:** first invocation downloads an open-source small model; downloads/compute are subject to network and hosting limits. Restricted to 50MB and 30 minutes per file. May fail on a small free instance.
- **Gemini:** optional, managed by Google; free quotas and prices depend on current model, region, and account. Check [official Gemini rate limits](https://ai.google.dev/gemini-api/docs/rate-limits). Using a paid-key account can incur charges.
- **Privacy:** no server database. Transcripts and summaries are kept in Streamlit's browser session and may be forwarded to Google if Gemini is enabled. Streamlit and hosting logs may still record application events. If a public app uses your server-side Gemini key, visitors can consume your API quota. Restrict access if you want the key only for yourself.

### Running locally (optional, for developers)

```bash
python -m venv .venv
# Windows PowerShell: .venv\\Scripts\\Activate.ps1
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

### Audio transcription

The default requirements include `faster-whisper` and `PyAV`. Streamlit Community Cloud resource allocation is limited. Only upload media you own or are authorized to process. Use **More options → Upload**. The first run may take time to download `tiny` Whisper weights; processing uses CPU and can be slower than real time on free servers. For longer files, use your local application and paste its transcript online.

### Authorized video/audio media downloads

This is **disabled by default** and not recommended on shared hosting. Where the content owner expressly authorizes downloading and the platform permits it, an administrator may enable it with a server-side secret/environment variable `ENABLE_YOUTUBE_MEDIA_DOWNLOAD=true`. Users must confirm they are authorized. Downloads are capped at 50MB and videos at 30 minutes. No DRM or access-control bypasses are provided. Many hosted IP addresses cannot access media, and this feature may fail. Video/audio download is never necessary for the main transcript workflow.

### Troubleshooting

- **Captions unavailable**: YouTube sometimes blocks datacenter IPs or access to certain videos; try another public video or paste an existing transcript. Do not attempt to bypass restrictions.
- **AI key unavailable**: free extractive summaries still work. Check Streamlit app secrets and model support before using Gemini.
- **App sleeps / slow**: expected on a free tier; refresh. Large Whisper jobs may exceed hosting resources.
- **PDF letters missing**: DejaVu font may not exist on every server; TXT/Markdown are Unicode-safe.
- **Cannot deploy to Hugging Face for free**: by late 2026, new Gradio compute Spaces require subscription or eligible ZeroGPU access. Streamlit is the recommended deployment for this package.

## File tree

```
app.py                    # Web interface and browser session
studio/youtube.py         # URL validation, oEmbed, public/translated captions
studio/models.py          # Typed data models
studio/summary.py         # Extractive / Gemini summarization, Q&A
studio/audio.py           # Whisper upload transcription
studio/chapters.py        # Suggested timeline, not official chapters
studio/export.py          # PDF, SRT, TXT, MD
studio/media.py           # Optional authorized media download
.streamlit/config.toml    # Cloud app/theme settings
requirements.txt          # Python dependencies
.env.example              # Env variable names (no credentials)
tests/                    # Offline unit and mocked integration tests
```

## Tests

```bash
pip install pytest
python -m pytest -q
```

The offline tests use mocks and synthetic transcripts; live YouTube/Google calls and actual Streamlit Cloud deployment are **not verified** by these tests. The optional `streamlit.testing.v1.AppTest` smoke test verifies UI execution without network calls.

## Technical safety

- User URLs can only resolve to validated YouTube video IDs (no arbitrary fetch endpoint).
- API keys are read from environment or Streamlit secrets, never source code or visible UI text.
- 50MB upload/download limits, 30-minute media limit, 180,000-character transcript ceiling.
- Temporary audio/download files are deleted. No permanent server database.
- Generative model prompts treat video transcript content as data, not operational instructions.
- Free fallback remains usable when external AI providers fail.

## Modifying this project

You may reuse the existing Windows app's logic later by replacing `studio/youtube.py`, `studio/audio.py`, or `studio/summary.py` while keeping the Streamlit interface. The original Windows project was not provided when this package was built, so no code was migrated from it.
