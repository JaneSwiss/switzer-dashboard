"""
build_competitor_section.py
Generates the ## Competitor Analysis markdown section from scraped Pinterest profile data.
Called as a post-processing step after the main audit.
"""
from __future__ import annotations
import os
import anthropic


COMPETITORS = [
    {
        "username": "marigoldgrey",
        "followers": 48919,
        "board_count": 86,
        "bio": "The best gift ideas, unique gift boxes & creative gift baskets for corporate gifts, wedding welcome bags, holiday gifts and more. Gift ideas for women, men & kids.",
        "url": "https://www.pinterest.com/marigoldgrey",
    },
    {
        "username": "ohheygiftday",
        "followers": 24,
        "board_count": 17,
        "bio": "Curated gift boxes for every occasion. Thoughtfully filled, beautifully wrapped, and ready to give.",
        "url": "https://www.pinterest.com/ohheygiftday",
    },
    {
        "username": "giftsforyounow",
        "followers": 8605,
        "board_count": 109,
        "bio": "Creating memories for life with fun personalized gifts for every occasion!",
        "url": "https://www.pinterest.com/giftsforyounow",
    },
    {
        "username": "vividgiftideas",
        "followers": 25235,
        "board_count": 71,
        "bio": "Unique gift ideas. Collect, share, inspire on the art of gift giving. Lover of cats and pretty things.",
        "url": "https://www.pinterest.com/vividgiftideas",
    },
    {
        "username": "amesandoates",
        "followers": 1980,
        "board_count": 31,
        "bio": "Modern gifting, made simple. We provide luxury curated & custom gifting experiences, perfect for corporate clients and individuals who want thoughtful, personalised gifts.",
        "url": "https://www.pinterest.com/amesandoates",
    },
]


def _fmt_followers(v: int) -> str:
    if v >= 1_000_000:
        return f"{v/1_000_000:.1f}M"
    if v >= 1_000:
        return f"{v/1_000:.0f}K"
    return str(v)


def build_competitor_section(niche: str, products: str) -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))

    lines = ["## Competitor Analysis\n"]

    # Summary table
    lines.append("| Account | Followers | Boards | Bio |")
    lines.append("|---------|-----------|--------|-----|")
    for c in COMPETITORS:
        followers = _fmt_followers(c["followers"])
        bio = c["bio"][:70] + "..." if len(c["bio"]) > 70 else c["bio"]
        lines.append(
            f"| [@{c['username']}]({c['url']}) | {followers} | {c['board_count']} | {bio} |"
        )
    lines.append("")

    # Per-competitor analysis
    for c in COMPETITORS:
        prompt = f"""Write a sharp Pinterest competitor snapshot for this account. Client niche: {niche}. Client sells: {products}.

Account: @{c['username']}
Followers: {_fmt_followers(c['followers'])}
Number of boards: {c['board_count']}
Bio: {c['bio']}
Pinterest URL: {c['url']}

Two short paragraphs only:
1. What they appear to sell and how their volume of boards ({c['board_count']} boards) and bio positioning suggests their content strategy.
2. One specific gap or weakness the client (Corner Cove Studios) can exploit given their handcrafted, in-house personalisation angle.

Under 100 words total. Be specific. No filler. Do not mention that you couldn't access their pins directly — work from what you have."""

        msg = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}],
        )

        followers_str = _fmt_followers(c["followers"])
        lines.append(f"### @{c['username']} — {followers_str} followers\n")
        lines.append(msg.content[0].text)
        lines.append("")

    return "\n".join(lines)


if __name__ == "__main__":
    section = build_competitor_section(
        niche="personalized gifts custom drinkware small gifts",
        products="High-quality custom gifts, drinkware and personalised products - all handcrafted in-house",
    )
    print(section)
