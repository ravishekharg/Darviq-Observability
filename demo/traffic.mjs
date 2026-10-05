// Demo traffic for Darviq-Buzz, so the dashboards have something to show on a laptop: a handful of
// simulated people sign in and browse (feed, profiles, posts, hashtags, notifications, messages),
// with the occasional mistyped address (404). Real requests through the real stack; nothing is
// written to the metrics directly.
//
//   node demo/traffic.mjs [minutes=15] [base=http://localhost:8000]
//
// Uses the invented sample accounts created by demo/seed-buzz.mjs (run that once first).

const MINUTES = Number(process.argv[2] ?? 15);
const BASE = process.argv[3] ?? "http://localhost:8000";
const PEOPLE = ["arjun_dev", "meera_s", "kabir_writes", "ananya_travels", "rohan_fit", "priyas_bakes"];
const PAGES = ["/", "/", "/", "/discover", "/notifications", "/messages", "/friend-requests",
  "/hashtag/engineering", "/hashtag/travel", "/hashtag/running", "/hashtag/smallbusiness",
  ...PEOPLE.map((p) => `/user/${p}`), "/messages/meera_s", "/user/arjun_dev/friends"];
const MISTAKES = ["/user/nobody_here", "/hashtag/", "/post/arjun_dev/not-a-post", "/favicon.ico"];
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function session(username) {
  const jar = {};
  const cookie = () => Object.entries(jar).map(([k, v]) => `${k}=${v}`).join("; ");
  const keep = (res) => {
    for (const c of res.headers.getSetCookie?.() ?? []) {
      const [pair] = c.split(";");
      const i = pair.indexOf("=");
      jar[pair.slice(0, i)] = pair.slice(i + 1);
    }
  };
  const get = async (path) => {
    const res = await fetch(BASE + path, { headers: { cookie: cookie() }, redirect: "manual" });
    keep(res);
    await res.arrayBuffer();
    return res.status;
  };
  const page = await fetch(`${BASE}/login`);
  keep(page);
  const token = (await page.text()).match(/name="csrf_token"[^>]*value="([^"]+)"/)?.[1];
  const login = await fetch(`${BASE}/login`, {
    method: "POST", redirect: "manual",
    headers: { "Content-Type": "application/x-www-form-urlencoded", cookie: cookie() },
    body: new URLSearchParams({ csrf_token: token, username, password: "Sample-Pass1!" }),
  });
  keep(login);
  return get;
}

(async () => {
  const visitors = await Promise.all(PEOPLE.map(session));
  const end = Date.now() + MINUTES * 60_000;
  const counts = {};
  let n = 0;
  await Promise.all(visitors.map(async (get) => {
    while (Date.now() < end) {
      const path = Math.random() < 0.04 ? MISTAKES[n % MISTAKES.length] : PAGES[Math.floor(Math.random() * PAGES.length)];
      const status = await get(path).catch(() => "error");
      counts[status] = (counts[status] ?? 0) + 1;
      if (++n % 500 === 0) console.log(new Date().toISOString().slice(11, 19), n, "requests", JSON.stringify(counts));
      await sleep(400 + Math.random() * 1200);   // a person reading, not a load test
    }
  }));
  console.log("done:", n, "requests", JSON.stringify(counts));
})();
