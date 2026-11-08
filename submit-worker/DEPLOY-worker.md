# Submission Worker — deploy guide

This lets students submit their CSV from the project page with **no GitHub
account and no repo access**. The Worker is the only thing that writes to the
repo, and it can **only** create or update `submissions/<team>.csv` — never
code, the leaderboard, the ground truth, or another team's file.

## Security first

- The GitHub token is **never** in the page or in any committed file. It lives
  only as a Worker secret (`wrangler secret put`), encrypted at Cloudflare.
- Generate a **fresh** fine-grained token for this — do not reuse one that has
  been pasted into chat/email, and revoke any that has. Scope it to the single
  `Programming-Challenge` repo, permission **Contents: Read and write**, nothing
  else.

## One-time setup (~15–30 min)

1. **Install Wrangler** (Cloudflare's CLI) and sign in to your Cloudflare
   account (free tier is fine):
   ```bash
   npm install -g wrangler        # or: npm i -D wrangler, then npx wrangler ...
   wrangler login
   ```

2. From this `submit-worker/` folder, **store the token as a secret**:
   ```bash
   wrangler secret put GITHUB_TOKEN
   # paste the fresh fine-grained token when prompted
   ```
   Optional — require a class/team code so only your students can submit:
   ```bash
   wrangler secret put SUBMIT_CODE      # choose any string; share it with the class
   ```

3. **Deploy:**
   ```bash
   wrangler deploy
   ```
   Wrangler prints a URL like
   `https://ser-leaderboard-submit.<your-subdomain>.workers.dev`.

4. **Point the page at it.** In `index.html`, near the bottom `<script>`:
   ```js
   const SUBMIT_ENDPOINT = "https://ser-leaderboard-submit.<your-subdomain>.workers.dev/submit";
   const REQUIRE_CODE   = false;   // set true only if you set SUBMIT_CODE above
   ```
   Commit and push `index.html`; GitHub Pages redeploys automatically.

5. **Test** with a real `<team>.csv`: it should land in `submissions/`, and the
   existing leaderboard Action rescans and updates the board within a minute or two.

## Config reference

- `wrangler.toml` holds the non-secret vars: `REPO_OWNER`, `REPO_NAME`, and
  `ALLOWED_ORIGIN` (the exact origin your page is served from — scheme + host,
  no trailing path). Update `ALLOWED_ORIGIN` if you move the page.
- The Worker re-validates every submission (columns, labels, rows, size) before
  committing, so the page's checks can't be bypassed.

## Notes

- Teams resubmit freely; each submission overwrites their own
  `submissions/<team>.csv`, and git history records every write.
- A `SUBMIT_CODE` stops random internet submissions and name-spoofing by
  outsiders; within the class it's a shared code, not per-team.
- Cost: well within Cloudflare Workers' free tier for a class-sized course.
