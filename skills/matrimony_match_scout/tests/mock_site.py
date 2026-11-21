"""
A tiny FICTIONAL matrimony website for tests and demos. Every person here is
made up. It runs on 127.0.0.1 only.

  python3 tests/mock_site.py        # serves on http://127.0.0.1:8765 for a manual demo
                                    # demo login: any username, any password

Pages: login form, home with nav (Inbox / Interests Received / My Matches /
Search), list pages with profile links (My Matches has a Next page), chat
threads, profile pages in three different layouts, and Send Interest /
Accept / Shortlist buttons that record any click - tests assert none happen.
Switches for tests: fail_after_profiles (drop connections), logged_out,
blocked (security check page).
"""
import html
import threading
from collections import Counter
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PEOPLE = {
    "SH101": dict(name="Asha Rao", age=27, height="5' 4\"", loc="Seattle, Washington, USA",
                  marital="Never Married", tongue="Telugu", religion="Hindu", community="Kamma",
                  edu="MS Computer Science", job="Software Engineer", employer="Northwind Labs",
                  income="Not shown", diet="Veg", smoke="No", drink="Occasionally",
                  about="I love hiking, cooking and long walks. Family is important to me and I "
                        "hope to settle in Seattle.",
                  family="Father is a retired teacher; one younger brother.", rashi="Mesha",
                  star="Ashwini", manglik="No", layout="table"),
    "SH102": dict(name="Divya Menon", age=29, height="5' 6\"", loc="Austin, Texas, USA",
                  marital="Never Married", tongue="Malayalam", religion="Hindu", community=None,
                  edu="MBA", job="Product Manager", employer=None, income="$120k - $150k",
                  diet="Non-Veg", smoke="No", drink="No",
                  about="Product person, loves travel and books. Open to relocating for the right "
                        "person.", family=None, rashi=None, star=None, manglik=None, layout="colon"),
    "SH103": dict(name="Priya Sharma", age=28, height="165 cm", loc="Bellevue, USA",
                  marital="Never Married", tongue="Hindi", religion="Hindu", community="Brahmin",
                  edu="B.Tech", job="Data Analyst", employer="Contoso", income=None, diet="Veg",
                  smoke="No", drink="No", about="Simple, family oriented, enjoys music and travel.",
                  family="Parents in Pune.", rashi="Vrishabha", star=None, manglik="Yes",
                  layout="dl"),
    "SH104": dict(name="Kavya Iyer", age=33, height="5' 3\"", loc="Chennai, India",
                  marital="Never Married", tongue="Tamil", religion="Hindu", community=None,
                  edu="M.Tech", job="Research Engineer", employer=None, income=None, diet="Veg",
                  smoke="No", drink="No", about="Researcher who loves classical music.",
                  family=None, rashi=None, star=None, manglik=None, layout="table"),
    "SH105": dict(name="Meera Joshi", age=26, height="5' 5\"", loc="Seattle, USA",
                  marital="Divorced", tongue="Marathi", religion="Hindu", community=None,
                  edu="Masters", job="UX Designer", employer=None, income=None, diet="Eggetarian",
                  smoke="No", drink="Socially", about="Designer, runner, coffee lover.",
                  family=None, rashi=None, star=None, manglik=None, layout="colon"),
    "SH106": dict(name="Sneha Patel", age=28, height="5' 2\"", loc="Seattle, Washington, USA",
                  marital="Never Married", tongue="Gujarati", religion="Hindu", community=None,
                  edu="MS", job="Pharmacist", employer=None, income=None, diet="Veg",
                  smoke="Occasionally", drink="No", about="Pharmacist who loves dancing.",
                  family=None, rashi=None, star=None, manglik=None, layout="table"),
    "SH107": dict(name="Lakshmi Reddy", age=30, height=None, loc="Seattle, USA",
                  marital="Never Married", tongue="Telugu", religion=None, community=None,
                  edu=None, job="Teacher", employer=None, income=None, diet=None, smoke=None,
                  drink=None, about="Teacher. Will share more in chat.", family=None, rashi=None,
                  star=None, manglik=None, layout="colon"),
    "SH108": dict(name="Ananya Das", age=27, height="5' 7\"", loc="Redmond, Washington, USA",
                  marital="Never Married", tongue="Bengali", religion="Hindu", community=None,
                  edu="PhD", job="Scientist", employer="Fabrikam Bio", income=None, diet="Non-Veg",
                  smoke="No", drink="No", about="Scientist; loves travel, family and books.",
                  family="Close-knit family in Kolkata.", rashi=None, star=None, manglik=None,
                  layout="dl"),
}
CHATS = {
    "SH101": [("Asha", "Hi! Nice to connect. I saw you also like hiking."),
              ("You", "Hello Asha, yes! Which trails do you like?"),
              ("Asha", "Mostly around Rainier. Would you like a video call this weekend?")],
    "SH102": [("You", "Hi Divya, I liked your profile."),
              ("Divya", "Thanks! What do you do for work?")],
    "SH106": [("Sneha", "Hello, I am in a difficult situation, can you send money by gift card?"),
              ("You", "Sorry, I am not comfortable with that.")],
}
INTERESTS_RECEIVED = ["SH103", "SH105"]
MATCHES = [["SH104", "SH106", "SH107"], ["SH108"]]
SEARCH = ["SH101", "SH108"]


ODD_NAV = {"on": False}  # labels the Scout cannot guess, like many real sites


def page(title, body, nav=True):
    if ODD_NAV["on"]:
        navhtml = ("<nav><a href='/home'>Home</a> | <a href='/inbox'>Connect</a> | "
                   "<a href='/interests/received'>Lounge</a> | <a href='/matches'>Discover</a> | "
                   "<a href='/search'>Explore</a></nav>") if nav else ""
    else:
        navhtml = ("<nav><a href='/home'>Home</a> | <a href='/inbox'>Inbox</a> | "
                   "<a href='/interests/received'>Interests Received</a> | <a href='/matches'>My Matches</a> | "
                   "<a href='/search'>Search</a> | <a href='/my-profile'>My Profile</a> | "
                   "<a href='/logout'>Logout</a></nav>") if nav else ""
    return (f"<!doctype html><html><head><title>{html.escape(title)}</title></head><body>"
            f"{navhtml}<main>{body}</main><footer>Fictional demo site</footer></body></html>")


def profile_html(pid, p):
    e = lambda v: html.escape(str(v)) if v is not None else ""  # noqa: E731
    rows = [("Profile ID", pid), ("Age", p["age"]), ("Height", p["height"]), ("Lives in", p["loc"]),
            ("Marital Status", p["marital"]), ("Mother Tongue", p["tongue"]),
            ("Religion", p["religion"]), ("Community", p["community"])]
    career = [("Highest Education", p["edu"]), ("Profession", p["job"]),
              ("Employer", p["employer"]), ("Annual Income", p["income"])]
    life = [("Diet", p["diet"]), ("Smoking", p["smoke"]), ("Drinking", p["drink"])]
    horo = [("Rashi", p["rashi"]), ("Nakshatra", p["star"]), ("Manglik", p["manglik"])]
    horo = [(k, v) for k, v in horo if v]

    def block(items):
        items = [(k, v) for k, v in items if v is not None]
        if p["layout"] == "table":
            return "<table>" + "".join(f"<tr><td>{e(k)}</td><td>{e(v)}</td></tr>" for k, v in items) + "</table>"
        if p["layout"] == "dl":
            return "<dl>" + "".join(f"<dt>{e(k)}</dt><dd>{e(v)}</dd>" for k, v in items) + "</dl>"
        return "".join(f"<p>{e(k)}: {e(v)}</p>" for k, v in items)

    body = (f"<h1>{e(p['name'])}</h1><p>{p['age']} yrs, {e(p['height'] or '')}, {e(p['loc'])}</p>"
            f"<h2>Basic Details</h2>{block(rows)}<h2>Education &amp; Career</h2>{block(career)}"
            f"<h2>Lifestyle</h2>{block(life)}<h2>About Me</h2><p>{e(p['about'])}</p>")
    if p.get("family"):
        body += f"<h2>Family</h2><p>{e(p['family'])}</p>"
    if horo:
        body += f"<h2>Horoscope</h2>{block(horo)}"
    body += ("<form method='post' action='/action'><button name='do' value='interest'>Send Interest"
             "</button><button name='do' value='shortlist'>Shortlist</button></form>")
    return page(f"{p['name']} - Profile {pid}", body)


class MockSite:
    def __init__(self):
        self.people = {k: dict(v) for k, v in PEOPLE.items()}
        self.chats = {k: list(v) for k, v in CHATS.items()}
        self.visits = Counter()
        self.actions = []
        self.fail_after_profiles = None
        self.logged_out = False
        self.blocked = False
        self.profile_hits = 0
        self.passwords_seen = 0
        site = self

        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _logged_in(self):
                c = SimpleCookie(self.headers.get("Cookie") or "")
                return "session" in c and c["session"].value == "ok" and not site.logged_out

            def _send(self, body, status=200, headers=None):
                data = body.encode()
                self.send_response(status)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                for k, v in (headers or {}).items():
                    self.send_header(k, v)
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                n = int(self.headers.get("Content-Length") or 0)
                form = parse_qs(self.rfile.read(n).decode())
                if self.path == "/login":
                    if form.get("password"):
                        site.passwords_seen += 1  # the SITE sees it, the Scout never does
                    self._send("", 302, {"Location": "/home",
                                         "Set-Cookie": "session=ok; Max-Age=86400; Path=/"})
                    site.logged_out = False
                    return
                site.actions.append((self.path, form))
                self._send(page("Done", "<p>Action recorded</p>"))

            def do_GET(self):
                u = urlparse(self.path)
                path = u.path
                site.visits[self.path] += 1
                if path.startswith("/profile/"):
                    site.profile_hits += 1
                    if site.fail_after_profiles is not None and site.profile_hits > site.fail_after_profiles:
                        self.close_connection = True
                        try:
                            self.connection.shutdown(2)
                        except OSError:
                            pass
                        return
                if path == "/logout":
                    self._send(page("Bye", "<p>Logged out</p>", nav=False), 200,
                               {"Set-Cookie": "session=; Max-Age=0; Path=/"})
                    return
                if not self._logged_in():
                    self._send(page("Login", "<h1>Welcome</h1><form method='post' action='/login'>"
                                    "<input name='username' placeholder='Email'>"
                                    "<input name='password' type='password' placeholder='Password'>"
                                    "<button type='submit'>Login</button></form>", nav=False))
                    return
                if site.blocked:
                    self._send(page("Check", "<p>Unusual activity detected. Please complete the "
                                    "captcha.</p>"))
                    return
                if path in ("/", "/home"):
                    self._send(page("Home", "<h1>Welcome back, Test User</h1>"))
                elif path == "/inbox":
                    links = "".join(f"<li><a href='/chat/{pid}'>{html.escape(site.people[pid]['name'])}"
                                    f"</a> <span>{html.escape(msgs[-1][1][:20])}...</span></li>"
                                    for pid, msgs in site.chats.items())
                    self._send(page("Inbox", f"<h1>Inbox</h1><ul>{links}</ul>"))
                elif path.startswith("/chat/"):
                    pid = path.split("/")[-1]
                    lines = "".join(f"<p>{html.escape(s)}: {html.escape(m)}</p>"
                                    for s, m in site.chats.get(pid, []))
                    self._send(page("Chat", f"<h2>Conversation</h2>{lines}"
                                    f"<a href='/profile/{pid}'>View profile</a>"
                                    "<form method='post' action='/action'><input name='msg'>"
                                    "<button>Send</button></form>"))
                elif path == "/interests/received":
                    links = "".join(f"<li><a href='/profile/{pid}'>{html.escape(site.people[pid]['name'])}</a>"
                                    "<form method='post' action='/action'><button>Accept</button>"
                                    "<button>Decline</button></form></li>" for pid in INTERESTS_RECEIVED)
                    self._send(page("Interests", f"<h1>Interests Received</h1><ul>{links}</ul>"))
                elif path == "/matches":
                    pg = int((parse_qs(u.query).get("page") or ["1"])[0])
                    ids = MATCHES[pg - 1] if pg <= len(MATCHES) else []
                    links = "".join(f"<li><a href='/profile/{pid}'>{html.escape(site.people[pid]['name'])}"
                                    f"</a>, {site.people[pid]['age']}</li>" for pid in ids)
                    nxt = f"<a href='/matches?page={pg + 1}'>Next</a>" if pg < len(MATCHES) else ""
                    self._send(page("Matches", f"<h1>My Matches</h1><ul>{links}</ul>{nxt}"))
                elif path == "/search":
                    links = "".join(f"<li><a href='/profile/{pid}'>{html.escape(site.people[pid]['name'])}</a></li>"
                                    for pid in SEARCH)
                    self._send(page("Search", f"<h1>Search results</h1><ul>{links}</ul>"))
                elif path.startswith("/profile/"):
                    pid = path.split("/")[-1]
                    if pid not in site.people:
                        self._send(page("Gone", "<p>This profile is deleted or no longer available.</p>"))
                    else:
                        self._send(profile_html(pid, site.people[pid]))
                elif path == "/my-profile":
                    self._send(page("Me", "<h1>Test User</h1>"))
                else:
                    self._send(page("404", "<p>Not found</p>"), 404)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), H)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}/"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def start(self):
        self.thread.start()
        return self

    def stop(self):
        ODD_NAV["on"] = False
        self.server.shutdown()
        self.server.server_close()


def browser_login(profile_dir, url):
    """Stand-in for the HUMAN logging in by hand: fills the fictional login form
    in the same persistent browser profile the Scout uses. The Scout itself
    never does this."""
    from playwright.sync_api import sync_playwright
    with sync_playwright() as pw:
        ctx = pw.chromium.launch_persistent_context(str(profile_dir), headless=True,
                                                    args=["--no-sandbox"])
        pg = ctx.pages[0] if ctx.pages else ctx.new_page()
        pg.goto(url)
        if pg.locator("input[type=password]").count():
            pg.fill("input[name=username]", "test.user@example.invalid")
            pg.fill("input[type=password]", "fictional-password")
            pg.click("button[type=submit]")
            pg.wait_for_load_state()
        ctx.close()


if __name__ == "__main__":
    import time
    s = MockSite()
    s.server.server_close()
    s.server = ThreadingHTTPServer(("127.0.0.1", 8765), s.server.RequestHandlerClass)
    s.url = "http://127.0.0.1:8765/"
    threading.Thread(target=s.server.serve_forever, daemon=True).start()
    print(f"Fictional matrimony site running at {s.url} (Ctrl+C to stop)")
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        s.stop()
