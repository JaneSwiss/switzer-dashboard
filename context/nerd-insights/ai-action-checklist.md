# AI tools — What to try next (specifically for Switzertemplates)

*You're already using Claude for tasks throughout this system. This list skips the basics and focuses only on techniques from the source material that are likely to add real leverage — things you're probably not doing yet.*

---

## Set up Claude Projects with a custom system prompt for each use case

Right now you're probably starting fresh chats with Claude each time. The difference between inconsistent results and a repeatable system is a **Project with a saved system prompt**. One source described this as the single biggest separator between people who get "meh" outputs and people running actual systems.

- [ ] Go to Claude.ai → Projects → create one called "Switzertemplates content." Add a system prompt that describes your brand voice, target customer, product prices, and tone rules. Every chat inside that project inherits those instructions automatically.
- [ ] Do the same for email: a "Switzertemplates email" project with your Flodesk tone, list context (21K warm past buyers), and upsell logic from CLAUDE.md. You should never have to re-explain your business in an email brief again.
- [ ] Optional third project: "Switzertemplates Pinterest" with board names, keywords, and pin spec baked in as context.

---

## Build a one-input → multiple-outputs content pipeline

One source built "Draft Loop" — paste one video transcript, get 15 tweets, 3 LinkedIn posts, 4 carousels, and a Substack essay automatically. The same principle applies to any long-form content.

- [ ] Take your next blog post or email. After writing it, paste it into Claude with this brief: "Turn this into: 5 Pinterest pin titles and descriptions, 3 Instagram caption variations, and a short email teaser. Use my brand voice: [paste your voice rules]." One piece of work → four content formats.
- [ ] If this works well, build it into a saved Claude skill: a single prompt file you paste at the start of any repurposing session, so you don't have to rewrite the brief each time.
- [ ] Test whether the Pinterest pin outputs are actually usable, or if they need editing. If they consistently need the same fixes, update the prompt to avoid those mistakes before the next run.

---

## Rewrite your 3-in-1 bundle copy around speed to value

Multiple sources confirmed the same thing: customers don't buy your product, they buy the outcome, and they pick whoever gets them there fastest. Your current product descriptions likely list what's included. The language that converts is different.

- [ ] Look at your $82 bundle listing on Etsy and your website. Count how many sentences describe *what's inside* vs. *what the customer's situation looks like after buying*. If it's more than 50% "what's inside," the copy is doing the wrong job.
- [ ] Test one rewrite with the frame: "You could spend the next three weeks piecing together a logo, a website, and 1,000 social media templates from five different shops. Or you could have all of it — matched, ready to launch, and looking like you hired a designer — by the weekend." That's the speed-to-value argument.
- [ ] Apply the same logic to Pinterest pin titles. Instead of "3-in-1 branding kit bundle Canva," test "launch your complete brand presence this week."

---

## Use Claude to find your positioning gap (before your next product launch)

One source built a Claude skill specifically for this: answer questions about your industry, background, and unfair advantage, and Claude generates a positioning report scoring opportunities out of 100 — identifying what's trending with high demand and low supply and where competitors have gaps.

- [ ] Before launching or promoting any new product, run this exercise: paste into Claude — "I sell [product]. My audience is [description]. My competitors on Etsy are selling [what they sell]. What angles, niches, or customer segments are underserved that I could own? Look for high demand + low competition." Treat the output as a list of hypotheses to validate, not a finished strategy.
- [ ] Check the comment sections on your top 3 competitors' most popular products (Etsy reviews, Instagram comments). Paste 20-30 comments into Claude and ask: "What frustrations or unmet needs appear most often in these?" This is the same competitor gap research the sources described — just without the custom app.

---

## Target the customers who are scared of AI, not the ones already using it

One source cited that 82% of people haven't used AI at all — and specifically called out coaches and service providers as the ones most behind. Your audience is exactly that group.

- [ ] Write one piece of content (email, pin, Instagram post) aimed directly at the business owner who is overwhelmed by AI and feels like everyone else has figured it out except her. The message: your templates work with or without AI, and if she wants to use AI to customise them, you'll show her how. No tech skills required.
- [ ] Test a pin angle: "You don't need to know AI to have a professional brand." It speaks directly to the people avoiding the trend rather than chasing them. There are a lot more of them than there are early adopters.
- [ ] Consider a simple add-on: a short PDF with 5 ChatGPT prompts for customising Instagram captions using your templates. Costs nothing to make, increases perceived value, and positions your products as AI-friendly without being AI-dependent.

---

## Connect Claude to Google Drive to stop copy-pasting between tools

Claude has a built-in Google Drive connector (Settings → Capabilities → connect Drive). Once connected, Claude can read your existing documents, pull context from them, and save outputs directly — no manual copy-pasting.

- [ ] Connect Google Drive and test it on one task you currently do manually — for example: "Read my brand voice doc from Drive and use it to write three Instagram captions for [product]." If it pulls the right file and uses it correctly, you've just removed a step from every content brief.
- [ ] Also test the Gmail connector if you're writing email sequences. Claude can reference past emails you've sent to maintain consistency in tone without you having to re-paste examples.

---

*Full detail on any of these: [ai-tools.md](ai-tools.md)*
