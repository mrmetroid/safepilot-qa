# Submission Checklist

Vultr Agent Runtime Hackathon, Stockholm, 27 November 2026.

**Hard deadline: 19:00 CET.** Submit before that time. Do not assume late moderator approval will save an unsubmitted form.

Sources used for this checklist:

- Event page: https://community.vultr.com/e/vultr-agent-runtime-hackathon
- Luma event: https://luma.com/stockholm-nn3n
- Credits guide PDF: https://del1.vultrobjects.com/partnerships/How%20to%20Claim%20Hackathon%20Credits%20-%20Vultr%20Agent%20Runtime%20Hackathon.pdf
- Project submission PDF: https://del1.vultrobjects.com/partnerships/Project%20Submission%20-%20Vultr%20Agent%20Runtime%20Hackathon.pdf

Judging rubric and prize details were not published on those pages at the time this repo was written. Do not invent them. Ask in the room if you need official scoring weights.

## 1. Credits and accounts (do this first)

- [ ] Redeem the **$200** hackathon credits with code `AGENTRUNTIME26` at [Vultr Billing](https://my.vultr.com/billing/?promo=HACKATHON). Follow the official credits guide PDF.
- [ ] Use an email address that has **not previously been used on Vultr**. A reused email can block the promo.
- [ ] Confirm the credit balance is visible in the Vultr portal before provisioning the Stockholm VM.
- [ ] Create a Serverless Inference API key and store it only in the control plane `.env` on the VM.
- [ ] Every teammate creates a [Vultr Community](https://community.vultr.com) account with the same email they will list on the submission.

## 2. Room check-in (required to unlock the form)

- [ ] On site, check in at https://community.vultr.com/e/vultr-agent-runtime-hackathon with the **8-character room code**.
- [ ] Confirm that **"Submit your build"** (Project Showcases) is visible after check-in. The official submission PDF says this button does not appear until you check in.
- [ ] Ask a volunteer, once, where they want the demo video link, and whether moderator approval of the post can happen after 19:00 CET as long as the form is submitted before 19:00. Record the answer. Do not wait on that answer to start recording the video.

## 3. Technical readiness before you hit record

- [ ] Public GitHub repo is `https://github.com/mrmetroid/safepilot-qa` (this repo must stay public).
- [ ] Live demo URL is reachable on the Vultr Stockholm VM (port 80/443, not a laptop localhost).
- [ ] `GET /api/health` is green for control plane, Docker, and Vultr Inference.
- [ ] One clean architecture diagram or screenshot is exported (README mermaid rendered, or a simple board photo plus the diagram). You will upload it on the form.
- [ ] README table at the top has the live demo URL and the recorded video URL filled in.
- [ ] The "How we use Vultr" block in the README is still accurate (Stockholm Cloud Compute + Docker + Serverless Inference, no false VX1 claim).

## 4. Demo video (60-90 seconds)

The Community form has no video field. Put the link at the top of the README and at the top of the Overview field. Use an unlisted YouTube, Loom, or similar public link that does not require a login.

Suggested script (keep it live, not a slide deck):

1. **0:00-0:10 Hook.** "Untrusted AI code deserves untrusted AI testers in disposable boxes." Show the dashboard on the Vultr URL.
2. **0:10-0:20 Start the run.** Click **Load Adversarial Test App (Demo Preset)** (or paste a preview URL). Show three boxes spawn in parallel.
3. **0:20-0:35 Box 1 gate.** Box 1 reaches checkout. Point at the Approve / Block bar. Click **Approve**. Say the irreversible submit is human-gated.
4. **0:35-0:55 Containment Moment.** Box 3 hits the promo or hostile path, CPU spikes or injection is flagged, the container is killed, and the red **Containment Receipt** appears (`secrets_exposed: 0`, `host_impact: "none"`, `container_destroyed: true`). Call out that Boxes 1 and 2 are still running.
5. **0:55-1:20 Verdict.** Box 2's red-boxed mobile CTA. Final banner **DO NOT SHIP**. Click **Copy Fix Prompt for Cursor** and paste it into a visible editor for one beat. End on the public Vultr URL.

- [ ] Video recorded after a successful live run on the public URL.
- [ ] Containment Moment is visible, not described after the fact.
- [ ] Link added to README and Overview.

## 5. Project Showcases form fields

Fill every required field. Attach the project to this event.

| Field | What to enter |
| --- | --- |
| Project Name | SafePilot QA |
| Short Description | Untrusted AI code deserves untrusted AI testers in disposable boxes. Three isolated Playwright sandboxes on a Vultr Stockholm VM crash-test a preview, vision-check mobile UI, and emit a SHIP IT or DO NOT SHIP verdict. |
| Architecture screenshots / diagrams | Upload the architecture diagram from the README (rendered mermaid or equivalent screenshot). Add a dashboard screenshot that shows all three boxes and a Containment Receipt if you have one. |
| Tag | Must include `Hackathons` |
| Public Repo Link | https://github.com/mrmetroid/safepilot-qa |
| Live Demo URL | The public Vultr-hosted dashboard URL |
| Tech Stack | Vultr Cloud Compute (Stockholm), Docker, Playwright, FastAPI, Vultr Serverless Inference (`qwen3.8-flash-next`), Caddy |
| Overview | First line: recorded demo video URL. Then 1-2 short paragraphs: the 3-box swarm, the Approve-Before-Submit gate, the live Containment Moment, and the Cursor fix prompt. |
| How did you use Vultr? | Paste the block from the README section **How we use Vultr**. |
| Team Members | List every teammate's Vultr Community account / name. Everyone listed should already have a Community account. |
| Event | Vultr Agent Runtime Hackathon |

- [ ] All fields above filled.
- [ ] Tag includes `Hackathons`.
- [ ] Event is set to **Vultr Agent Runtime Hackathon**.
- [ ] Form submitted before **19:00 CET**.

## 6. Timeline buffer (build day)

Aim to stop feature work by **17:30 CET**, record by **18:15 CET**, and submit by **18:45 CET**. The last 15 minutes are only for "the form did not show up" or "the video link is processing" problems.

If something slips:

1. Protect the live Containment Moment, the Box 1 approval gate, and a public Vultr URL. Those are the rules-shaped demo.
2. A slightly rough UI is acceptable. A missing sandbox, a missing inference call, or a frontend hosted off Vultr is not.
3. If the recorded video is still uploading at 18:50, submit the form with the live demo URL and a "video link incoming in README" note only if a volunteer said that is acceptable. Otherwise wait for the link and submit before 19:00.

## 7. Day-of contacts and unknowns

Confirm in the room (do not block the build on these):

- The 8-character check-in code.
- Whether submission visibility or moderator approval can complete after 19:00 CET if the form itself was sent before 19:00.
- Any video length limit or preferred host.
- The official judging rubric, if they publish or announce it.

Keep answers here:

```
Room code:
Video instructions:
Rubric notes:
Volunteer names:
```
