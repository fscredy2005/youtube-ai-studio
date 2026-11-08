"""YouTube AI Studio — free-first Streamlit web app."""
from __future__ import annotations
import os
import re
from copy import deepcopy
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import streamlit as st

from studio.models import Segment, VideoResult
from studio.youtube import analyze_youtube, retrieve_translation, CaptionsUnavailable, VideoInputError
from studio.audio import transcribe_upload, AudioError
from studio.summary import (STYLES, timestamp, youtube_at, generate_summary,
                            extractive, find_related, ask_gemini)
from studio.chapters import suggested_chapters
from studio.integrity import check_integrity, parse_video_duration
from studio.credits import fetch_supadata_balance, parse_reset_date, next_expected_monthly_reset
from studio.export import transcript_txt, transcript_srt, report_markdown, report_pdf

st.set_page_config(page_title="YouTube AI Studio", page_icon="🎬", layout="wide",
                   initial_sidebar_state="expanded")

st.markdown("""
<style>
.block-container {max-width: 1280px; padding-top: 1.4rem; padding-bottom: 3rem;}
.hero {border: 1px solid #dbe9fa; border-radius: 20px; padding: 24px 30px;
       background: linear-gradient(115deg, #f4f9ff 0%, #e8f5ff 58%, #e9f9f4 100%);
       margin-bottom: 24px;}
.eyebrow {font-size: .77rem; color: #1871bb; font-weight: 700; letter-spacing: .11em;}
.hero h1 {font-size: 2.45rem; letter-spacing: -.045em; margin: 7px 0 5px; color: #142b49;}
.hero p {margin: 0; color: #42617a; font-size: 1.0rem;}
.micro {font-size: .77rem; color: #60758a;}
.round-label {display:inline-block; padding: .2rem .65rem; border-radius: 15px;
              background:#e4f3ff; color:#1662a4; font-size:.82rem; font-weight:600;}
[data-testid="stMetricValue"] {font-size: 1.25rem;}
div[data-testid="stTabs"] button {font-weight: 600;}
@media (max-width: 780px) {.hero h1 {font-size: 1.8rem;} .hero {padding: 17px;}}
</style>
""", unsafe_allow_html=True)


def read_setting(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value:
        return value
    try:
        return str(st.secrets.get(name, default) or default)
    except Exception:
        # Streamlit raises a framework-specific exception when secrets.toml is absent.
        return default


@st.cache_data(ttl=90, show_spinner=False)
def cached_supadata_balance(api_key: str):
    """Short-lived cache avoids fetching account status on every Streamlit rerun."""
    return fetch_supadata_balance(api_key)


def language_label(code: str) -> str:
    return {"en": "English", "fr": "French", "es": "Spanish", "de": "German",
            "it": "Italian", "pt": "Portuguese"}.get(code.split("-")[0].lower(), code)


def set_result(result: VideoResult, style: str, target_lang: str) -> None:
    if not result.segments:
        raise ValueError("No transcript text could be extracted.")
    if len(result.segments) > 15000 or len(result.text) > 180000:
        raise ValueError("This transcript exceeds the 180,000-character safety limit. Use a shorter source.")
    key = read_setting("GEMINI_API_KEY")
    model = read_setting("GEMINI_MODEL", "gemini-2.5-flash-lite")
    result.summary, result.summary_engine, result.summary_note = generate_summary(
        result.segments, style, result.video_id, target_lang, key, model)
    result.summary_kind = style
    st.session_state.current = result
    st.session_state.takeaways = extractive(result.segments, "Key takeaways", result.video_id)
    st.session_state.qa_answer = ""
    st.session_state.pop("media_download", None)
    st.session_state.pop("translation", None)
    history = st.session_state.setdefault("history", {})
    name = result.video_id or f"upload:{result.title}"
    history[name] = {"result": deepcopy(result), "takeaways": st.session_state.takeaways}
    while len(history) > 6:
        history.pop(next(iter(history)))


def make_pasted_result(text: str, title: str, video_url: str = "") -> VideoResult:
    text = (text or "").strip()
    if len(text) < 40 or len(text) > 180000:
        raise ValueError("Paste at least 40 characters and at most 180,000 characters.")
    # Plain text has no real time reference. Preserve user-supplied [mm:ss] when available.
    segments = []
    running = 0.0
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        match = re.match(r"^\[?(?:(\d+):)?(\d{1,2}):(\d{2})\]?\s*[-–:]?\s*(.+)$", line)
        if match:
            hours, minutes, seconds, content = match.groups()
            running = int(hours or 0) * 3600 + int(minutes) * 60 + int(seconds)
            segments.append(Segment(float(running), 5, content))
        else:
            # Group plain transcript into reasonable passages; these are NOT real timestamps.
            for i in range(0, len(line), 260):
                segments.append(Segment(0, 0, line[i:i+260]))
    from studio.youtube import parse_video_id
    # Without supplied timestamps, a YouTube URL does not establish reliable time links.
    vid = parse_video_id(video_url) if video_url.strip() and any(s.start > 0 for s in segments) else ""
    return VideoResult(video_id=vid, title=(title.strip() or "Pasted transcript")[:140],
                       channel="User-provided transcript", source="Pasted text",
                       language="unknown", segments=segments)


def go_to_result(item: dict) -> None:
    st.session_state.current = deepcopy(item["result"])
    st.session_state.takeaways = item["takeaways"]
    st.session_state.qa_answer = ""
    st.session_state.pop("media_download", None)
    st.session_state.pop("translation", None)


st.markdown('''<div class="hero"><div class="eyebrow">YOUR VIDEO KNOWLEDGE WORKSPACE</div>
<h1>▶ YouTube AI Studio</h1><p>From video to insight — transcripts, concise summaries and useful exports, all in your browser.</p></div>''',
            unsafe_allow_html=True)

with st.sidebar:
    st.markdown("### ⚙️ Preferences")
    target_language = st.selectbox("Summary language", ["English", "Français"], index=0,
                                   help="Free mode cannot translate; Gemini can generate the selected language.")
    chosen_style = st.selectbox("Summary format", STYLES, index=0)
    gemini_key = read_setting("GEMINI_API_KEY")
    if gemini_key:
        st.success("✨ Generative AI configured")
    else:
        st.info("🆓 Free extractive mode · no API key needed")
    st.caption("Add GEMINI_API_KEY to your private Streamlit secrets for generative summaries and bilingual output.")
    if read_setting("SUPADATA_API_KEY"):
        st.success("Cloud captions fallback ready")
    else:
        st.caption("Optional SUPADATA_API_KEY enables a hosted caption fallback when YouTube blocks the server.")
    st.divider()
    st.markdown("### 🗂 Recent analyses")
    history = st.session_state.get("history", {})
    if not history:
        st.caption("Your last six videos will appear here for this browser session.")
    else:
        for idx, (k, item) in enumerate(reversed(list(history.items()))):
            if st.button("↗ " + item["result"].title[:40], use_container_width=True, key=f"recent_{idx}"):
                go_to_result(item)
                st.rerun()
    if st.button("Clear session", use_container_width=True, help="Forget analyses currently held in this browser session"):
        st.session_state.pop("history", None)
        st.session_state.pop("current", None)
        st.session_state.pop("takeaways", None)
        st.session_state.pop("qa_answer", None)
        st.session_state.pop("translation", None)
        st.rerun()
    st.divider()
    st.caption("🔒 Sessions aren't saved to a database. Processing happens on the hosting server. Avoid submitting confidential material to shared deployments.")

st.markdown("#### 01  ·  Analyze a YouTube video")
left, right = st.columns([4.5, 1.2], vertical_alignment="bottom")
with left:
    link = st.text_input("YouTube link", placeholder="https://www.youtube.com/watch?v=...",
                         label_visibility="collapsed", help="Standard links, Shorts, live replay URLs and youtu.be are supported.")
with right:
    analyze_clicked = st.button("✨ Analyze video", type="primary", use_container_width=True)

with st.expander("More options · caption language and upload alternatives", expanded=False):
    pref = st.selectbox("Preferred caption language", ["Auto", "en", "fr", "es", "de", "it", "pt"],
                        help="If the selected language isn't available, the app falls back to another caption language.")
    st.markdown("**No accessible YouTube captions?** Upload media you're allowed to process, or paste a transcript.")
    c_upload, c_paste = st.columns(2)
    with c_upload:
        media = st.file_uploader("Authorized audio / video file (max 50 MB, 30 min)",
                                 type=["mp3", "m4a", "wav", "ogg", "flac", "mp4", "webm"])
        upload_clicked = st.button("🎙 Transcribe uploaded media", use_container_width=True, disabled=media is None)
    with c_paste:
        title_paste = st.text_input("Transcript title", value="My transcript")
        raw_paste = st.text_area("Paste transcript", height=100,
                                 placeholder="[00:15] Welcome ...\n[00:32] Today we will ...")
        paste_clicked = st.button("📄 Analyze pasted transcript", use_container_width=True,
                                  disabled=len(raw_paste.strip()) < 40)

if analyze_clicked:
    if not link.strip():
        st.warning("Paste a YouTube URL in the field above.")
    else:
        try:
            with st.status("Analyzing video…", expanded=True) as status:
                st.write("Checking the link and fetching public captions…")
                result = analyze_youtube(link, pref, read_setting("SUPADATA_API_KEY"))
                st.write(f"Loaded {len(result.segments)} transcript passages. Creating your summary…")
                set_result(result, chosen_style, target_language)
                status.update(label="Analysis complete", state="complete")
        except (VideoInputError, CaptionsUnavailable, ValueError) as exc:
            st.error(str(exc))
        except Exception:
            st.error("The video could not be analyzed. Check the URL or try an uploaded transcript.")
        finally:
            # A successful analysis can spend Supadata transcript and/or metadata credits.
            if read_setting("SUPADATA_API_KEY"):
                cached_supadata_balance.clear()

if upload_clicked:
    try:
        with st.status("Transcribing uploaded media…", expanded=True) as status:
            st.write("Transcribing on CPU. The first run may download a small open-source speech model.")
            result = transcribe_upload(media)
            set_result(result, chosen_style, target_language)
            status.update(label="Transcription and summary complete", state="complete")
    except (AudioError, ValueError) as exc:
        st.error(str(exc))
    except Exception:
        st.error("Transcription failed. Try a shorter supported file or pasted transcript.")

if paste_clicked:
    try:
        with st.spinner("Summarizing pasted transcript…"):
            result = make_pasted_result(raw_paste, title_paste, link)
            set_result(result, chosen_style, target_language)
    except ValueError as exc:
        st.error(str(exc))

# Read-only provider quota display; independent of Gemini token usage.
supadata_key = read_setting("SUPADATA_API_KEY")
with st.container(border=True):
    heading, refresh = st.columns([4, 1], vertical_alignment="center")
    with heading:
        st.markdown("**☁️ Supadata extraction credits**")
    with refresh:
        if st.button("↻ Refresh", key="refresh_supadata_credits",
                     disabled=not bool(supadata_key), use_container_width=True):
            cached_supadata_balance.clear()
    if not supadata_key:
        st.caption("Add SUPADATA_API_KEY to your private Streamlit secrets to show your balance.")
    else:
        balance = cached_supadata_balance(supadata_key)
        if balance is None:
            st.caption("Credit balance unavailable right now. Try Refresh or check the Supadata dashboard.")
        else:
            credit_metric, credit_detail = st.columns([1.5, 3.5], vertical_alignment="center")
            with credit_metric:
                st.metric("Credits remaining", f"{balance.remaining:,} / {balance.max_credits:,}")
            with credit_detail:
                st.caption(f"Plan: {balance.plan} · {balance.used_credits:,} credits used")
                st.progress(min(1.0, balance.remaining / balance.max_credits)
                            if balance.max_credits else 0.0)
        st.caption("Supadata credits are not Gemini tokens. Native caption fallback and "
                   "video metadata can use credits; pasted transcripts use none.")
        with st.expander("📅 Monthly credit reset date", expanded=False):
            date_text = st.text_input(
                "Next reset date shown in Supadata (YYYY-MM-DD)",
                value=read_setting("SUPADATA_RESET_DATE"),
                key="supadata_reset_date_input",
                placeholder="YYYY-MM-DD",
                help="Look in your Supadata account dashboard. The /me API does not return a reset date.",
            )
            st.caption("This input lasts for your browser session. To keep the date after "
                       "reopening the app, add SUPADATA_RESET_DATE = \"YYYY-MM-DD\" "
                       "to private Streamlit secrets.")
        try:
            supplied_reset = parse_reset_date(date_text)
        except ValueError as exc:
            st.warning(str(exc))
            supplied_reset = None
        if supplied_reset:
            today_paris = datetime.now(ZoneInfo("Europe/Paris")).date()
            expected = next_expected_monthly_reset(supplied_reset, today_paris)
            days = (expected - today_paris).days
            count_label = "today" if days == 0 else f"in {days} day{'s' if days != 1 else ''}"
            st.markdown(f"**Next expected credit reset: {expected:%d %b %Y} ({count_label})**")
            st.caption("Estimate based on your supplied date and a calendar-month cycle, "
                       "not an API-confirmed renewal. Verify it in the Supadata dashboard.")
        else:
            st.caption("Next reset date: unknown · Supadata does not provide it via the account API.")

result: VideoResult | None = st.session_state.get("current")
if not result:
    st.markdown("#### How it works")
    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("**① Paste a link**")
        st.caption("Standard YouTube links and Shorts. No sign-in needed for supported public captions.")
    with c2:
        st.markdown("**② Analyze**")
        st.caption("Get the transcript and a free source-grounded overview; use optional Gemini for generative summaries.")
    with c3:
        st.markdown("**③ Explore & export**")
        st.caption("Navigate timestamps, search captions, ask questions and download your report.")
    st.info("Free mode selects transcript excerpts rather than writing a generative summary. Cloud caption access can be blocked; optionally configure SUPADATA_API_KEY in Streamlit secrets or paste a transcript under More options.")
    st.stop()

st.divider()
st.markdown("#### 02  ·  Your results")
info, details = st.columns([1.2, 3.8], vertical_alignment="center")
with info:
    if result.thumbnail:
        st.image(result.thumbnail, use_container_width=True)
    else:
        st.markdown("🎙️ **Uploaded transcript**")
with details:
    st.markdown(f"### {result.title}")
    st.caption(f"{result.channel}  ·  {language_label(result.language)}  ·  {result.source}")
    m1, m2, m3 = st.columns(3)
    m1.metric("Caption passages", f"{len(result.segments):,}")
    m2.metric("Words", f"{len(result.text.split()):,}")
    m3.metric("Last caption time", timestamp(max(s.start + max(0, s.duration) for s in result.segments)))
    if result.url:
        st.link_button("▶ Open video on YouTube", result.url)
    st.markdown(f'<span class="round-label">{result.summary_engine}</span>', unsafe_allow_html=True)
    if result.summary_note:
        st.caption(result.summary_note)

st.markdown("##### 🔎 Transcript integrity check")
st.caption("Automatic timing checks identify suspicious gaps; they cannot prove that every spoken word is present.")
real_duration = result.duration if result.video_id and result.duration_source else None
duration_key = "reference_video_duration_" + (result.video_id or "uploaded")
with st.expander("Optional: correct or enter the video's length"):
    video_length = st.text_input(
        "Video duration shown on YouTube",
        placeholder="e.g. 26:49",
        help="Normally detected via Supadata metadata (1 additional credit per analysis). "
             "Enter YouTube's displayed length if metadata was unavailable or inaccurate.",
        key=duration_key,
    )
try:
    manual_duration = parse_video_duration(video_length)
    audit = check_integrity(result.segments, manual_duration if manual_duration is not None else real_duration)
except ValueError as exc:
    st.warning(str(exc))
    manual_duration = None
    audit = check_integrity(result.segments, real_duration)

if manual_duration is not None:
    st.caption("Video duration source: **YouTube length entered manually** (overrides metadata).")
elif real_duration is not None:
    st.caption(f"Video duration source: **{result.duration_source}** (independent of caption timestamps).")
else:
    st.caption("Duration unavailable from Supadata and direct YouTube metadata. Expand the field above to enter the length shown on YouTube. Caption end times cannot be used as an independent duration.")

if audit.status == "Review recommended":
    st.warning("**Review recommended.** " + audit.summary)
elif audit.status == "No obvious timing issues":
    st.success("**No obvious timing issues.** " + audit.summary)
else:
    st.info("**" + audit.status + ".** " + audit.summary)

largest_gap = max((gap.seconds for gap in audit.gaps), default=0)
# Ignore tiny edge offsets (e.g. the first caption at 0.2s) in the visual warnings.
# These are common timestamp rounding artifacts, not intervals worth reviewing.
MIN_VISIBLE_EDGE_GAP = 3.0
visible_start_gap = (audit.reference_duration is not None and audit.first_start is not None
                     and audit.first_start >= MIN_VISIBLE_EDGE_GAP)
visible_end_gap = (audit.reference_duration is not None and audit.last_end is not None
                   and audit.reference_duration - audit.last_end >= MIN_VISIBLE_EDGE_GAP)
mc1, mc2, mc3, mc4 = st.columns(4)
mc1.metric("Actual video length", timestamp(audit.reference_duration) if audit.reference_duration else "Unknown")
mc2.metric("Last caption endpoint", timestamp(audit.last_end) if audit.last_end is not None else "Unknown")
mc3.metric("Long gaps (≥15s)", len(audit.gaps))
mc4.metric("Longest internal gap", f"{largest_gap:.0f} s" if largest_gap else "None")

# Colored timeline shows only timing intervals, NOT semantic or word-level coverage.
bar_duration = audit.reference_duration or audit.last_end
if bar_duration and bar_duration > 0:
    intervals = [(gap.start, gap.end, "internal") for gap in audit.gaps]
    if visible_start_gap:
        intervals.append((0.0, audit.first_start, "start"))
    if visible_end_gap:
        intervals.append((audit.last_end, audit.reference_duration, "end"))
    colored = []
    for interval_start, interval_end, kind in intervals:
        left_pct = max(0.0, min(100.0, interval_start / bar_duration * 100))
        width_pct = max(0.0, min(100.0 - left_pct, (interval_end - interval_start) / bar_duration * 100))
        if width_pct:
            color = "#ef4444" if kind in {"start", "end"} else "#f59e0b"
            colored.append(f'<span style="position:absolute;left:{left_pct:.5f}%;width:{width_pct:.5f}%;'
                           f'height:100%;background:{color};"></span>')
    st.markdown('<div role="img" aria-label="Green caption timeline; amber indicates internal gaps; '
                'red indicates unavailable start or end sections" '
                'style="position:relative;width:100%;height:18px;border-radius:7px;'
                'overflow:hidden;background:#10b981;">' + ''.join(colored) + '</div>',
                unsafe_allow_html=True)
    st.caption("🟩 Caption intervals · 🟧 Gaps ≥15 seconds · 🟥 Uncovered beginning/end. "
               "Silence or music can also produce gaps; this is not a word-accuracy score.")

with st.expander("Inspect suspected gaps and technical details"):
    entries = []
    if visible_start_gap:
        entries.append((0.0, audit.first_start, "Beginning without captions"))
    entries.extend((gap.start, gap.end, "Internal gap") for gap in audit.gaps)
    if visible_end_gap:
        entries.append((audit.last_end, audit.reference_duration, "End without captions"))
    if entries:
        st.markdown("**Intervals worth reviewing on YouTube**")
        for start_sec, stop_sec, label in sorted(entries, key=lambda row: row[1] - row[0], reverse=True)[:12]:
            interval_text = (f"{label}: {timestamp(start_sec)}–{timestamp(stop_sec)} "
                             f"({stop_sec - start_sec:.0f} s)")
            if result.video_id:
                st.markdown(f"- [{interval_text}]({youtube_at(result.video_id, start_sec)})")
            else:
                st.markdown("- " + interval_text)
        if len(entries) > 12:
            st.caption(f"Showing 12 of {len(entries)} intervals.")
    else:
        st.caption("No suspicious intervals at the configured 15-second threshold.")
    st.caption(f"{audit.out_of_order} out-of-order timestamps · {audit.invalid_timing} invalid intervals · "
               f"{audit.overlaps} substantial overlapping intervals · {audit.zero_duration} zero-duration captions")
    for note in audit.notes:
        st.caption("• " + note)

(t_overview, t_summary, t_transcript, t_chapters, t_export, t_ask, t_compare) = st.tabs(
    ["📌 Overview", "✨ AI Summary", "📝 Transcript", "🕒 Timeline", "⬇️ Export", "💬 Ask", "⚖️ Compare"])

with t_overview:
    st.markdown("##### At a glance")
    st.markdown(result.summary)
    st.markdown("##### Key takeaways (extractive)")
    st.markdown(st.session_state.get("takeaways", ""))
    st.caption("The free key-takeaway view quotes representative transcript passages; it does not infer conclusions.")

with t_summary:
    st.markdown("##### Select your format")
    summary_style = st.selectbox("Summary style", STYLES,
                                 index=STYLES.index(result.summary_kind) if result.summary_kind in STYLES else 0,
                                 key="result_summary_style")
    if st.button("↻ Generate selected format", key="regen_summary"):
        try:
            with st.spinner("Creating summary…"):
                result.summary, result.summary_engine, result.summary_note = generate_summary(
                    result.segments, summary_style, result.video_id, target_language,
                    read_setting("GEMINI_API_KEY"), read_setting("GEMINI_MODEL", "gemini-2.5-flash-lite"))
                result.summary_kind = summary_style
                st.session_state.current = result
                key = result.video_id or f"upload:{result.title}"
                if key in st.session_state.get("history", {}):
                    st.session_state.history[key]["result"] = deepcopy(result)
        except Exception:
            st.error("Could not regenerate the summary.")
    st.markdown(result.summary)
    with st.expander("Copy summary as Markdown"):
        st.code(result.summary, language="markdown")

with t_transcript:
    search = st.text_input("Search within transcript", placeholder="Search a keyword or concept…")
    matches = [s for s in result.segments if search.lower() in s.text.lower()] if search else result.segments
    st.caption(f"{len(matches):,} matches · first 800 displayed")
    records = [{"Time": timestamp(s.start), "Transcript": s.text, "Jump to video": youtube_at(result.video_id, s.start)}
               for s in matches[:800]]
    if records:
        st.dataframe(records, use_container_width=True, hide_index=True,
                     column_config={"Jump to video": st.column_config.LinkColumn("Jump to video")})
    else:
        st.info("No transcript passages matched.")
    if result.video_id == "":
        st.caption("Uploaded or pasted source may have no verified YouTube timestamps.")
    elif result.source == "YouTube captions":
        st.divider()
        st.markdown("##### Optional translated captions")
        st.caption("YouTube must make a translated caption track available; this is independent of AI summaries.")
        translate_to = st.selectbox("Translation language", ["en", "fr", "es", "de", "it", "pt"],
                                    format_func=language_label, key="translate_to")
        if st.button("Fetch translated captions", key="translate_captions"):
            try:
                with st.spinner("Fetching translation from YouTube…"):
                    translated = retrieve_translation(result.video_id, result.language, translate_to)
                    st.session_state.translation = (result.video_id, translate_to, translated)
            except CaptionsUnavailable as exc:
                st.warning(str(exc))
        current_translation = st.session_state.get("translation")
        if current_translation and current_translation[:2] == (result.video_id, translate_to):
            _, target, translated = current_translation
            translated_result = VideoResult(video_id=result.video_id, title=result.title,
                                           language=target, segments=translated,
                                           source="YouTube translated captions")
            st.caption(f"Translated passages: {len(translated):,} · language: {language_label(target)}")
            col_tr1, col_tr2 = st.columns(2)
            with col_tr1:
                st.download_button("Translated TXT", data=transcript_txt(translated_result),
                                   file_name=f"{result.video_id}-{target}-translated.txt", mime="text/plain")
            with col_tr2:
                st.download_button("Translated SRT", data=transcript_srt(translated_result),
                                   file_name=f"{result.video_id}-{target}-translated.srt", mime="application/x-subrip")
            with st.expander("Preview translated transcript"):
                st.text("\n".join(f"[{timestamp(s.start)}] {s.text}" for s in translated[:120]))

with t_chapters:
    st.markdown("##### Suggested timeline")
    st.caption("These are automatic navigation windows based on the transcript, **not official YouTube chapters**.")
    chapters = suggested_chapters(result.segments, result.video_id)
    for chapter in chapters:
        col_clock, col_info = st.columns([1.1, 4.9], vertical_alignment="center")
        with col_clock:
            if chapter["url"]:
                st.link_button("▶ " + chapter["time"], chapter["url"], use_container_width=True)
            else:
                st.markdown("`" + chapter["time"] + "`")
        with col_info:
            st.markdown("**" + chapter["title"] + "**")
            st.caption(chapter["text"][:210] + ("…" if len(chapter["text"]) > 210 else ""))
        st.divider()

with t_export:
    st.markdown("##### Download your work")
    slug = re.sub(r"[^A-Za-z0-9_-]+", "-", result.title).strip("-")[:45] or "video"
    downloads = [
        ("📝 Transcript (TXT)", transcript_txt(result), "text/plain", f"{slug}-transcript.txt"),
        ("⏱ Captions (SRT)", transcript_srt(result), "application/x-subrip", f"{slug}-subtitles.srt"),
        ("📃 Report (Markdown)", report_markdown(result, st.session_state.get("takeaways", "")), "text/markdown", f"{slug}-report.md"),
    ]
    for label, bytes_data, mime, filename in downloads:
        st.download_button(label, data=bytes_data, file_name=filename, mime=mime,
                           use_container_width=True, key="download-" + filename)
    try:
        pdf = report_pdf(result, st.session_state.get("takeaways", ""))
        st.download_button("📕 Report (PDF)", data=pdf, file_name=f"{slug}-report.pdf",
                           mime="application/pdf", use_container_width=True)
    except Exception:
        st.warning("PDF export is not available for this transcript; TXT and Markdown exports still work.")
    st.divider()
    st.markdown("##### Authorized media download (optional)")
    if read_setting("ENABLE_YOUTUBE_MEDIA_DOWNLOAD", "false").lower() != "true":
        st.info("Media file downloads are disabled on this deployment. TXT, SRT, Markdown, and PDF exports remain available. To enable authorized downloads, see the README.")
    elif not result.video_id:
        st.caption("Only YouTube video IDs support optional media download.")
    else:
        user_confirmed = st.checkbox("I own this video or have permission to download the media.")
        audio_only = st.checkbox("Audio only (original format)")
        if st.button("Prepare authorized media file", disabled=not user_confirmed):
            try:
                from studio.media import download_authorized
                with st.spinner("Downloading from YouTube where permitted…"):
                    filename, file_data = download_authorized(result.url, audio_only, user_confirmed)
                    st.session_state.media_download = (filename, file_data)
            except Exception as exc:
                st.error(str(exc))
        if st.session_state.get("media_download"):
            name, data = st.session_state.media_download
            st.download_button("Download prepared media", data=data, file_name=name)

with t_ask:
    st.markdown("##### Ask a question about this video")
    user_question = st.text_input("Your question", placeholder="What tools or methods does the speaker explain?")
    if st.button("Find an answer", disabled=not bool(user_question.strip())):
        try:
            if gemini_key:
                with st.spinner("Finding supporting video passages…"):
                    answer = ask_gemini(result.segments, user_question, gemini_key,
                                        read_setting("GEMINI_MODEL", "gemini-2.5-flash-lite"), target_language)
            else:
                answer = find_related(result.segments, user_question, result.video_id)
            st.session_state.qa_answer = answer
        except Exception:
            st.session_state.qa_answer = find_related(result.segments, user_question, result.video_id)
            st.warning("Generative Q&A unavailable; showing matching transcript passages instead.")
    if st.session_state.get("qa_answer"):
        st.markdown(st.session_state.qa_answer)
    st.caption("Without Gemini, this is a transcript passage search, not a generative question-answering model.")

with t_compare:
    st.markdown("##### Compare two previously analyzed videos")
    entries = st.session_state.get("history", {})
    if len(entries) < 2:
        st.info("Analyze at least two videos in the same session to compare their summaries.")
    else:
        keys = list(entries)
        a, b = st.columns(2)
        with a:
            left_id = st.selectbox("Video A", keys, index=max(0, len(keys)-2),
                                   format_func=lambda k: entries[k]["result"].title)
            st.markdown(entries[left_id]["result"].summary)
        with b:
            right_id = st.selectbox("Video B", keys, index=len(keys)-1,
                                    format_func=lambda k: entries[k]["result"].title)
            st.markdown(entries[right_id]["result"].summary)
        st.caption("Side-by-side comparison of summaries already generated in this browser session.")

st.divider()
st.caption("YouTube AI Studio · Free-first web app · YouTube caption access depends on the video and cloud provider · Please respect creators' rights and applicable platform terms.")
