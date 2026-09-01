import asyncio
import json
import re

from agents import Agent, Runner, function_tool, trace

from cv import load_cv

MODEL = "gpt-5.4-mini"

CV_TEXT = load_cv()

LANG = {
    "English": "Write in English.",
    "Hebrew": "Write in Hebrew (עברית). Keep company names in their original form.",
}


@function_tool
def search_cv(query: str) -> str:
    """Search Saar's CV/summary for lines related to this query. Use before claiming experience."""
    q = query.lower()
    hits = [line for line in CV_TEXT.splitlines() if q in line.lower() and line.strip()]
    if hits:
        return "\n".join(hits[:12])
    return CV_TEXT[:4000]


researcher = Agent(
    name="Company researcher",
    model=MODEL,
    instructions=(
        "You brief a job candidate. Using ONLY the job posting and any company notes the user pasted, "
        "write 5-8 bullets: what the company seems to do, why this role might exist, "
        "and 1-2 honest personalization hooks. Do not invent facts, funding, or products "
        "that are not in the input. If notes are thin, say so."
    ),
)

matcher = Agent(
    name="CV matcher",
    model=MODEL,
    tools=[search_cv],
    instructions=(
        "You compare a job description to Saar Agmon's CV. "
        "Call search_cv for skills/keywords from the JD. "
        "First line MUST be exactly: Fit: high   OR   Fit: medium   OR   Fit: low\n"
        "Then:\n"
        "- 3 strongest matching experiences (only what is in the CV)\n"
        "- Gaps you must not invent\n"
        "Never claim tools, years, or titles that are not in the CV."
    ),
)

writer = Agent(
    name="Outreach writer",
    model=MODEL,
    instructions=(
        "Write a short recruiter email (120-180 words) from Saar Agmon. "
        "One company-specific sentence from the research, then fit from the matcher, "
        "then one clear ask (15-min call or permission to send a CV). "
        "No buzzword soup. No invented experience. Plain text. Sign as Saar Agmon."
    ),
)

reviewer = Agent(
    name="Recruiter reviewer",
    model=MODEL,
    instructions=(
        "You are a busy recruiter. Critique this outreach. Be blunt. "
        "Check: too long? generic? missing ask? claims not backed by the match notes? "
        "Reply with: Verdict (send / revise), 3 bullets of issues, and what to change. "
        "Do not rewrite the full email."
    ),
)

improver = Agent(
    name="Outreach improver",
    model=MODEL,
    instructions=(
        "Rewrite using the reviewer notes. Do not add experience that was not in the match notes.\n"
        "Output exactly two blocks:\n"
        "### EMAIL\n"
        "(under 180 words, plain text, ready to send)\n"
        "### LINKEDIN\n"
        "(under 300 characters, no Dear/Hi Mr, one specific ask, no invented facts)\n"
    ),
)

reply_desk = Agent(
    name="Reply desk",
    model=MODEL,
    instructions=(
        "A recruiter replied to Saar's outreach. Classify and plan the next step.\n"
        "Return STRICT JSON with keys:\n"
        '  "label": one of interested, reject, question, times, other\n'
        '  "status": one of replied, interview, rejected, hold\n'
        '  "next_action": short string for Saar\n'
        '  "draft_reply": Saar\'s next email if a reply is appropriate, else empty string\n'
        "No markdown fences."
    ),
)


def parse_fit(match_notes: str) -> str:
    m = re.search(r"fit:\s*(high|medium|low)", match_notes or "", re.I)
    return (m.group(1).lower() if m else "medium")


def parse_improved(text: str) -> tuple[str, str]:
    email, linkedin = text, ""
    if "### EMAIL" in text:
        rest = text.split("### EMAIL", 1)[1]
        if "### LINKEDIN" in rest:
            email, linkedin = rest.split("### LINKEDIN", 1)
        else:
            email = rest
    return email.strip(), linkedin.strip()


def _pack(company, position, jd, notes, research="", match="", language="English") -> str:
    return (
        f"{LANG.get(language, LANG['English'])}\n\n"
        f"Company: {company}\nRole: {position}\n\n"
        f"Company notes (may be empty):\n{notes or '(none)'}\n\n"
        f"Job posting:\n{jd}\n\n"
        f"Research:\n{research or '(not yet)'}\n\n"
        f"Match notes:\n{match or '(not yet)'}\n"
    )


async def generate_outreach(
    company: str, position: str, jd: str, company_notes: str, language: str = "English"
) -> dict:
    base = _pack(company, position, jd, company_notes, language=language)
    with trace("Job outreach generate"):
        research_run, match_run = await asyncio.gather(
            Runner.run(
                researcher,
                base + "\nWrite the company research brief.",
            ),
            Runner.run(
                matcher,
                base + "\n\nCandidate CV:\n"
                + CV_TEXT[:8000]
                + "\n\nMatch this JD to the CV. Use search_cv.",
            ),
        )
        research = research_run.final_output
        match_notes = match_run.final_output
        fit = parse_fit(match_notes)
        if fit == "low":
            return {
                "research": research,
                "match_notes": match_notes,
                "draft": "",
                "review": "Skipped writing: CV fit is low. Do not send a stretch email.",
                "final_message": "",
                "linkedin_message": "",
                "fit": fit,
            }
        packed = _pack(
            company, position, jd, company_notes, research, match_notes, language
        )
        draft_run = await Runner.run(
            writer, packed + "\nWrite the recruiter email now."
        )
        draft = draft_run.final_output
        review_run = await Runner.run(
            reviewer,
            packed + f"\n\nDraft email:\n{draft}\n\nReview this as a recruiter.",
        )
        review = review_run.final_output
        improved_run = await Runner.run(
            improver,
            packed + f"\n\nDraft:\n{draft}\n\nReviewer:\n{review}\n\nRewrite now.",
        )
        final, linkedin = parse_improved(improved_run.final_output)
    return {
        "research": research,
        "match_notes": match_notes,
        "draft": draft,
        "review": review,
        "final_message": final,
        "linkedin_message": linkedin,
        "fit": fit,
    }


async def handle_reply(
    role_summary: str, outbound: str, inbound: str, language: str = "English"
) -> dict:
    prompt = (
        f"{LANG.get(language, LANG['English'])}\n"
        f"{role_summary}\n\nSaar sent:\n{outbound}\n\nRecruiter replied:\n{inbound}\n"
    )
    with trace("Job outreach reply"):
        result = await Runner.run(reply_desk, prompt)
    text = result.final_output.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:]
        text = text.strip()
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = {
            "label": "other",
            "status": "replied",
            "next_action": "Read the reply and respond manually.",
            "draft_reply": text,
        }
    return data
