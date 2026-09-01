# Job-search outreach agent

A small **multi-agent** app for internship / early-career outreach.

## About

Built by **[Saar Agmon](https://github.com/saaragmon)** — Industrial Engineering & Management student at Ben-Gurion University, focused on data, AI, and using agents for real workflows (not just chat).

This repo is a portfolio project: take a job posting, check it honestly against a CV, draft outreach, have a second model critique it like a recruiter, then track status. It started from OpenAI Agents SDK patterns (tools, parallel runs, a reviewer step) and is meant to be easy to clone and demo locally.

- GitHub: [saaragmon/Job-search-outreach-agent](https://github.com/saaragmon/Job-search-outreach-agent)
- Default safety: email **yourself** unless you explicitly allow another address

You paste a job posting. The app:

1. Writes a company brief from **your notes + the JD** (it does not invent facts)
2. Compares the role to **your CV**
3. If the fit is **low**, it **does not write an email** (no fake-strong pitch)
4. If the fit is ok, it drafts an email, then a second LLM **reviews it like a recruiter** and rewrites it
5. Also drafts a short **LinkedIn** note you can copy
6. Saves everything in SQLite: company → role → contact → status → next action

Built with the [OpenAI Agents SDK](https://openai.github.io/openai-agents-python/) (`Agent`, `Runner`, tools, traces) and a Gradio UI.

This is a **draft + track** tool. It does **not** scrape recruiter emails. You type the address. By default it will **only send to your own inbox**.

---

## Demo (safe)

1. Put **your** Gmail in Contact email (it is filled from `.env` if set)
2. Paste any JD + a few company notes
3. Click **Generate** (takes ~1 minute — several model calls)
4. Read **CV match**, **reviewer**, **improved email**, **LinkedIn note**
5. Click **Send** — mail goes to **you**, not a company
6. On **Reply**, paste a fake recruiter message and classify it
7. **Tracker** → Export CSV

Do **not** tick “I typed this address on purpose” unless you really mean to email that person.

---

## How the agents are wired

```
                ┌─────────────┐
   JD + notes → │ Researcher  │ ─┐
                └─────────────┘  │ asyncio.gather
                ┌─────────────┐  │
         CV  →  │ CV matcher  │ ─┘
                └─────────────┘
                       │
              fit = low? ── yes → stop (status: hold)
                       │ no
                ┌─────────────┐
                │ Writer      │
                └─────────────┘
                ┌─────────────┐
                │ Recruiter   │  second LLM
                │ reviewer    │
                └─────────────┘
                ┌─────────────┐
                │ Improver    │  email + LinkedIn
                └─────────────┘
                       │
              you copy / send (guarded)
```

Orchestration is **in code** for research + match (parallel). Writing, review, and rewrite are sequential LLM steps. Recruiter replies are **pasted** (no inbound mailbox).

---

## Run locally

Needs Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
git clone https://github.com/saaragmon/Job-search-outreach-agent.git
cd Job-search-outreach-agent
cp .env.example .env
# add OPENAI_API_KEY (and optional Gmail SMTP vars)
uv sync
uv run app.py
```

Open the local URL (e.g. http://127.0.0.1:7865).

Optional: put `resume.pdf` next to `app.py` (gitignored). `summary.txt` is the short bio used for matching.

### Gmail send (optional)

App password (16 characters, no spaces), 2-step verification on:

```
EMAIL_ADDRESS=you@gmail.com
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_APP_PASSWORD=...
```

Without these, Send is a dry run (prints in the terminal).

Traces: [platform.openai.com/traces](https://platform.openai.com/traces)

---

## What this is not

- Not a Hugging Face Space (Gradio Spaces are paid; this app needs a secret API key)
- Not an email harvester
- Not automatic apply-to-all-jobs

---

## Project layout

| File | Role |
|---|---|
| `app.py` | Gradio UI |
| `pipeline.py` | Agents + generate/reply |
| `db.py` | SQLite tracker |
| `mail.py` | SMTP + “send only to me” guard |
| `cv.py` | Load `summary.txt` / `resume.pdf` |
| `summary.txt` | Candidate bio |

---

## License

Personal portfolio project. Use and adapt freely.
