# Vultr Agent Runtime Hackathon: Official Brief

Source: event page (copied verbatim for agent and team context). This is the organizer's brief. Our project-specific decisions live in [`../BUILD_SPEC.md`](../BUILD_SPEC.md) and [`../AGENTS.md`](../AGENTS.md).

- **Date:** Friday, 27 November 2026
- **Format:** 12-hour, in-person hackathon
- **Location:** Netlight Consulting, Stockholm, hosted with Vultr

## Challenge

Build a web-based agent that performs real work, writing and running code or operating a real browser, with every action contained in a sandbox on Vultr. The system should plan tasks, dispatch them to isolated environments, and return verifiable output.

**Containment-first is required:** an agent that only chats is a demo, one that executes safely is a product.

## Tracks

### Pattern A: Sandboxed code execution

- **CSV Analyst:** upload a spreadsheet, ask questions in plain English, get an executed chart plus the code.
- **Prove-It Code Reviewer:** run a snippet or PR and its tests in the sandbox, then report what happened.
- **Chart Anything:** natural language in, executed matplotlib or plotly image out.
- **File Fixer:** messy CSV or JSON in, cleaned file out, with an executed before/after diff.
- **Self-Healing Runner:** run code, read errors, patch and retry, with the retry loop visible on screen.

### Pattern B: Sandboxed browser use

- **Comparison Shopper:** two or three product URLs in, screenshot-backed comparison table out.
- **Form Filler:** structured data in, a multi-step web form filled, with a screenshot trail and an approve-before-submit gate.
- **Site QA Sweep:** find broken flows and links in a web app, with screenshots and repro steps. **(SafePilot QA's track)**
- **Research with Receipts:** a brief where every claim links to a screenshot of its source.
- **Page Watcher:** monitor listing or pricing pages, extract structured data, and diff against the previous day.

## Containment focus areas

Address real safety and reliability challenges in agent execution:

- **Process isolation:** execution never touches the host or app runtime.
- **Secret hygiene:** no API keys or credentials inside the sandbox.
- **Resource limits:** time and memory caps on every run.
- **Lifecycle discipline:** reset or destroy the environment after each task.

Show how isolation makes autonomous execution shippable.

## Required stack

- **Vultr VM:** the backend, acting as the central control and orchestration system.
- **Vultr Serverless Inference:** all agent LLM calls. OpenAI-compatible, base URL `https://api.vultrinference.com/v1`, vision-capable models available.
- **Sandbox boundary:** containers or throwaway instances on Vultr, never inside the app process. Docker strongly recommended; OpenSandbox, gVisor and E2B are good starting points.
- **Vultr API (optional):** spin up and destroy a throwaway instance per task.

## Deliverables

- [ ] Public GitHub repository with setup and documentation
- [ ] Backend deployed on a Vultr VM, with LLM calls through Vultr Serverless Inference
- [ ] Public demo URL with a real product-style experience, not just a local demo
- [ ] Recorded demo video including one containment moment, such as the sandbox absorbing an `rm -rf`, an infinite loop, or a hostile web page
- [ ] Clear explanation of the architecture and use case

## Who can join

Developers, AI/ML and platform engineers, and technical founders building agentic applications.

- **Team size:** 2 to 4 members. Solo participants are helped to join or form a team.
- **What to bring:** a laptop and a GitHub account. No special hardware needed.
- **Skills:** working Python or TypeScript, API experience, and basic LLM familiarity.

Register on Luma first. If shortlisted, secure your spot on the event page.
