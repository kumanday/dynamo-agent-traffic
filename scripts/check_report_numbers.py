#!/usr/bin/env python3
"""Check the numbers the report page displays against results/full/RESULTS.md.

The page draws its tables and figure titles in the browser, so the check reads the rendered page:

    python3 -m http.server 8765 --directory report &
    chrome --headless=new --virtual-time-budget=8000 --dump-dom http://127.0.0.1:8765/ > /tmp/report-dom.html
    python3 scripts/check_report_numbers.py /tmp/report-dom.html

Each displayed value must equal the RESULTS.md value to the precision the page prints.
Exit status 1 if any value differs.
"""
import html, re, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
dom = Path(sys.argv[1]).read_text()
md = (REPO / "results/full/RESULTS.md").read_text()

checks, failures = 0, []


def check(what, shown, expected, tol):
    global checks
    checks += 1
    if shown is None or abs(shown - expected) > tol + 1e-9:
        failures.append(f"{what}: page {shown}, RESULTS.md {expected}")


def num(s):
    return float(re.sub(r"[^\d.\-]", "", s))


def ms(s):
    """'8.1 s', '1,008 ms' or '697 s' -> (milliseconds, half of the printed step)."""
    v = num(s)
    if s.strip().endswith("ms"):
        return v, 0.5
    return v * 1000, 50 if "." in s else 500


def strip(cell):
    return html.unescape(re.sub(r"<[^>]+>", "", cell)).strip()


def page_table(name, trace=None):
    extra = f' data-trace="{trace}"' if trace else ""
    m = re.search(rf'<table data-table="{name}"{extra}>(.*?)</table>', dom, re.S)
    rows = re.findall(r"<tr>(.*?)</tr>", m[1], re.S)
    return [[strip(c) for c in re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", r, re.S)] for r in rows][1:]


def md_table(heading):
    """Rows of the first table under a '## heading' line."""
    block = md.split(f"## {heading}", 1)[1].split("\n## ", 1)[0]
    rows = [l for l in block.splitlines() if l.startswith("|")][2:]
    return [[c.strip().strip("`") for c in l.strip("|").split("|")] for l in rows], block


def page_text(attr, key):
    m = re.search(rf'<[^>]+data-{attr}="{key}"[^>]*>(.*?)</', dom, re.S)
    return strip(m[1]) if m else ""


# All runs and endpoint windows: every column of the two router tables.
shown = page_table("routers")
for heading, label, off in (("All leaderboard runs", "all runs", 0), ("Endpoint windows", "windows", 4)):
    rows, _ = md_table(heading)
    for i, r in enumerate(rows):
        p, who = shown[off + i], f"{label}, {r[0]}"
        check(f"{who}: prefix reuse", num(p[2]), num(r[1]), 0)
        check(f"{who}: prefill tokens", num(p[3]), num(r[2]), 0.05)
        check(f"{who}: units meeting SLA", num(p[4].split(" of ")[0]), num(r[3].split(" of ")[0]), 0)
        check(f"{who}: units", num(p[4].split(" of ")[1]), num(r[3].split(" of ")[1]), 0)
        check(f"{who}: requests meeting SLA", num(p[5]), num(r[4]), 0)
        v, tol = ms(p[6]); check(f"{who}: mean TTFT", v, num(r[5]), tol)
        v, tol = ms(p[7]); check(f"{who}: median p99 TTFT", v, num(r[6]), tol)

# Traffic sources.
shown = page_table("traffic")
for heading, p in zip(("Traffic from DeepSeek-V4.1-Flash", "Traffic from GLM-5.3-Flash (zai-org)",
                       "Traffic from Ripple-65B-Preview", "Traffic from flint"), shown):
    rows, block = md_table(heading)
    for i in range(4):
        check(f"{p[0]}: runs meeting SLA, router {i}", num(p[2 + i].split(" of ")[0]), num(rows[i][3].split(" of ")[0]), 0)
    check(f"{p[0]}: runs", num(p[1]), num(rows[0][3].split(" of ")[1]), 0)
    check(f"{p[0]}: default / affinity prefill", num(p[6]), num(rows[1][2]) / num(rows[3][2]), 0.06)
    check(f"{p[0]}: provider cached", num(p[7]), num(re.search(r"Provider cached share over the same runs: ([\d.]+)%", block)[1]), 0)
    check(f"{p[0]}: affinity prefix reuse", num(p[8]), num(rows[3][1]), 0)

# Harness versions.
rows, _ = md_table("By harness (prefill tokens, billions; runs meeting SLA)")
shown = {r[0]: r for r in page_table("harness")}
for r in rows:
    p = shown[r[0]]
    check(f"{r[0]}: runs", num(p[1]), num(r[1]), 0)
    check(f"{r[0]}: requests", num(p[2]), num(r[2]), 0)
    for i in range(4):
        check(f"{r[0]}: runs meeting SLA, router {i}", num(p[3 + i].split(" of ")[0]), num(re.search(r"\((\d+)\)", r[3 + i])[1]), 0)
    check(f"{r[0]}: prefill, KV defaults", num(p[7]), num(r[4].split(" ")[0]), 0)
    check(f"{r[0]}: prefill, affinity", num(p[8]), num(r[6].split(" ")[0]), 0)

# Slice check.
rows, _ = md_table("Slice check")
for r, p in zip(rows, page_table("slices")):
    who = f"slice check {r[0][-4:]}, {r[1]}"
    for col, name in ((2, "prefix reuse"), (3, "prefill"), (4, "requests meeting SLA"), (5, "p99 TTFT")):
        for side in (0, 1):
            check(f"{who}: {name} {'full' if side == 0 else 'sliced'}", num(p[col].split(" / ")[side]), num(r[col].split(" / ")[side]), 0)

# Native DeepSeek-V4.1-Flash cross-check. RESULTS.md prints its prefill in billions with two decimals.
rows, _ = md_table("DeepSeek-V4.1-Flash native cross-check")
for r, p in zip(rows, page_table("native")):
    who = f"native check, {r[0]}"
    check(f"{who}: prefix reuse", num(p[1]), num(r[1]), 0)
    check(f"{who}: prefill tokens", num(p[2]), 1000 * num(r[2]), 5)
    check(f"{who}: requests meeting SLA", num(p[4]), num(r[4]), 0)
    v, tol = ms(p[5]); check(f"{who}: mean TTFT", v, num(r[5]), tol)
    v, tol = ms(p[6]); check(f"{who}: p99 TTFT", v, num(r[6]), tol)

# The cover number and the figure titles that carry headline values.
rows, block = md_table("All leaderboard runs")
wrows, wblock = md_table("Endpoint windows")
check("cover ratio", num(page_text("fill", "hero-ratio")), num(rows[1][2]) / num(rows[3][2]), 0.05)
med, p90 = re.search(r"KV router \(defaults\) ([\d.]+)x / ([\d.]+)x", block).groups()
title = page_text("title", "ratio")
found = re.findall(r"([\d.]+)x", title)
check("Fig. 7 title: median run", num(found[0]) if found else None, float(med), 0.05)
check("Fig. 7 title: 90th-percentile run", num(found[1]) if len(found) > 1 else None, float(p90), 0.05)
title = page_text("title", "units")
found = [int(x) for x in re.findall(r"\d+", title)]
meets = lambda r: [int(x) for x in r[3].split(" of ")]
(kv_r, n_r), (aff_r, _), (kv_w, n_w), (aff_w, _) = meets(rows[1]), meets(rows[3]), meets(wrows[1]), meets(wrows[3])
expected = [n_r - kv_r, n_r, n_w - kv_w, n_w] + ([n_r - aff_r, n_w - aff_w] if aff_r < n_r or aff_w < n_w else [])
checks += 1
if len(found) != len(expected):
    failures.append(f"Fig. 4 title: {len(found)} numbers, expected {len(expected)}")
for i, e in enumerate(expected):
    check(f"Fig. 4 title: value {i}", found[i] if len(found) > i else None, e, 0)
title = page_text("title", "bars")
found = re.findall(r"([\d.]+)x", title)
check("Fig. 3 title: all runs", num(found[0]) if found else None, num(rows[1][2]) / num(rows[3][2]), 0.05)
check("Fig. 3 title: windows", num(found[1]) if len(found) > 1 else None, num(wrows[1][2]) / num(wrows[3][2]), 0.05)
hero = re.search(r'data-chart="hero".*?</svg>', dom, re.S)[0]
for r in rows:
    shown_b = re.findall(r">([\d.]+)B<", hero)
    check(f"cover figure: {r[0]} prefill", next((float(x) for x in shown_b if abs(float(x) - num(r[2])) <= 0.05 + 1e-9), None), num(r[2]), 0.05)

# Headline values written in the prose.
prose = strip(dom)
cached = re.search(r"Provider cached share over the same runs: ([\d.]+%)", block)[1]
for what, text in (
    ("default-router misses", f"misses the SLA on {n_r - kv_r} of {n_r} runs"),
    ("affinity misses", f"Affinity meets it on all {n_r}" if aff_r == n_r else f"against affinity's {n_r - aff_r}"),
    ("default-router windows", f"meets the SLA in {kv_w} of {n_w} windows"),
    ("round-robin multiple", f"Round-robin prefills {num(rows[0][2]) / num(rows[3][2]):.1f}x what affinity does"),
    ("window gap", f"a {num(wrows[1][2]) / num(wrows[3][2]):.1f}x gap"),
    ("window requests inside the SLA", f"with {wrows[1][4]} of requests inside it"),
    ("round-robin window TTFT", f"a mean TTFT of {num(wrows[0][5]) / 1000:.1f} s"),
    ("provider cached share", f"the providers served {cached} of prompt tokens from cache"),
    ("simulated affinity reuse", f"The simulated deployment with affinity reuses {rows[3][1]}"),
):
    checks += 1
    if text not in prose:
        failures.append(f"prose, {what}: expected to find '{text}'")

print(f"{checks} values checked against results/full/RESULTS.md, {len(failures)} differ")
for f in failures:
    print("  " + f)
sys.exit(1 if failures else 0)
