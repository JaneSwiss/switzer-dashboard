# AI Video Editing — Actionable summary

*All sources listed at the bottom*

---

<a name="rough-cuts-silence-filler-removal"></a>
## Making Rough Cuts: Removing Silence, Filler Words, and Mistakes

The foundation of AI video editing is automated rough cutting — the tedious work of trimming dead space, removing "ums" and "uhs," and cutting repeated takes. This alone can save hours per video.

**How the custom skill approach works:**

One creator built a Claude skill that combines two tools:
- **Whisper** analyzes the transcript to identify filler words, repetitions, and mistakes
- **FFmpeg** examines video frames to detect visual pauses and dead space

The skill then decides what to cut based on both audio and visual signals. Importantly, it preserves laughter for comedic timing — so you're not just getting robotic cuts.

> A 7-minute video took 3 minutes to process and was reduced by 1.5 minutes after the rough cut.

**Customizing how aggressive the cuts are:**

You don't have to accept the default cutting style. Give Claude a reference video showing how you manually edit — your typical pacing, how much silence you leave between sentences, whether you keep certain verbal tics for personality. Claude will adapt to match your style.

**The Descript alternative:**

One creator who found Claude Code's Remotion integration too slow switched to Descript's built-in AI agent called Underlord. Their workflow:

1. Run "Edit for Clarity" at moderate intensity (not low or heavy)
2. Shorten word gaps — they changed 4-second gaps to 3 seconds
3. Remove filler words with the "avoid harsh cuts" option enabled
4. Remove retakes automatically
5. Enable Studio Sound for audio enhancement

> A 17-minute raw video was reduced to 14 minutes after Descript AI edits.

The advantage of Descript: its transcript-based view shows exactly what was edited, line by line. With Claude Code, you have to watch the entire output to verify the edits.

**Critical prep work:** Raw footage should be manually edited to remove obvious mistakes and dead space before processing. The AI struggles with interpreting retakes — it doesn't know which take you wanted to keep.

**For Switzertemplates:** If you're creating tutorial content showing how to customize Canva templates or set up a Wix website, this rough-cut automation would eliminate the most time-consuming part of editing — trimming all the pauses while you click around the interface.

---

<a name="overlays-broll-timestamps"></a>
## Adding Images, B-Roll, and Overlays at the Right Timestamps

Once you have a rough cut, the next layer is visual enhancement — placing images, screenshots, and B-roll at specific moments that match what you're saying.

**How transcript-based timestamp mapping works:**

Claude reads your transcript and identifies moments where visual support would help. One creator demonstrated this by:

1. Extracting images from a Google Slides PDF
2. Giving Claude both the images and the transcript
3. Claude mapped 20 photo moments to correct timestamps based on what was being discussed

The key mechanism: Claude isn't watching the video (it can't). It's reading the transcript text and matching concepts to images you've provided.

**The Slack bot asset pipeline:**

One creator built a Slack bot that saves screenshots and assets to a Finder folder that Claude can access during editing. When you're recording and realize you'll need a meme or screenshot later, you send it to Slack — it lands in the folder, and Claude can pull it during the edit session.

> Example: A "confused math lady" meme was saved via the Slack bot. When the creator requested it be placed at 1:50, Claude actually corrected the timestamp to 1:46 after detecting where the subject appeared most confused in the transcript.

**Pulling B-roll automatically:**

For stock footage, one creator connected the Pexels API (free) so Claude Code could pull relevant B-roll based on transcript content. In their example, a 12-minute video was edited down to 8-9 minutes with B-roll automatically inserted.

**For Switzertemplates:** When creating content showcasing template customizations, you could pre-save screenshots of different template states (before/after, color variations, font options) and have Claude place them at the exact moments you mention those features.

---

<a name="sound-effects-zooms"></a>
## Adding Sound Effects and Zooms Based on Content

Beyond visuals, AI can handle audio accents and camera movement that would normally require manual keyframing.

**Sound effect placement:**

Claude reads the transcript to identify emotional beats where sound effects make sense. One creator demonstrated adding Duolingo correct/wrong sounds at moments where they were explaining something that worked versus didn't work.

The mechanism: you tell Claude what sounds you have available (success ding, error buzz, whoosh, etc.) and what contexts they should appear in. Claude scans the transcript for those contexts.

**Zoom effects with cinematic terminology:**

You can request zooms using film terminology that Claude understands:
- **Ken Burns effect** — slow pan and zoom, documentary style
- **Harsh zoom** — quick punch-in for emphasis

Claude will return a list of recommended zoom timestamps based on emotional peaks in the transcript. You can also show Claude a reference video and describe the zoom style you want replicated.

**How to describe effects from reference videos:**

Since Claude can't watch video, you describe what you see: "At 0:23 there's a quick 1.2x zoom that holds for 2 seconds then eases back out over 1 second." Claude can then apply similar effects at moments it identifies as appropriate.

---

<a name="motion-graphics-overlays"></a>
## Creating Motion Graphics and Animated Overlays

This is where AI video editing gets genuinely impressive — generating animated elements that would traditionally require After Effects skills.

**Two main approaches:**

| Method | What it is | Setup difficulty | Power level |
|--------|-----------|------------------|-------------|
| Claude Design | Web app, no code needed | Minimal | Good for simple animations |
| HyperFrames | HTML → Browser → FFmpeg → MP4 pipeline | Requires Claude Code setup | Audio-reactive, 3D effects, complex animations |

**Claude Design workflow:**

1. Go to the Claude web app
2. Prompt for the animation you want (text overlays, motion graphics, charts)
3. Claude generates standalone HTML
4. Export options: screen record the full-screen preview, OR use the "handoff to Claude Code" feature which copies a command to render as MP4

**Critical limitation:** Claude Design cannot read, listen to, or transcribe video content. You must manually provide transcripts with timestamps if you want animations synced to speech.

**HyperFrames workflow (more powerful):**

1. Install Claude Code (works in VS Code or Claude desktop app)
2. Clone the official HeyGen HyperFrames GitHub repo
3. Have Claude analyze the repo to build skills and knowledge
4. Provide your video asset and a JSON file with word-for-word transcription and timestamps
5. Prompt for the animations you want

For transcription, use either:
- Local Python Whisper (uses your RAM, free)
- OpenAI's Whisper API (requires API key, faster)

**What HyperFrames can create:**
- Audio-reactive animations that pulse with speech
- Terminal-style typing animations
- Chromatic radial splits
- Karaoke-style subtitles synced to voice
- 3D UI reveals
- Pre-built catalog elements: macOS notifications, Reddit postcards, app showcase animations, various transitions

> One creator rendered over 60 videos in one day while iterating on different methods.

**The Remotion reality check:**

One creator was blunt: Remotion results were "pretty crappy" and slow, even after watching tutorials. Their workaround: copy animation links from external template sites and have Claude Code rebuild similar animations in Remotion. But they emphasized this approach isn't perfected yet.

**For Switzertemplates:** Animated text overlays showing template features, before/after reveals, or step-by-step callouts would elevate tutorial content significantly. HyperFrames' pre-built macOS notification style could work well for "new client booked!" type demonstrations in your website templates.

---

<a name="long-to-short-form"></a>
## Converting Long-Form Content to Short-Form Clips

One of the highest-ROI applications: automatically turning a long video into multiple vertical clips for Instagram, TikTok, and YouTube Shorts.

**The Clipify skill:**

A creator built and open-sourced a clipping tool (built in one hour using Claude) that has 300 stars on GitHub. It eliminates the need for paid tools like Opus Clip.

Clipify options:
- Caption format customization
- Split screen showing multiple faces
- Zoom-in on active speaker for vertical video output

The mechanism: Claude identifies the most engaging segments from the transcript, determines good start/end points, and handles the reformatting for vertical aspect ratio.

> The creator went viral on Twitter sharing this tool.

**For Switzertemplates:** A single 10-minute tutorial on customizing your branding kit could become 5-8 short clips — each showing one specific feature (changing colors, swapping fonts, adding your logo). This multiplies your content output dramatically without additional recording time.

---

<a name="tella-mcp-integration"></a>
## The Tella MCP: Direct Editor Control from Claude

This represents the most seamless integration currently available — Claude controlling a video editor directly rather than generating files to import.

**How MCP (Model Context Protocol) works:**

Tella built an MCP that allows Claude to perform actions that are immediately reflected in the Tella editor. It's not exporting and importing — Claude is manipulating the timeline directly.

**Available MCP tools:**
- List videos in your Tella account
- Upload clips
- Cut clips at specific points
- Get frames for thumbnail selection
- Remove filler words
- Add B-roll layouts

**The thumbnail extraction feature:**

The MCP can extract frames from videos for YouTube thumbnails, selecting based on criteria like:
- Eyes pointing forward (not looking away)
- Animated expressions (not flat/bored looking)

You describe what makes a good thumbnail for your content, and Claude pulls candidate frames.

**Connected tool integrations:**

The workflow can connect to:
- **Eleven Labs** for AI-generated narration
- **Seedance** for AI-generated B-roll footage
- **Remotion** for motion graphics that upload directly as B-roll to Tella

This creates a pipeline where Claude orchestrates multiple AI tools, each handling what it does best.

---

<a name="costs-limitations-reality"></a>
## Costs, Token Limits, and Realistic Expectations

Before diving in, understand the resource requirements and honest limitations.

**Cost breakdown for Claude Code approach:**

| Tool | Cost |
|------|------|
| Claude AI (via Open Writer API) | ~4¢ for videos under 10 min, ~20¢ for 60-min videos |
| FFmpeg | Free |
| Whisper | Free (local) or pay-per-use (API) |
| Pexels API | Free |
| Remotion | Free |

**Token and usage limits:**

> One video editing session used approximately 263k tokens out of 1 million context, prompting a session clear and handoff message to reduce token usage.

> The full project (one video from start to finish with revisions) consumed approximately 10% of a 5-hour limit on the $200/month max Claude plan.

Multiple revision rounds add up. If you're iterating heavily on motion graphics, expect to hit limits faster.

**The taste problem — honest assessment:**

One creator attempted a ClickUp product demo that required 5 prompt iterations and still produced output that lost energy and taste compared to human editing.

> "People with existing editing skills and creative intuition will be able to use these tools to 10x productivity, while those without taste may get mediocre outputs."

The AI executes what you describe. If you can't articulate what good editing looks like — through reference videos, specific terminology, or detailed feedback — the output will be generic.

**Historical context on time savings:**

> In 2018, using Adobe Premiere Pro and After Effects, a 5-minute video took 6-8 hours to edit manually.

> A 23-second animated clip that would take approximately 2 hours to edit manually (or 30-45 minutes for expert editors) can be created using Claude.

The savings are real, but they're most dramatic for people who already know what they want and can communicate it clearly.

**For Switzertemplates:** At 4-20 cents per video for the Claude Code approach, the cost barrier is negligible compared to your product prices ($15-$82). The real question is whether the time investment in setup and learning pays off for your content volume. If you're producing weekly tutorials, it almost certainly does.

---

*Sources: [I Use Claude to Edit Videos: Here's My Exact Process](https://www.youtube.com/watch?v=1w_H6uA3N-g), [Claude Just Destroyed Every Video Editing Tool](https://www.youtube.com/watch?v=ZNbgOhxhzXg), [How I Fully Automated My Video Editing with Claude Code (No Hype)](https://www.youtube.com/watch?v=OjRiJRItPrY)*