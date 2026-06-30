# GLOSSARY — Plain-English Guide to Every Technical Term

*For non-technical founders and operators. If you see a term you don't know, it's here.*

---

## GitHub Concepts

**Pull Request (PR)**
A formal request to change code. You write new code, push it, and ask the team "Should we merge this?" Everyone reviews, comments, and agrees before merging (combining it with the main codebase).

**GitHub App**
Software that plugs into GitHub like a browser extension. It watches for events (PR opened, code pushed) and does something automatically (runs checks, posts messages, updates statuses).

**Webhook**
A push notification from GitHub to your app. When a PR opens, GitHub sends a message to our app saying "Hey, new PR!" The app then wakes up and runs checks.

**GitHub Checks API**
A way our app talks back to GitHub and says: "I ran my checks on this PR. Here are the results." GitHub displays them right on the PR, colored green (pass) or orange (needs attention).

**Installation**
When you click "Install" on a GitHub App, you're granting it permission to watch your repos and post results. You can uninstall anytime.

**Permission (GitHub App)**
Rules about what an app can read/write:
- **Read** = can see the code but can't change it.
- **Write** = can change things (like post comments, update status).
- **Contents R** = can read your code.
- **PRs R/W** = can read PR info and post reviews/comments.
- **Checks R/W** = can create and update check results.
- **Metadata R** = can read public repo information.

**Event (GitHub)**
Something that happens: a PR opens, a commit is pushed, a review is posted. We listen to specific events and react to them.

---

## Code Quality & Security

**SAST (Static Application Security Testing)**
Code analyzing software that reads your source code (without running it) and looks for dangerous patterns: things like hardcoded passwords, unsafe string concatenation (SQL injection risk), or missing input validation. Like a spell-checker for security mistakes.

**CVE (Common Vulnerabilities and Exposures)**
A database entry for a known security bug in publicly available software. Example: "Version 2.1 of library X has a CVE that lets attackers crash the server." We check: "Is this library version installed, and does it have a known CVE?" If yes, we report it.

**Vulnerable Dependency**
A library (dependency) your code uses that has a known security flaw (a CVE). If the flaw could affect your code, it's a problem.

**Secret / API Key**
A private string (password, token, credentials) that proves who you are to a third-party service. Examples: database password, AWS API key, Stripe payment key. Should NEVER be committed to code.

**Leaked Secret**
A secret (password, API key) that was accidentally written into code and saved to the repo. Bad: anyone with access to the repo can see it. We detect this using pattern matching and entropy checks.

**HMAC (Keyed Hash Message Authentication Code)**
A cryptographic "signature" for a message. GitHub signs every webhook it sends us with a secret key, and we verify the signature. This proves the message really came from GitHub and nobody faked it.

**HMAC-SHA256**
The specific algorithm: hash the message using the SHA-256 algorithm with a secret key. If the signature matches, the message is real.

---

## Package & Dependency Management

**Package / Library / Dependency**
Code written by someone else that your project uses. Examples: Python's `requests` library, JavaScript's `react`. You declare "I need version X.Y of package Z," and a tool fetches and installs it.

**Package Registry**
A central store where packages live. Like an app store for code.
- **PyPI** = Python packages
- **npm** = JavaScript packages
- **crates.io** = Rust packages

**Hallucinated Package / Made-Up Package**
A package that doesn't exist in any official registry. An AI tool might suggest `import quantumllm_helper` (sounds good, doesn't exist). We check every declared package against the real registries.

**Workspace / Monorepo**
A single repo with multiple sub-projects. Example: a JavaScript monorepo might have `packages/api`, `packages/ui`, `packages/lib`. When one sub-project depends on another, it uses a `workspace:` reference, not an external package. We whitelist these so they don't get flagged as fake.

**Scoped Package**
A package with a namespace: `@mycompany/utils`. The `@mycompany` part is the "scope." These are often private or organization-specific and we handle them carefully.

**Private Registry**
A custom package store (not PyPI or npm) run by a company for internal code. We check for private registry config and don't flag packages that are supposed to come from there.

**Lockfile**
A file (`package-lock.json`, `poetry.lock`, `Cargo.lock`) that "locks down" exact versions of every dependency. Ensures everyone uses the same versions. We parse these to know what's actually installed.

---

## Code Issues

**Placeholder / TODO**
Code that's incomplete. Examples:
- `# TODO: implement password validation`
- `throw new NotImplementedError()`
- An empty function body
- `pass  # fix this later`

**Incomplete Code**
Functions or modules that look done but aren't—empty bodies, ellipsis (`...`), or stubs that just return dummy data. We flag these because shipping incomplete code is risky.

**AI Reasoning Scratchpad / Thinking Block**
When an AI tool (like Claude) is thinking through a problem, it sometimes includes `<thinking>...</thinking>` tags with scratch work. Accidentally committing these is embarrassing and wastes space. We detect and flag them.

---

## Licensing

**License / Software License**
A legal document that says "Here's what you can and can't do with this code." GPL says "If you use this, you must open-source your own code." MIT says "Use it freely, just give credit." Apache says "Use it, but acknowledge it and don't claim patents."

**License Compatibility**
Whether two licenses can coexist in the same project. Example: GPL (open-source required) + closed-source proprietary code = incompatible, risky.

**GPL / Copyleft**
A license that requires you to open-source any code you write that uses GPL code. If you're building a closed-source product, GPL is risky.

**Proprietary / Closed Source**
Code that's private, not open-source. You can't share it or modify it without permission.

**Unknown License**
We don't know the legal terms. Risk depends on context, but it's a yellow flag.

---

## App Architecture & Operations

**API / API Endpoint**
A URL your app exposes (like `/webhooks/github`) that accepts requests and sends back responses. External services (GitHub) call these to trigger actions.

**Async / Asynchronous**
Code that doesn't wait for everything to finish in order. Example: webhook arrives → immediately return 202 (OK) → run checks in the background. Fast response, work happens later.

**Queue / Job Queue**
A to-do list for background tasks. Instead of running checks immediately (slow), we add a job to the queue, return quickly, and a worker processes jobs one by one.

**Redis / Cache**
In-memory data storage. Super fast. We use it for job queues, rate-limit tracking, and caching (storing data we just fetched so we don't fetch it again).

**PostgreSQL / Relational Database**
A permanent data store. Unlike Redis, it survives crashes. Stores all PR analyses, findings, and audit logs. Organized into tables (like spreadsheets).

**Migration / Database Migration**
A script that updates the database schema (adds a table, changes a column). We use `Alembic` to version migrations so they can be rolled back.

**Idempotency / Idempotent Operation**
If you run it twice, it's the same as running it once. Example: "Add user X" is idempotent if a second run doesn't create a duplicate. Webhooks can be delivered twice (by accident), so our code is idempotent.

**Deduplication / Dedupe**
Detecting and discarding duplicates. GitHub might send the same webhook twice; we detect it (via `X-GitHub-Delivery` header) and only process it once.

**Correlation ID**
A unique ID assigned to one "request" that travels through the whole system. Lets us trace one PR check from webhook arrival through all the background steps. Useful for debugging.

**Observability / Logging / Tracing**
Tracking what the system is doing. Logs are messages ("started check X"). Traces show the flow (webhook → queue → worker → database). Helps us debug problems.

---

## Deployment & Hosting

**Containerization / Docker**
Packaging your app as a lightweight "container" that runs the same way on any computer. Like shipping a desktop app in a box.

**Image / Container Image**
The blueprint for a container. Includes the code, dependencies, and everything needed to run.

**Distroless Image**
A very minimal container image with only what's necessary to run the app, no extra tools. Smaller = faster + harder to attack.

**Non-root User**
Running code as a regular user, not the admin (root). Limits damage if the code is compromised.

**Fly.io**
A hosting platform for deploying apps. We run our API and worker there.

**Vercel**
A hosting platform for dashboards and websites. We host the Next.js dashboard there.

**Supabase**
A managed PostgreSQL database + authentication service. We use it for data storage and user login.

**Upstash**
A managed Redis service. We use it for job queues.

**Cloudflare**
A global network that sits in front of our app. Protects against attacks (DDoS), caches responses, restricts access by IP.

**WAF (Web Application Firewall)**
Software that filters malicious requests before they reach your app. Cloudflare provides this.

**Rate Limiting**
Restricting how many requests a client can make in a time window. Prevents abuse.

**TLS / HTTPS / SSL**
Encryption protocol that secures communication over the internet. Your browser uses it (that `https://` in the address bar). We use Let's Encrypt (free) to get TLS certificates.

---

## Development & CI/CD

**GitHub Actions**
GitHub's built-in automation. We use it to test code, run security scans, and auto-deploy when pushing to main.

**CI/CD (Continuous Integration / Continuous Deployment)**
Automated testing + deployment. Write code → push → tests run → if green, automatically deploy. Catches bugs fast.

**Dogfood / Eating Your Own Dog Food**
Using your own product on your own project. We run the Guard on the Guard's own code. Proves it works.

**Kill Switch / Feature Flag**
An environment variable that disables a checker without redeploying. Example: `DISABLED_ANALYZERS=SECRETS` disables secret checks. Useful if a checker is misfiring.

---

## Confidence & Findings

**Confidence Level**
How sure we are about a finding:
- **CERTAIN** = A reproducible, verifiable fact (package doesn't exist, secret checksum matches known format). Can block.
- **HIGH** = Very likely but not guaranteed (strong pattern match, multiple signals). Advisory.
- **MEDIUM** = Uncertain; context-dependent (placeholder code that might be intentional). Advisory.

**Finding**
One issue we discovered. Includes: what it is, where in the code, why it's a problem, and suggested fix.

**Block-Eligible**
A finding that can stop a merge if blocking is turned on. Only CERTAIN findings with block enabled.

**Action Required**
GitHub's status color for "Findings detected; needs attention." Orange. Doesn't block, but makes it obvious something needs review.

**False Positive (FP)**
We flagged something as a problem when it's actually fine. Bad. We measure FP rate and aim for <1%.

---

## User Experience

**Dashboard**
A web page showing your PR history, findings, settings, and AI explanations.

**Plain English**
Non-technical language. Instead of "SAST P1 violation: CWE-89 SQL injection risk," the AI Crew says: "Your code builds a database query from user input without checking it. An attacker could break in. Here's how to fix it."

**Advisory**
A heads-up that something might be risky, with advice. Not a hard block.

**Block / Blocking**
Preventing a PR from merging. Only CERTAIN findings, only if the repo enabled it, only if the user approved.

**Bypass / Override**
Allowing a merge even though the Guard flagged something. Dashboard interface for this (logged in audit trail).

---

All terms are used consistently throughout the docs and the app.
