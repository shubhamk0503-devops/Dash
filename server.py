import json, os, re, base64, subprocess, threading, uuid, time, tempfile
from collections import Counter
from datetime import date
from urllib.parse import urlparse, parse_qs
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler

STATE = os.environ.get("STATE_FILE", "/data/state.json")
HERE = os.path.dirname(os.path.abspath(__file__))
APPS = {"airtel-iq": "Airtel-IQ", "wynk": "Wynk"}
def mk(d, va, co, zd):
    def blk(rows): return {"shared": sum(r[1] for r in rows), "closed": sum(r[2] for r in rows), "owners": {r[0]: {"shared": r[1], "closed": r[2]} for r in rows}}
    return {"date": d, "image_va": blk(va), "compliance": blk(co), "zero_day": dict(zd)}
W_VA0 = [("Aakash",43657,5513),("Abhinav",51219,8686),("Gautam Gokul",40753,2884),("Mohit Goyal",51500,5893),("Nisha",58022,7577),("Satya Mishra",15479,2636),("Shivani",55327,13802),("Shubham Kumar",13696,654),("Vinod Kumar",57928,3994),("Srinivasulu Aakurathi",1104,571)]
W_VA1 = [("Aakash",43657,5713),("Abhinav",51219,9615),("Gautam Gokul",40753,4660),("Mohit Goyal",51500,7105),("Nisha",58022,6922),("Satya Mishra",15479,2928),("Shivani",55327,13853),("Shubham Kumar",13696,886),("Vinod Kumar",57928,4459),("Srinivasulu Aakurathi",1104,544)]
W_CO0 = [("Aakash",731,24),("Abhinav",1023,289),("Gautam Gokul",88,0),("Kaushik Singh",4,0),("Mohit Goyal",1205,15),("Nisha",1653,4),("Satya Mishra",603,1),("Shiv",2841,1573),("Shivani",3224,695),("Srinivasulu Aakurathi",111,0),("Vinod",2234,506),("Yash",276,4)]
W_CO1 = [("Aakash",731,28),("Abhinav",1023,353),("Gautam Gokul",88,1),("Kaushik Singh",4,0),("Mohit Goyal",1205,22),("Nisha",1653,4),("Satya Mishra",603,1),("Shiv",2841,1579),("Shivani",3224,703),("Srinivasulu Aakurathi",111,0),("Vinod",2234,506),("Yash",276,16)]
W_ZD0 = {"PostgreSQL":63,"Iranian Muddy Water":2,"LiteLLM":5,"Http2":100,"Account_Takeover":3,"Guardrails":10,"Image_Decoding":509,"Libssh2":27,"Copy_Escape":6,"SSRF":4,"Curl":359}
W_ZD1 = {"PostgreSQL":51,"LiteLLM":5,"Http2":50,"Account_Takeover":3,"Guardrails":10,"Image_Decoding":30,"Libssh2":7,"Copy_Escape":6,"SSRF":4,"Curl":341,"Brocolli2Shell":12692}
SEED = {"airtel-iq": {"lob": "Airtel-IQ", "owner": "Himank Jain", "snapshots": [
 {"date": "2026-10-27", "image_va": {"shared": 80539, "closed": 22837}, "compliance": {"shared": 812, "closed": 39},
  "zero_day": {"PostgreSQL": 111, "Libssh2": 6, "Curl": 22}},
 {"date": "2026-11-03", "image_va": {"shared": 80539, "closed": 28723}, "compliance": {"shared": 812, "closed": 68},
  "zero_day": {"PostgreSQL": 93, "Libssh2": 5, "Curl": 19, "Brocolli2Shell": 195}}]},
 "wynk": {"lob": "Wynk", "owner": "", "snapshots": [mk("2026-10-27", W_VA0, W_CO0, W_ZD0), mk("2026-11-03", W_VA1, W_CO1, W_ZD1)]}}

def load():
    try: st = json.load(open(STATE))
    except Exception: st = {}
    if "snapshots" in st: st = {"airtel-iq": st}  # older single-app file
    for k in list(st):
        if isinstance(st[k], dict) and "sheet" in st[k]:
            sh = st[k].pop("sheet"); st[k].setdefault("sheets", {})[(sh.get("uploaded") or time.strftime("%Y-%m-%d"))[:10]] = sh
    changed = False
    for k, v in SEED.items():
        st.setdefault(k, json.loads(json.dumps(v)))
        if not st[k].get("seeded"):  # load the starter data once, only into an empty dashboard
            if not st[k]["snapshots"]: st[k]["snapshots"] = json.loads(json.dumps(v["snapshots"]))
            st[k]["seeded"] = True; changed = True
    if changed:
        try: save(st)
        except Exception: pass
    return st
def save(st):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    json.dump(st, open(STATE, "w"), indent=1)
def rd(n): return open(os.path.join(HERE, n), encoding="utf-8").read()
def short(x): return f"{x.day} {x.strftime('%b')}"

def render(slug, f=None, t=None):
    s = load()[slug]; sn = sorted(s["snapshots"], key=lambda x: x["date"])
    if len(sn) < 2:
        return (f"<body style='font:16px sans-serif;padding:30px'><h1>{s['lob']}: OND Tracker dashboard</h1>"
                f"<p>{len(sn)} of 2 dates saved. Add {2 - len(sn)} more to see a comparison.</p>"
                f"<p><a href='/{slug}/update'>Add tracker screenshots</a> &nbsp; <a href='/'>All dashboards</a></p></body>")
    by = {x["date"]: x for x in sn}
    if f in by and t in by and f != t: p, c = sorted((by[f], by[t]), key=lambda x: x["date"])
    else: p, c = sn[-2], sn[-1]
    pd, cd = date.fromisoformat(p["date"]), date.fromisoformat(c["date"])
    names = sorted(dict.fromkeys(list(p["zero_day"]) + list(c["zero_day"])), key=lambda n: -c["zero_day"].get(n, 0))
    def own(k):
        co_, po_ = c[k].get("owners") or {}, p[k].get("owners") or {}
        return [[n, v["shared"], po_.get(n, {}).get("closed", 0), v["closed"]] for n, v in co_.items()] if len(co_) > 1 else []
    data = {"va": {"name": "Image VA", "shared": c["image_va"]["shared"], "a": p["image_va"]["closed"], "b": c["image_va"]["closed"]},
            "co": {"name": "Compliance", "shared": c["compliance"]["shared"], "a": p["compliance"]["closed"], "b": c["compliance"]["closed"]},
            "zd": [[n, p["zero_day"].get(n, 0), c["zero_day"].get(n, 0)] for n in names],
            "ow": {"va": own("image_va"), "co": own("compliance")},
            "hist": [{"d": x["date"], "va": [x["image_va"]["shared"], x["image_va"]["closed"]], "co": [x["compliance"]["shared"], x["compliance"]["closed"]],
                      "zd": x["zero_day"], "vow": {n: [v["shared"], v["closed"]] for n, v in (x["image_va"].get("owners") or {}).items()},
                      "cow": {n: [v["shared"], v["closed"]] for n, v in (x["compliance"].get("owners") or {}).items()}} for x in sn]}
    h = rd("template.html").replace("__DATA__", json.dumps(data))
    for a, b in (("27 Oct 2026", "@@P1"), ("3 Nov 2026", "@@C1"), ("27 Oct", "@@P2"), ("3 Nov", "@@C2")): h = h.replace(a, b)
    for a, b in (("@@P1", f"{short(pd)} {pd.year}"), ("@@C1", f"{short(cd)} {cd.year}"), ("@@P2", short(pd)), ("@@C2", short(cd))): h = h.replace(a, b)
    d = (cd - pd).days
    h = h.replace("(7 days)", f"({d} days)").replace("in 7 days", f"in {d} days")
    h = h.replace("App owner: Himank Jain &nbsp;|&nbsp; ", f"App owner: {s['owner']} &nbsp;|&nbsp; " if s["owner"] else "")
    h = h.replace("Airtel-IQ", s["lob"])
    opt = lambda sel: "".join(f'<option value="{x["date"]}"{" selected" if x["date"] == sel else ""}>{short(date.fromisoformat(x["date"]))} {x["date"][:4]}</option>' for x in sn)
    nav = "".join(f'<a href="/{k}"{" style=font-weight:700" if k == slug else ""}>{v}</a> &nbsp; ' for k, v in APPS.items())
    bar = (f'<form method="get" action="/{slug}" class="card" style="margin-bottom:14px;display:flex;gap:10px;flex-wrap:wrap;align-items:center">'
           f'{nav}| <b>Compare</b><select name="from">{opt(p["date"])}</select> with <select name="to">{opt(c["date"])}</select>'
           f'<button style="padding:5px 12px">Show</button> <a href="/{slug}">Latest two</a> &nbsp; <a href="/{slug}/update">Add new data</a> &nbsp; <a href="/{slug}/sheet">Sheet view</a> &nbsp; <a href="/{slug}/zeroday">Zero-day view</a></form>')
    h = h.replace('<div class="row" id="kpis">', bar + '<div class="row" id="kpis">', 1)
    return h.replace("</main>", f'<p class="note"><a href="/{slug}/update">Add a new tracker screenshot</a></p></main>')

def ocr(data_url):
    raw = base64.b64decode(data_url.split(",", 1)[1])
    try:
        r = subprocess.run(["tesseract", "stdin", "stdout", "--psm", "6"], input=raw, capture_output=True, timeout=60)
    except FileNotFoundError:
        raise RuntimeError("tesseract is not installed on the server. Type the numbers by hand below.")
    return r.stdout.decode("utf-8", "ignore")

def parse_table(text, lob=""):
    owners = {}
    for l in text.splitlines():
        l = l.replace("|", " ").strip()
        if lob: l = re.sub("^" + re.escape(lob) + r"\s+", "", l, flags=re.I)
        m = re.match(r"^([A-Za-z][A-Za-z .'\-]*?)\s+([\d,]+)\s+([\d,]+)\s+(\d+(?:\.\d+)?)\s*$", l)
        if m:
            sh, cl, pc = int(m.group(2).replace(",", "")), int(m.group(3).replace(",", "")), float(m.group(4))
            if cl <= sh and (sh == 0 or abs(cl / sh * 100 - pc) < 0.2): owners[m.group(1).strip()] = {"shared": sh, "closed": cl}
    if len(owners) > 1:
        return {"shared": sum(v["shared"] for v in owners.values()), "closed": sum(v["closed"] for v in owners.values()), "owners": owners}
    return parse_table_total(text)

def parse_table_total(text):
    rows = [re.findall(r"\d+(?:\.\d+)?", l.replace(",", "")) for l in text.splitlines()]
    for ns in rows:  # best: Shared, Closed, Closure% where closed/shared matches the percentage
        for i in range(len(ns) - 2):
            s_, c_, p_ = float(ns[i]), float(ns[i + 1]), float(ns[i + 2])
            if s_ > 0 and c_ <= s_ and abs(c_ / s_ * 100 - p_) < 0.2: return {"shared": int(s_), "closed": int(c_)}
    for ns in rows:
        ints = [int(x) for x in ns if "." not in x]
        if len(ints) >= 2 and ints[-2] >= ints[-1] > 0: return {"shared": ints[-2], "closed": ints[-1]}
    raise ValueError("Could not find Shared and Closed numbers in the screenshot")

def parse_zero(text, lob, owner):
    out = {}
    for l in text.splitlines():
        pat = "|".join(re.escape(w) for w in (lob, owner) if w)
        l = re.sub(pat, " ", l.replace("|", " "), flags=re.I).strip() if pat else l.replace("|", " ").strip()
        m = re.match(r"^\W*([A-Za-z][A-Za-z0-9_.\- ]*?)\s+(\d+)\s*$", l)
        if m and m.group(1).strip().lower() not in ("lob", "zero-day", "zero day", "current", "zeroday"):
            out[m.group(1).strip()] = int(m.group(2))
    if not out: raise ValueError("Could not find any zero-day rows in the screenshot")
    return out

def extract(imgs, lob, owner):
    res = {"date": "", "image_va": {"shared": 0, "closed": 0}, "compliance": {"shared": 0, "closed": 0}, "zero_day": {}}
    errs = []
    for key, name in (("va", "image_va"), ("co", "compliance")):
        if imgs.get(key):
            try: res[name] = parse_table(ocr(imgs[key]), lob)
            except Exception as e: errs.append(f"{name}: {e}")
    if imgs.get("zd"):
        try: res["zero_day"] = parse_zero(ocr(imgs["zd"]), lob, owner)
        except Exception as e: errs.append(f"zero_day: {e}")
    if errs: res["_warnings"] = errs
    return res

def check(x):
    date.fromisoformat(x["date"])
    for k in ("image_va", "compliance"):
        for f in ("shared", "closed"): x[k][f] = int(x[k][f])
        x[k]["owners"] = {n: {"shared": int(v["shared"]), "closed": int(v["closed"])} for n, v in (x[k].get("owners") or {}).items()} or None
        if x[k]["owners"] is None: del x[k]["owners"]
    x["zero_day"] = {str(k): int(v) for k, v in x["zero_day"].items()}
    return x


JOBS, LOCK = {}, threading.Lock()
def find_col(hdr, names):
    for n in names:
        idx = [i for i, h in enumerate(hdr) if h == n]
        if idx: return idx[-1]
    return None

def aggregate_sheet(path, job):
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True); ws = wb.worksheets[0]
    it = ws.iter_rows(values_only=True)
    hdr = [str(h).strip() if h is not None else "" for h in next(it)]
    cols = {"cluster": find_col(hdr, ["Clusters", "Cluster"]), "owner": find_col(hdr, ["App Owners", "App Owner", "Owner"]),
            "sev": find_col(hdr, ["Severity"]), "aging": find_col(hdr, ["Aging Status"]),
            "status": find_col(hdr, ["Status.1", "Tracker Status", "Status"])}
    missing = [k for k in ("cluster", "owner", "status") if cols[k] is None]
    if missing: raise ValueError("Columns not found for: " + ", ".join(missing) + ". Headers seen: " + ", ".join(h for h in hdr if h))
    g = lambda r, k: (str(r[cols[k]]).strip() if cols[k] is not None and cols[k] < len(r) and r[cols[k]] not in (None, "") else "(blank)")
    cnt, n = Counter(), 0
    for r in it:
        if r is None or all(v is None for v in r): continue
        cnt[(g(r, "cluster"), g(r, "owner"), g(r, "sev"), g(r, "aging"), g(r, "status"))] += 1
        n += 1
        if n % 20000 == 0: job["progress"] = n
    wb.close()
    return {"rows": [list(k) + [v] for k, v in cnt.items()], "total": n, "columns": {k: (hdr[v] if v is not None else None) for k, v in cols.items()}}


ZD_DIR = os.path.join(os.path.dirname(STATE), "zd")
ZD_FIELDS = [("cve", ["Name"]), ("sev", ["Severity"]), ("score", ["Score"]), ("epss", ["Exploitation Probability (EPSS)"]),
 ("exp", ["HasExploit"]), ("kev", ["HasCisaKevExploit"]), ("first", ["FirstDetected"]), ("fix", ["Remediation"]), ("pkg", ["DetailedName"]),
 ("ver", ["Version"]), ("fixed", ["FixedVersion"]), ("det", ["DetectionMethod"]), ("asset", ["AssetName"]), ("aid", ["AssetID"]),
 ("atype", ["AssetType"]), ("region", ["AssetRegion"]), ("sub", ["SubscriptionName", "SubscriptionExternalId"]),
 ("cluster", ["Clusters"]), ("ns", ["Namespaces"]), ("proj", ["Projects"])]
ZD_NUM, ZD_BOOL, ZD_NONE = {"score", "epss"}, {"exp", "kev"}, {"cluster", "ns"}

def zd_path(app, day): return os.path.join(ZD_DIR, f"{app}_{day}.json")

def aggregate_zd(path, job, app, day):
    from openpyxl import load_workbook
    wb = load_workbook(path, read_only=True, data_only=True)
    cols = ["cat"] + [f for f, _ in ZD_FIELDS]
    tabs = {c: {} for c in cols if c not in ZD_NUM and c not in ZD_BOOL}
    rows, cats, n = [], {}, 0
    def code(c, v):
        t = tabs[c]
        if v not in t: t[v] = len(t)
        return t[v]
    for ws in wb.worksheets:
        it = ws.iter_rows(values_only=True)
        try: hdr = [str(h).strip() if h is not None else "" for h in next(it)]
        except StopIteration: continue
        if "Name" not in hdr or "Severity" not in hdr: continue
        idx = {f: [i for nm in names for i, h in enumerate(hdr) if h == nm][::-1] for f, names in ZD_FIELDS}
        cat = ws.title.strip(); c = cats.setdefault(cat, {"n": 0, "Critical": 0, "High": 0, "Medium": 0, "Low": 0, "kev": 0, "exp": 0})
        for r in it:
            if r is None or all(v is None for v in r): continue
            row = [code("cat", cat)]
            for f, _ in ZD_FIELDS:
                v = None
                for i in idx[f]:
                    if i < len(r) and r[i] not in (None, ""): v = r[i]; break
                if f in ZD_NUM:
                    try: row.append(round(float(v), 2))
                    except (TypeError, ValueError): row.append(0)
                elif f in ZD_BOOL: row.append(1 if str(v).strip().lower() in ("true", "1", "yes") else 0)
                else:
                    sv = str(v).strip() if v is not None else ""
                    if sv.upper() in ("#N/A", "N/A", "NAN", "NONE", "NULL"): sv = ""
                    if f == "first": sv = sv[:10]
                    row.append(code(f, sv or ("(none)" if f in ZD_NONE else "(blank)")))
            rows.append(row); n += 1
            sev = str(r[idx["sev"][0]]).strip() if idx["sev"] and idx["sev"][0] < len(r) and r[idx["sev"][0]] else ""
            c["n"] += 1
            if sev in c: c[sev] += 1
            c["kev"] += row[cols.index("kev")]; c["exp"] += row[cols.index("exp")]
            if n % 2000 == 0: job["progress"] = n
    wb.close()
    if not rows: raise ValueError("No zero-day sheets found (each sheet needs Name and Severity columns)")
    os.makedirs(ZD_DIR, exist_ok=True)
    out = {"cols": cols, "tab": {c: list(t) for c, t in tabs.items()}, "rows": rows}
    with open(zd_path(app, day), "w") as f: json.dump(out, f, separators=(",", ":"))
    aid, cl = set(), set()
    for r in rows: aid.add(r[cols.index("aid")]); cl.add(r[cols.index("cluster")])
    return {"total": n, "cats": cats, "assets": len(aid), "clusters": len([x for x in out["tab"]["cluster"] if x != "(none)"])}

def run_job(jid, app, path, fname, day, kind="sheet"):
    job = JOBS[jid]
    try:
        res = aggregate_zd(path, job, app, day) if kind == "zd" else aggregate_sheet(path, job)
        res.update({"filename": fname, "uploaded": time.strftime("%Y-%m-%d %H:%M")})
        with LOCK:
            st = load(); st[app].setdefault("zd" if kind == "zd" else "sheets", {})[day] = res; save(st)
        job["status"] = "done"
    except Exception as e:
        job["status"] = "error"; job["error"] = str(e)
    finally:
        try: os.remove(path)
        except OSError: pass

HOME = """<!DOCTYPE html><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1"><title>OND Tracker dashboards</title>
<body style="font:16px 'Segoe UI',sans-serif;max-width:640px;margin:40px auto;padding:0 16px"><h1>OND Tracker dashboards</h1>%s</body>"""

class H(BaseHTTPRequestHandler):
    def send(self, body, ct="text/html; charset=utf-8", code=200):
        b = body.encode(); self.send_response(code); self.send_header("Content-Type", ct)
        self.send_header("Content-Length", str(len(b))); self.end_headers(); self.wfile.write(b)
    def do_GET(self):
        u = urlparse(self.path); q = parse_qs(u.query); parts = [x for x in u.path.split("/") if x]
        if u.path == "/api/job": return self.send(json.dumps(JOBS.get(q.get("id", [""])[0], {"status": "error", "error": "Unknown job"})), "application/json")
        if u.path == "/api/zd":
            app, day = q.get("app", [""])[0], q.get("date", [""])[0]
            try:
                if app not in APPS: raise ValueError
                date.fromisoformat(day); return self.send(open(zd_path(app, day), encoding="utf-8").read(), "application/json")
            except Exception: return self.send("{}", "application/json", 404)
        if u.path == "/api/state": return self.send(json.dumps(load().get(q.get("app", [""])[0], {})), "application/json")
        if not parts:
            n = lambda k: len(load()[k]["snapshots"])
            return self.send(HOME % "".join(f'<p><a href="/{k}"><b>{v}: OND Tracker dashboard</b></a> ({n(k)} dates saved)</p>' for k, v in APPS.items()))
        if parts[0] not in APPS: return self.send("Not found", code=404)
        if parts[1:] == ["sheet"]:
            sh = load()[parts[0]].get("sheets", {})
            return self.send(rd("sheet.html").replace("__APP__", parts[0]).replace("__NAME__", APPS[parts[0]]).replace("__SHEETS__", json.dumps(sh)))
        if parts[1:] == ["zeroday"]:
            zs = load()[parts[0]].get("zd", {})
            return self.send(rd("zeroday.html").replace("__APP__", parts[0]).replace("__NAME__", APPS[parts[0]]).replace("__SUMS__", json.dumps(zs)))
        if parts[1:] == ["update"]: return self.send(rd("update.html").replace("__APP__", parts[0]).replace("__NAME__", APPS[parts[0]]))
        self.send(render(parts[0], q.get("from", [None])[0], q.get("to", [None])[0]))
    def sheet_upload(self):
        q = parse_qs(urlparse(self.path).query); app = q.get("app", [""])[0]
        if app not in APPS: raise ValueError("Unknown app")
        n = int(self.headers["Content-Length"]); fd, path = tempfile.mkstemp(suffix=".xlsx")
        with os.fdopen(fd, "wb") as f:
            while n > 0:
                chunk = self.rfile.read(min(1 << 20, n))
                if not chunk: break
                f.write(chunk); n -= len(chunk)
        day = q.get("date", [""])[0] or time.strftime("%Y-%m-%d"); date.fromisoformat(day)
        jid = uuid.uuid4().hex[:10]; JOBS[jid] = {"status": "running", "progress": 0}
        threading.Thread(target=run_job, args=(jid, app, path, q.get("name", ["sheet.xlsx"])[0], day, "zd" if self.path.startswith("/api/zd") else "sheet"), daemon=True).start()
        self.send(json.dumps({"job": jid}), "application/json")
    def do_POST(self):
        try:
            if self.path.startswith("/api/sheet") or self.path.startswith("/api/zd?"): return self.sheet_upload()
            b = json.loads(self.rfile.read(int(self.headers["Content-Length"]))); app = b.get("app")
            if app not in APPS: raise ValueError("Unknown app")
            st = load(); a = st[app]
            if self.path == "/api/extract": out = extract(b["images"], a["lob"], a.get("owner", ""))
            elif self.path == "/api/save":
                x = check({k: v for k, v in b["data"].items() if not k.startswith("_")})
                a["owner"] = b.get("owner", a["owner"]).strip()
                a["snapshots"] = [q for q in a["snapshots"] if q["date"] != x["date"]] + [x]; save(st); out = {"ok": True}
            elif self.path == "/api/zddelete":
                a.get("zd", {}).pop(b["date"], None); save(st)
                try: os.remove(zd_path(app, b["date"]))
                except OSError: pass
                out = {"ok": True}
            elif self.path == "/api/sheetdelete":
                a.get("sheets", {}).pop(b["date"], None); save(st); out = {"ok": True}
            elif self.path == "/api/delete":
                a["snapshots"] = [q for q in a["snapshots"] if q["date"] != b["date"]]; save(st); out = {"ok": True}
            else: return self.send("{}", "application/json", 404)
            self.send(json.dumps(out), "application/json")
        except Exception as e: self.send(json.dumps({"error": str(e)}), "application/json", 400)

if __name__ == "__main__":
    ThreadingHTTPServer(("0.0.0.0", int(os.environ.get("PORT", 8080))), H).serve_forever()
