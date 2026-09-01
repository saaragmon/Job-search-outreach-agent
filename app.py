from pathlib import Path

from dotenv import load_dotenv
import gradio as gr

from db import (
    add_message,
    export_csv_path,
    find_duplicate,
    get_role,
    insert_role,
    tracker_rows,
    update_role,
)
from mail import EMAIL_ADDRESS, assert_can_send, send_email
from pipeline import generate_outreach, handle_reply

_HERE = Path(__file__).resolve().parent
load_dotenv(_HERE / ".env", override=True)
_course_env = _HERE.parents[2] / ".env" if len(_HERE.parents) >= 3 else None
if _course_env is not None and _course_env.exists():
    load_dotenv(_course_env, override=False)
load_dotenv(override=True)

HEADERS = [
    "id",
    "company",
    "position",
    "contact",
    "fit",
    "status",
    "next_action",
    "created_at",
]


def _table():
    return tracker_rows()


def _empty_gen(msg: str):
    return msg, "", "", "", "", "", None, None, _table()


async def on_generate(
    company,
    position,
    jd,
    notes,
    contact_name,
    contact_email,
    language,
    allow_duplicate,
):
    company, position, jd = company.strip(), position.strip(), jd.strip()
    if not company or not position or not jd:
        return _empty_gen("Fill in company, position, and job posting.")

    dup = find_duplicate(company, position)
    if dup and not allow_duplicate:
        return _empty_gen(
            f"Already tracked as id {dup['id']} ({dup['status']}). "
            "Tick “allow duplicate” to generate again."
        )

    out = await generate_outreach(company, position, jd, notes.strip(), language)
    low = out["fit"] == "low"
    next_action = (
        "Low CV fit — do not send; tighten applications or skip this role."
        if low
        else "Review the email + LinkedIn note, copy or send to your inbox."
    )
    role_id = insert_role(
        company=company,
        position=position,
        jd_text=jd,
        company_notes=notes.strip(),
        contact_name=contact_name.strip(),
        contact_email=contact_email.strip(),
        research=out["research"],
        match_notes=out["match_notes"],
        draft=out["draft"],
        review=out["review"],
        final_message=out["final_message"],
        linkedin_message=out["linkedin_message"],
        language=language,
        fit=out["fit"],
        status="hold" if low else "drafted",
        next_action=next_action,
    )
    status = (
        f"Saved as id {role_id}. Fit: {out['fit']}."
        + (" Writing skipped." if low else "")
    )
    return (
        out["research"],
        out["match_notes"],
        out["draft"],
        out["review"],
        out["final_message"],
        out["linkedin_message"],
        status,
        role_id,
        role_id,
        _table(),
    )


def on_send(role_id, final_message, contact_email, position, allow_external):
    if role_id is None:
        return "Generate a draft first.", _table()
    role_id = int(role_id)
    role = get_role(role_id) or {}
    if (role.get("fit") or "").lower() == "low" and not allow_external:
        return "Fit is low — sending blocked. Apply elsewhere or tick the override only if you really mean it.", _table()
    body = (final_message or "").strip()
    if not body:
        return "Nothing to send (empty draft).", _table()
    to_addr = (contact_email or "").strip() or role.get("contact_email") or ""
    blocked = assert_can_send(to_addr, allow_external)
    if blocked:
        return blocked, _table()
    subject = f"{position or role.get('position')} — Saar Agmon"
    result = send_email(to_addr, subject, body)
    update_role(
        role_id,
        final_message=body,
        contact_email=to_addr,
        status="sent",
        next_action="Wait for a reply, or paste one in the Reply tab.",
    )
    add_message(role_id, "out", body)
    return result, _table()


async def on_reply(role_id, inbound):
    if role_id is None:
        return "Enter the application id from the tracker.", "", "", _table()
    role = get_role(int(role_id))
    if not role:
        return "Unknown id.", "", "", _table()
    inbound = inbound.strip()
    if not inbound:
        return "Paste the recruiter reply.", "", "", _table()
    add_message(role["id"], "in", inbound)
    summary = (
        f"Company: {role['company']}\nRole: {role['position']}\n"
        f"Match notes:\n{role['match_notes']}"
    )
    data = await handle_reply(
        summary,
        role["final_message"] or role["draft"] or "",
        inbound,
        role.get("language") or "English",
    )
    update_role(
        role["id"],
        status=data.get("status") or "replied",
        next_action=data.get("next_action") or "",
    )
    label = data.get("label", "")
    draft = data.get("draft_reply") or ""
    return (
        f"Classified as: {label}\nStatus → {data.get('status')}\nNext: {data.get('next_action')}",
        draft,
        data.get("status") or "",
        _table(),
    )


def send_followup(role_id, draft, contact_email, position, allow_external):
    if role_id is None:
        return "Need an application id.", _table()
    role_id = int(role_id)
    role = get_role(role_id) or {}
    to_addr = (contact_email or "").strip() or role.get("contact_email") or ""
    body = (draft or "").strip()
    if not body:
        return "No draft reply to send.", _table()
    blocked = assert_can_send(to_addr, allow_external)
    if blocked:
        return blocked, _table()
    result = send_email(to_addr, f"Re: {position or role.get('position')}", body)
    add_message(role_id, "out", body)
    update_role(role_id, next_action="Follow-up sent.")
    return result, _table()


def on_export():
    return str(export_csv_path())


with gr.Blocks(title="Job outreach agent") as demo:
    gr.Markdown(
        "# Job-search outreach\n"
        f"Default send target is **your** inbox (`{EMAIL_ADDRESS or 'set EMAIL_ADDRESS in .env'}`). "
        "Agents research (from pasted notes only), match the CV, skip weak fits, "
        "draft email + LinkedIn, then a recruiter-reviewer rewrites. "
        "Paste replies to classify. No Hugging Face / no inbound mailbox."
    )
    role_id = gr.State(None)

    with gr.Tab("New outreach"):
        with gr.Row():
            company = gr.Textbox(label="Company")
            position = gr.Textbox(label="Position")
            language = gr.Dropdown(["English", "Hebrew"], value="English", label="Language")
        jd = gr.Textbox(label="Job posting", lines=10)
        notes = gr.Textbox(
            label="Company notes (paste About page / what you know)",
            lines=3,
        )
        with gr.Row():
            contact_name = gr.Textbox(label="Contact name")
            contact_email = gr.Textbox(
                label="Contact email — use YOUR Gmail unless you tick the box below",
                value=EMAIL_ADDRESS or "",
            )
        with gr.Row():
            allow_duplicate = gr.Checkbox(label="Allow duplicate company + role")
            allow_external = gr.Checkbox(
                label="I typed this address on purpose (send to someone who is not me)"
            )
        gen = gr.Button("Generate", variant="primary")
        gen_status = gr.Textbox(label="Status", lines=2)
        with gr.Row():
            research = gr.Textbox(label="Research", lines=8, show_copy_button=True)
            match_notes = gr.Textbox(label="CV match", lines=8, show_copy_button=True)
        with gr.Row():
            draft = gr.Textbox(label="First draft", lines=8, show_copy_button=True)
            review = gr.Textbox(label="Recruiter reviewer", lines=8, show_copy_button=True)
        final = gr.Textbox(
            label="Improved email (copy or edit, then Send)",
            lines=10,
            show_copy_button=True,
        )
        linkedin = gr.Textbox(
            label="LinkedIn note (copy-paste into LinkedIn — not emailed)",
            lines=4,
            show_copy_button=True,
        )
        send = gr.Button("Send email")
        send_status = gr.Textbox(label="Send status")

    with gr.Tab("Reply"):
        reply_id = gr.Number(label="Application id", precision=0)
        inbound = gr.Textbox(label="Paste recruiter reply", lines=8)
        classify = gr.Button("Classify + draft next reply")
        classify_out = gr.Textbox(label="Classification", lines=5)
        next_draft = gr.Textbox(
            label="Draft reply (copy or send)", lines=10, show_copy_button=True
        )
        send_next = gr.Button("Send follow-up")
        follow_status = gr.Textbox(label="Follow-up status")

    with gr.Tab("Tracker"):
        grid = gr.Dataframe(headers=HEADERS, value=_table(), interactive=False)
        with gr.Row():
            refresh = gr.Button("Refresh")
            export_btn = gr.Button("Export CSV")
        csv_file = gr.File(label="CSV")

    gen.click(
        on_generate,
        inputs=[
            company,
            position,
            jd,
            notes,
            contact_name,
            contact_email,
            language,
            allow_duplicate,
        ],
        outputs=[
            research,
            match_notes,
            draft,
            review,
            final,
            linkedin,
            gen_status,
            role_id,
            reply_id,
            grid,
        ],
    )
    send.click(
        on_send,
        inputs=[role_id, final, contact_email, position, allow_external],
        outputs=[send_status, grid],
    )
    classify.click(
        on_reply,
        inputs=[reply_id, inbound],
        outputs=[classify_out, next_draft, follow_status, grid],
    )
    send_next.click(
        send_followup,
        inputs=[reply_id, next_draft, contact_email, position, allow_external],
        outputs=[follow_status, grid],
    )
    refresh.click(lambda: _table(), outputs=[grid])
    export_btn.click(on_export, outputs=[csv_file])


if __name__ == "__main__":
    demo.launch(inbrowser=True)
