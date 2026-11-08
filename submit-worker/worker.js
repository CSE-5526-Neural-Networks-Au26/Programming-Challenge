/**
 * SER Challenge — submission Worker
 * =================================
 * Receives { team, csv, code } from the project page, re-validates the CSV
 * server-side, and commits it to submissions/<team>.csv in the repo using a
 * repo-scoped GitHub token held ONLY as a Worker secret.
 *
 * It can ONLY create/update submissions/<slug>.csv — it cannot touch code,
 * the leaderboard, the ground truth, or any other file. Students need no
 * GitHub account and no repo access.
 *
 * Secrets (set with `wrangler secret put ...`, never in code):
 *   GITHUB_TOKEN  - fine-grained token, this repo only, Contents: Read & write
 *   SUBMIT_CODE   - (optional) a class/team code; if set, it is required
 * Vars (wrangler.toml):
 *   REPO_OWNER, REPO_NAME, ALLOWED_ORIGIN
 */

const EMOTIONS = new Set(["anger", "disgust", "fear", "happy", "neutral", "sad"]);
const MAX_BYTES = 5_000_000;

export default {
  async fetch(request, env) {
    const cors = {
      "Access-Control-Allow-Origin": env.ALLOWED_ORIGIN || "*",
      "Access-Control-Allow-Methods": "POST, OPTIONS",
      "Access-Control-Allow-Headers": "Content-Type",
      "Access-Control-Max-Age": "86400",
      "Vary": "Origin",
    };

    if (request.method === "OPTIONS") return new Response(null, { headers: cors });
    if (request.method !== "POST") return json({ ok: false, error: "Use POST." }, 405, cors);

    let body;
    try { body = await request.json(); }
    catch { return json({ ok: false, error: "Invalid request." }, 400, cors); }

    const team = String(body.team || "").trim();
    const csv  = String(body.csv || "");
    const code = String(body.code || "");

    if (env.SUBMIT_CODE && code !== env.SUBMIT_CODE)
      return json({ ok: false, error: "Invalid team code." }, 403, cors);
    if (!team)
      return json({ ok: false, error: "Missing team name." }, 400, cors);
    if (csv.length > MAX_BYTES)
      return json({ ok: false, error: "File is too large." }, 413, cors);

    // Sanitize the team name into a safe, single filename. This is the only
    // path the Worker will ever write — nothing else is reachable.
    const slug = team.toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 60);
    if (!slug) return json({ ok: false, error: "Team name has no usable characters." }, 400, cors);

    const v = validateCSV(csv);
    if (!v.ok) return json({ ok: false, error: v.error }, 422, cors);

    const owner = env.REPO_OWNER, repo = env.REPO_NAME;
    const path  = `submissions/${slug}.csv`;
    const api   = `https://api.github.com/repos/${owner}/${repo}/contents/${path}`;
    const gh = {
      "Authorization": `Bearer ${env.GITHUB_TOKEN}`,
      "Accept": "application/vnd.github+json",
      "User-Agent": "ser-leaderboard-worker",
      "X-GitHub-Api-Version": "2022-11-28",
    };

    // Look up the existing file's SHA (required to update it); 404 means new.
    let sha;
    const head = await fetch(`${api}?ref=main`, { headers: gh });
    if (head.status === 200) sha = (await head.json()).sha;
    else if (head.status === 401 || head.status === 403)
      return json({ ok: false, error: "Server is not authorized to commit. Contact the instructor." }, 502, cors);
    else if (head.status !== 404)
      return json({ ok: false, error: `GitHub read error (${head.status}).` }, 502, cors);

    const put = await fetch(api, {
      method: "PUT",
      headers: { ...gh, "Content-Type": "application/json" },
      body: JSON.stringify({
        message: `Submission: ${slug} (${v.rows} rows)`,
        content: toBase64(csv),
        branch: "main",
        ...(sha ? { sha } : {}),
      }),
    });
    if (!put.ok) return json({ ok: false, error: `Commit failed (${put.status}).` }, 502, cors);

    return json({ ok: true, team: slug.replace(/_/g, " "), rows: v.rows }, 200, cors);
  },
};

function validateCSV(text) {
  const lines = text.replace(/\r/g, "").split("\n").filter((l) => l.trim().length);
  if (!lines.length) return { ok: false, error: "File is empty." };
  const header = lines[0].split(",").map((s) => s.trim().toLowerCase());
  const ci = header.indexOf("clip_id"), pi = header.indexOf("predicted_emotion");
  if (ci < 0 || pi < 0)
    return { ok: false, error: "Header must contain clip_id and predicted_emotion." };
  const rows = lines.slice(1);
  if (!rows.length) return { ok: false, error: "No prediction rows." };
  let bad = 0;
  for (const l of rows) {
    const em = (l.split(",")[pi] || "").trim().toLowerCase();
    if (!EMOTIONS.has(em)) bad++;
  }
  if (bad) return { ok: false, error: `${bad} row(s) have invalid emotion labels.` };
  return { ok: true, rows: rows.length };
}

function toBase64(str) {
  const bytes = new TextEncoder().encode(str);
  let bin = "";
  for (const b of bytes) bin += String.fromCharCode(b);
  return btoa(bin);
}

function json(obj, status, cors) {
  return new Response(JSON.stringify(obj), {
    status,
    headers: { ...cors, "Content-Type": "application/json" },
  });
}
