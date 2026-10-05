// Invented sample people, posts, reactions, stories and messages for a fresh Darviq-Buzz stack, so
// demo/traffic.mjs has accounts to sign in with and the dashboards have realistic activity.
// Written straight to the backend services (the same calls web-bff makes, with the
// X-User-Username header it asserts after sign-in). Everything here is made up.
//
//   node demo/seed-buzz.mjs        (once, after Buzz's docker compose up)
const PASSWORD = "Sample-Pass1!";
const URL = { user: 5001, graph: 5002, post: 5003, engage: 5004, story: 5005, msg: 5006 };
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function call(svc, method, path, as, body) {
  const res = await fetch(`http://localhost:${URL[svc]}${path}`, {
    method,
    headers: { "Content-Type": "application/json", ...(as ? { "X-User-Username": as } : {}) },
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status >= 400 && res.status !== 409) throw new Error(`${method} ${svc}${path} -> ${res.status} ${await res.text()}`);
  return res.status === 204 ? null : res.json().catch(() => null);
}

const PEOPLE = [
  ["arjun_dev", { bio: "Backend engineer. Chai, cricket and Kubernetes.", work: "Software engineer", current_city: "Bengaluru", hometown: "Mysuru" }],
  ["meera_s", { bio: "Product designer who sketches on trains.", work: "Product designer", current_city: "Mumbai", hometown: "Pune" }],
  ["kabir_writes", { bio: "Writing a novel, one chapter a month.", work: "Writer", current_city: "Delhi" }],
  ["ananya_travels", { bio: "Weekends in the hills, weekdays in spreadsheets.", work: "Analyst", current_city: "Hyderabad" }],
  ["rohan_fit", { bio: "Coach. Running clubs every Sunday at 6.", work: "Fitness coach", current_city: "Bengaluru" }],
];
const BUSINESS = ["priyas_bakes", { bio: "Small-batch sourdough and Mysore pak. Orders open Thursday to Sunday.", current_city: "Bengaluru" }];

(async () => {
  for (const [u] of PEOPLE) await call("user", "POST", "/auth/register", null, { username: u, password: PASSWORD, account_type: "personal" });
  await call("user", "POST", "/auth/register", null, {
    username: BUSINESS[0], password: PASSWORD, account_type: "business",
    business_category: "Local Business", business_phone: "+91 90000 12345", business_address: "Indiranagar, Bengaluru",
  });
  for (const [u, profile] of [...PEOPLE, BUSINESS]) await call("user", "PUT", `/users/${u}`, u, profile);

  const all = [...PEOPLE.map((p) => p[0]), BUSINESS[0]];
  for (const a of all) for (const b of all) if (a !== b) await call("graph", "POST", `/follow/${b}`, a);
  for (const [a, b] of [["meera_s", "arjun_dev"], ["rohan_fit", "arjun_dev"], ["arjun_dev", "ananya_travels"]]) {
    await call("graph", "POST", `/friends/${b}/request`, a);
    await call("graph", "POST", `/friends/${a}/accept`, b);
  }
  await call("graph", "POST", "/friends/arjun_dev/request", "kabir_writes"); // left pending: shows a friend request

  const posts = {};
  const post = async (key, user, content) => {
    posts[key] = await call("post", "POST", "/posts", user, { content, image_url: null });
    await sleep(1100); // distinct timestamps, newest last
  };
  await post("run", "rohan_fit", "Sunday 6 am run at Cubbon Park: 42 people, two first-timers finished 5 km. Proud of everyone. #running #bengaluru");
  await post("bake", "priyas_bakes", "Fresh sourdough and Mysore pak this weekend. Pre-order by Friday 6 pm and pick up in Indiranagar. #smallbusiness #baking");
  await post("trip", "ananya_travels", "Three days in Coorg with no laptop. Coffee estates, rain, and the best pandi curry of my life. #travel #coorg");
  await post("design", "meera_s", "Redesigned our checkout from 5 steps to 2. Drop-off fell by a third in the first week. Small screens deserve better forms. #design #ux");
  await post("k8s", "arjun_dev", "Moved our feed to fan-out-on-write today. Reads went from ~400 ms to ~20 ms. Writes got busier, which is the right trade for us. #engineering");
  await post("chapter", "kabir_writes", "Chapter 9 is done. It only took three rewrites and one long walk. #writing");

  const reactions = [
    ["k8s", "meera_s", "love"], ["k8s", "rohan_fit", "wow"], ["k8s", "ananya_travels", "like"], ["k8s", "kabir_writes", "like"],
    ["design", "arjun_dev", "love"], ["design", "ananya_travels", "wow"],
    ["trip", "arjun_dev", "love"], ["trip", "meera_s", "love"], ["trip", "priyas_bakes", "like"],
    ["run", "arjun_dev", "like"], ["run", "ananya_travels", "like"],
    ["bake", "arjun_dev", "love"], ["bake", "meera_s", "haha"], ["chapter", "arjun_dev", "like"],
  ];
  for (const [key, user, type] of reactions) {
    const p = posts[key];
    await call("engage", "POST", `/posts/${p.username}/${p.url_id}/react`, user, { reaction_type: type });
  }
  const comments = [
    ["k8s", "meera_s", "20 ms! What did you do about celebrity accounts with huge follower counts?"],
    ["k8s", "arjun_dev", "Hybrid: fan-out for most, pull at read time for the few very large accounts."],
    ["trip", "arjun_dev", "Adding Coorg to the list. Which estate did you stay at?"],
    ["bake", "rohan_fit", "Saving two loaves for the running club breakfast."],
  ];
  for (const [key, user, content] of comments) {
    const p = posts[key];
    await call("engage", "POST", `/posts/${p.username}/${p.url_id}/comments`, user, { content });
  }
  await call("post", "POST", `/posts/${posts.design.username}/${posts.design.url_id}/repost`, "arjun_dev",
    { comment: "Every product team should read this." });

  await call("story", "POST", "/stories", "ananya_travels", { content: "Mist over the coffee estate at 7 am ☕", image_url: null });
  await call("story", "POST", "/stories", "rohan_fit", { content: "New 10 km route this Sunday. Who's in?", image_url: null });
  await call("story", "POST", "/stories", "priyas_bakes", { content: "Last 6 loaves of the day!", image_url: null });

  for (const [from, to, text] of [
    ["meera_s", "arjun_dev", "Are you coming to the design-engineering meetup on Thursday?"],
    ["arjun_dev", "meera_s", "Yes! I'm giving a 10-minute talk on the feed rewrite."],
    ["meera_s", "arjun_dev", "Perfect. Save me a seat near the front."],
  ]) {
    await call("msg", "POST", `/messages/${to}`, from, { content: text });
    await sleep(300);
  }
  console.log("seeded", all.length, "users,", Object.keys(posts).length, "posts");
})();
