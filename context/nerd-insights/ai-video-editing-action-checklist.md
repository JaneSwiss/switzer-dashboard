# AI Video Editing — Step-by-step for JaneFitmind

*You edit in CapCut and don't touch a terminal. None of the three sources cover CapCut directly — they cover Descript, Remotion, and custom Claude Code setups built by developers. This guide translates what they actually do into two tracks that work for you: things you can do yourself in a normal Claude chat, and things you hand to me (your Claude Code agent) directly — no terminal, no new tools to learn.*

---

## Track A: Things you do yourself, in 5 minutes, no new tools

**Turn one vlog into a list of reel-worthy moments**

1. Record your vlog like normal.
2. Get the transcript — YouTube auto-generates one (Studio → Subtitles → download), or CapCut can export captions from your clip.
3. Open Claude.ai (the regular chat, not this project) and paste the transcript in. Ask: *"Here's the transcript of my vlog. Find the 5-8 most engaging 30-60 second moments that would work as standalone Instagram Reels. Give me the timestamp and a one-line reason for each."*
4. Take that list into CapCut and cut those exact clips yourself. You skip the "watch the whole thing twice trying to find the good bits" step entirely.

**Get sound effect, zoom, and caption timing suggestions before you edit**

1. Same transcript, same Claude.ai chat.
2. Ask: *"Where in this transcript would a zoom-in for emphasis work well? Where would a sound effect (success ding, error buzz, whoosh) land naturally? Give me timestamps."*
3. Apply those manually in CapCut. This is exactly what the sources describe Claude doing automatically inside Claude Code — the difference is you're doing the placement yourself in CapCut instead of a custom pipeline doing it for you. Same thinking, no setup.

---

## Track B: Things you hand to me — no terminal, just send me the file

This is the part of the sources that actually requires Claude Code (terminal-based) — Whisper for transcription, FFmpeg for cutting. You don't run any of that. I do, when you ask.

**Rough-cut a vlog automatically**

1. Next time you have a raw, unedited vlog, tell me in chat: *"Here's a raw video, can you rough-cut it?"* and share the file.
2. I'll use the same approach the sources describe — Whisper finds the filler words and dead air, FFmpeg trims it — and hand you back a tighter cut with the "ums," pauses, and obvious flubs removed.
3. You take that trimmed video into CapCut and do what you already do best: music, text style, brand polish, your usual pacing.

**Turn one long vlog into multiple short clips automatically**

1. Tell me: *"Turn this vlog into 5-8 vertical clips for Reels."*
2. I'll find the most engaging segments from the transcript, pick good start/end points, and export them already cropped to vertical. This is the same "Clipify" approach from the sources — it replaces what a paid tool like Opus Clip does.
3. You finish each clip in CapCut with your usual branding.

**One thing to flag honestly:** the sources warn that AI editing output is only as good as the taste behind the request. If you want a specific pacing or style, the best results come from telling me what you want explicitly — or pointing me to one of your own past videos that nailed the pacing you like — rather than a vague brief.

---

## What to skip for now

The sources also cover HyperFrames (motion graphics via a HeyGen GitHub repo), Tella's MCP (direct editor control), and Remotion. All three require setting up a new tool or account and were built by developers for their own pipelines. They're not a fit for a CapCut-first workflow — skip these unless you decide later you want to move off CapCut entirely.

---

## Cost reality check

- Track A (Claude.ai chat for planning) — free, just your normal Claude.ai usage.
- Track B (me running rough cuts or clip generation for you) — sources cite roughly 4¢ for videos under 10 minutes, up to ~20¢ for an hour-long video. Negligible.
- The time saved is the real win, not the cost. One source's 7-minute video took 3 minutes to rough-cut automatically instead of the usual manual scrub-through.

---

*Full detail and source examples: [ai-video-editing.md](ai-video-editing.md)*
