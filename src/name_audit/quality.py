"""Mechanical quality checks on the study materials, run before any paid call.

  1. Each resume reads like its own application: length, format, no near copies,
     no shared bullets, no shared employers.
  2. Nothing but the name hints at race or gender: a lexicon scan for pronouns,
     identity, religion, language, place, family, military and sports terms, plus the
     words the prompt and posting must avoid.
  3. The same text works with all 12 names: every rendering is checked.
  4. A spread of strong, borderline and weak candidates.
  5. The name, email and degree slots fill the same way in every version.

A careful human read covers what a script cannot judge.
"""

import csv
import itertools
import re
from collections import Counter
from dataclasses import dataclass, field
from difflib import SequenceMatcher

from .config import COMPANY, MATERIALS
from .materials import PLACEHOLDERS, Materials
from .prompt import system_prompt

HEADINGS = ["SUMMARY", "EXPERIENCE", "EDUCATION", "SKILLS", "ADDITIONAL"]
WORDS_MIN, WORDS_MAX = 500, 700
SHINGLE = 5
SHINGLE_LIMIT = 0.05
BULLET_LIMIT = 0.75
# Short credential lines (a certification name and year) legitimately repeat.
BULLET_MIN_WORDS = 12
JOB_LINE = re.compile(
    r"^(?P<title>[^|]+) \| (?P<employer>[^|]+), Columbus, OH \| "
    r"(?P<start>[A-Z][a-z]{2} \d{4}) to (?P<end>[A-Z][a-z]{2} \d{4}|Present)$"
)
MONTHS = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
EMAIL = re.compile(r"^[a-z]+\.[a-z]+@[a-z]+\.[a-z]+$")

BANNED = r"test\w*|bias\w*|fair\w*|evaluat\w*|demograph\w*|divers\w*|inclus\w*"
LEXICON = {
    "banned word": BANNED,
    "pronoun": r"he|she|him|her|hers|his|they|them|their|theirs|himself|herself|themselves"
    r"|themself|i|me|my|mine|myself|we|our|ours|us",
    "gendered word": r"man|men|woman|women|male|female|mother|father|mom|dad|wife|husband"
    r"|son|daughter|girl|girls|boy|boys|lady|ladies|gentlem[ae]n|chairman|chairwoman"
    r"|salesman|saleswoman|spokesman|spokeswoman|sorority|fraternity|brotherhood|sisterhood"
    r"|maternity|paternity|pregnan\w*|mrs?|ms",
    "race or ethnicity": r"black|white|african|latin[oax]|hispanic|asian|caucasian|native"
    r"|indigenous|minority|minorities|ethnic\w*|racial|race|hbcu|naacp|heritage",
    "religion": r"church|mosque|synagogue|temple|christian|muslim|islamic|jewish|catholic"
    r"|baptist|methodist|faith|ministry|gospel|bible|congregation",
    "language or origin": r"bilingual|spanish|french|mandarin|chinese|korean|arabic|hindi"
    r"|vietnamese|somali|german|portuguese|languages?|fluent|immigra\w*|visa|citizen\w*"
    r"|native speaker|hometown|born",
    "family or health": r"caregiv\w*|parental|family|families|children|kids|disab\w*"
    r"|medical leave|sabbatical",
    "military": r"army|navy|marines?|air force|veteran\w*|military|deployment",
    "sports or hobbies": r"sports?|athlet\w*|varsity|football|basketball|soccer|baseball"
    r"|softball|volleyball|hockey|golf|tennis|lacrosse|hobb\w*|interests",
    "age": r"retire\w*|grand\w+|young|youth|older|elderly|age",
}
# Phrases that use a flagged word in a neutral, non-identity sense.
ALLOWED = {
    "race or ethnicity": [r"white space", r"black box", r"white glove"],
    "family or health": [r"(product|color|item) famil\w*", r"famil\w* (code|hierarch)\w*"],
    "language or origin": [
        r"query language",
        r"programming language",
        r"plain-language",
        r"^Languages:",
    ],
    "military": [r"model deployment", r"dashboard deployment"],
    "age": [r"(vendor|property|order|invoice) and age", r"older (building|system|server)s?"],
}
# Two-letter USPS codes; OH is the study city's state.
STATE_CODES = set(
    "AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV "
    "NH NJ NM NY NC ND OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC".split()
)
STATES = (
    "Alabama Alaska Arizona Arkansas California Colorado Connecticut Delaware Florida "
    "Georgia Hawaii Idaho Illinois Indiana Iowa Kansas Kentucky Louisiana Maine Maryland "
    "Massachusetts Michigan Minnesota Mississippi Missouri Montana Nebraska Nevada Ohio "
    "Oklahoma Oregon Pennsylvania Tennessee Texas Utah Vermont Virginia Washington "
    "Wisconsin Wyoming"
).split() + [
    "New Hampshire",
    "New Jersey",
    "New Mexico",
    "New York",
    "North Carolina",
    "North Dakota",
    "Rhode Island",
    "South Carolina",
    "South Dakota",
    "West Virginia",
]
CITIES = (
    "Cleveland Cincinnati Dayton Toledo Akron Detroit Chicago Atlanta Houston Dallas Boston "
    "Philadelphia Pittsburgh Indianapolis Louisville Nashville Memphis Baltimore Miami "
    "Seattle Denver Phoenix Oakland Brooklyn Bronx Harlem Compton Dearborn Lagos Mexico "
    "Delhi Mumbai Manila Seoul Beijing Shanghai Tokyo Nairobi Accra"
).split() + ["Los Angeles", "San Francisco", "New Orleans", "St. Louis", "Kansas City"]
STATE_CODE = re.compile(r"[A-Za-z.]+, ([A-Z]{2})\b")


@dataclass
class Check:
    title: str
    passed: bool = True
    details: list[str] = field(default_factory=list)

    def fail(self, message: str) -> None:
        self.passed = False
        self.details.append(f"FAIL: {message}")

    def note(self, message: str) -> None:
        self.details.append(message)


def sections(text: str) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    current = "HEADER"
    for line in text.splitlines():
        if line in HEADINGS:
            current = line
            out[current] = []
        else:
            out.setdefault(current, []).append(line)
    return out


def bullets(text: str) -> list[str]:
    return [line[2:].strip() for line in text.splitlines() if line.startswith("- ")]


def words(text: str) -> list[str]:
    return re.findall(r"[a-z0-9$%.,']+", text.lower())


def shingles(text: str) -> set[tuple[str, ...]]:
    stripped = text
    for p in PLACEHOLDERS:
        stripped = stripped.replace(p, " ")
    w = re.findall(r"[a-z0-9]+", stripped.lower())
    return {tuple(w[i : i + SHINGLE]) for i in range(len(w) - SHINGLE + 1)}


def month_index(stamp: str) -> int:
    if stamp == "Present":
        return 2026 * 12 + 10
    mon, year = stamp.split()
    return int(year) * 12 + MONTHS.index(mon)


def load_tiers() -> dict[int, dict[str, str]]:
    with (MATERIALS / "resumes" / "index.csv").open() as fh:
        return {int(r["resume_id"]): r for r in csv.DictReader(fh)}


def check_format_and_slots(m: Materials, tiers: dict[int, dict[str, str]]) -> Check:
    c = Check("5. Name, email and degree slots fill the same way in every version")
    renders = 0
    for rid, text in sorted(m.resumes.items()):
        for p in PLACEHOLDERS:
            if text.count(p) != 1:
                c.fail(f"resume {rid}: {p} appears {text.count(p)} times")
        if re.search(r"\{(?!NAME\}|EMAIL\}|DEGREE_LINE\})", text):
            c.fail(f"resume {rid}: stray brace")
        lines = text.splitlines()
        if lines[0] != "{NAME}":
            c.fail(f"resume {rid}: first line is not {{NAME}}")
        expected = f"Columbus, OH | (614) 555-01{rid:02d} | {{EMAIL}}"
        if lines[1] != expected:
            c.fail(f"resume {rid}: contact line is {lines[1]!r}")
        heads = [line for line in lines if line in HEADINGS]
        if heads != HEADINGS:
            c.fail(f"resume {rid}: headings {heads}")
        edu = [x for x in sections(text).get("EDUCATION", []) if x.strip()]
        year = tiers[rid]["graduation_year"]
        if edu != [f"{{DEGREE_LINE}}, {year}"]:
            c.fail(f"resume {rid}: education section is {edu}")
        for name in m.names:
            if not EMAIL.match(name.email):
                c.fail(f"email {name.email} is malformed")
            for level, line in m.degree_lines.items():
                filled = m.fill(rid, name, level)
                renders += 1
                if "{" in filled or "}" in filled:
                    c.fail(f"resume {rid} with {name.name}/{level}: unfilled slot")
                if filled.splitlines()[0] != name.name:
                    c.fail(f"resume {rid} with {name.name}: name line differs")
                if filled.count(name.email) != 1 or filled.count(line) != 1:
                    c.fail(f"resume {rid} with {name.name}/{level}: slot count differs")
                back = (
                    filled.replace(name.email, "{EMAIL}")
                    .replace(line, "{DEGREE_LINE}")
                    .replace(name.name, "{NAME}")
                )
                if back != text:
                    c.fail(f"resume {rid} with {name.name}/{level}: text outside slots changed")
    c.note(
        f"{renders} renderings checked (40 resumes x 12 names x 2 degree levels): one name "
        "line, one contact line with the email, one education line, nothing else changes."
    )
    c.note(f"Degree lines: high = {m.degree_lines['high']!r}; low = {m.degree_lines['low']!r}.")
    return c


def check_realism(m: Materials) -> Check:
    c = Check("1. Each resume reads like its own application, with no near copies")
    counts = {}
    employers: dict[str, set[int]] = {}
    for rid, text in sorted(m.resumes.items()):
        if not text.isascii():
            c.fail(f"resume {rid}: non-ASCII characters")
        lengths = [len(m.fill(rid, n, lvl).split()) for n in m.names for lvl in m.degree_lines]
        counts[rid] = (min(lengths), max(lengths))
        if min(lengths) < WORDS_MIN or max(lengths) > WORDS_MAX:
            c.fail(f"resume {rid}: {min(lengths)} to {max(lengths)} words")
        previous_start = None
        for line in sections(text).get("EXPERIENCE", []):
            if not line or line.startswith("- "):
                continue
            match = JOB_LINE.match(line)
            if not match:
                c.fail(f"resume {rid}: job line not in the standard format: {line!r}")
                continue
            start, end = month_index(match["start"]), month_index(match["end"])
            if end < start:
                c.fail(f"resume {rid}: job ends before it starts: {line!r}")
            if previous_start is not None and start > previous_start:
                c.fail(f"resume {rid}: jobs are not newest first")
            previous_start = start
            employers.setdefault(match["employer"].strip(), set()).add(rid)
    shared = {e: sorted(r) for e, r in employers.items() if len(r) > 1}
    for employer, rids in shared.items():
        c.fail(f"employer {employer!r} appears in resumes {rids}")
    lo = min(v[0] for v in counts.values())
    hi = max(v[1] for v in counts.values())
    c.note(f"Length: {lo} to {hi} words across every rendering (limit {WORDS_MIN} to {WORDS_MAX}).")
    c.note(f"{len(employers)} distinct employers; none shared between resumes.")

    sh = {rid: shingles(t) for rid, t in m.resumes.items()}
    pairs = []
    for a, b in itertools.combinations(sorted(sh), 2):
        jac = len(sh[a] & sh[b]) / len(sh[a] | sh[b])
        pairs.append((jac, a, b))
    pairs.sort(reverse=True)
    for jac, a, b in pairs:
        if jac > SHINGLE_LIMIT:
            c.fail(f"resumes {a} and {b} share {jac:.1%} of {SHINGLE}-word sequences")
    c.note(
        f"Closest pair by shared {SHINGLE}-word sequences: resumes {pairs[0][1]} and "
        f"{pairs[0][2]} at {pairs[0][0]:.1%} (limit {SHINGLE_LIMIT:.0%}); median pair "
        f"{pairs[len(pairs) // 2][0]:.2%}."
    )

    all_bullets = [
        (rid, b)
        for rid, t in m.resumes.items()
        for b in bullets(t)
        if len(b.split()) >= BULLET_MIN_WORDS
    ]
    close = []
    for (ra, ba), (rb, bb) in itertools.combinations(all_bullets, 2):
        if ra == rb:
            continue
        ratio = SequenceMatcher(None, ba.lower(), bb.lower()).quick_ratio()
        if ratio >= BULLET_LIMIT:
            ratio = SequenceMatcher(None, ba.lower(), bb.lower()).ratio()
            if ratio >= BULLET_LIMIT:
                close.append((ratio, ra, rb, ba, bb))
    for ratio, ra, rb, ba, _ in sorted(close, reverse=True):
        c.fail(f"bullets in resumes {ra} and {rb} are {ratio:.0%} alike: {ba[:70]!r}")
    c.note(
        f"{len(all_bullets)} bullets of {BULLET_MIN_WORDS} or more words compared pairwise "
        "across resumes (shorter lines are certification names, which real applicants share); "
        f"{len(close)} pairs at or above {BULLET_LIMIT:.0%} similarity."
    )

    grams: Counter = Counter()
    for t in m.resumes.values():
        w = re.findall(r"[a-z]+", t.lower())
        grams.update({tuple(w[i : i + 4]) for i in range(len(w) - 3)})
    common = [(" ".join(g), n) for g, n in grams.most_common(12) if n >= 6]
    if common:
        c.note(
            "Most repeated 4-word phrases (resumes containing each): "
            + "; ".join(f"'{g}' ({n})" for g, n in common)
        )
    return c


def scan(text: str) -> list[tuple[str, str]]:
    hits = []
    for label, pattern in LEXICON.items():
        cleaned = text
        for allowed in ALLOWED.get(label, []):
            cleaned = re.sub(allowed, " ", cleaned, flags=re.IGNORECASE | re.MULTILINE)
        for match in re.finditer(rf"\b(?:{pattern})\b", cleaned, flags=re.IGNORECASE):
            word = match.group(0)
            if label == "pronoun" and word == "US":
                continue
            hits.append((label, word))
    for place in STATES + CITIES:
        if place in ("Washington",):
            pattern = rf"\b{place}\b(?! Street| Avenue)"
        else:
            pattern = rf"\b{re.escape(place)}\b"
        if re.search(pattern, text):
            hits.append(("place", place))
    for match in STATE_CODE.finditer(text):
        if match.group(1) in STATE_CODES:
            hits.append(("place", match.group(0)))
    return hits


def check_leaks(m: Materials) -> Check:
    c = Check("2. Nothing but the name hints at race or gender")
    for rid, text in sorted(m.resumes.items()):
        template = text
        for p in PLACEHOLDERS:
            template = template.replace(p, " ")
        for label, word in scan(template):
            c.fail(f"resume {rid}: {label} {word!r}")
    for label, text in (
        ("job posting", m.job_posting),
        ("system prompt", system_prompt(COMPANY)),
        ("degree lines", " ".join(m.degree_lines.values())),
    ):
        for found in re.finditer(rf"\b(?:{BANNED})\b", text, flags=re.IGNORECASE):
            c.fail(f"{label}: banned word {found.group(0)!r}")
    c.note(
        "Scanned every resume for: " + ", ".join(LEXICON) + ", place names other than "
        "Columbus, OH, and two-letter state codes other than OH."
    )
    c.note(
        "Scanned the job posting, system prompt and degree lines for the banned words "
        "(bias, fairness, test, evaluation, demographic, diversity and their forms)."
    )
    return c


def check_names(m: Materials) -> Check:
    c = Check("3. The same text reads naturally with all 12 names")
    groups = Counter(n.group for n in m.names)
    if sorted(groups.values()) != [3, 3, 3, 3] or len(m.names) != 12:
        c.fail(f"name groups are {dict(groups)}")
    for rid, text in sorted(m.resumes.items()):
        if re.search(r"\b(he|she|his|her|him|hers|they|them|their)\b", text, re.IGNORECASE):
            c.fail(f"resume {rid}: a pronoun would have to agree with the name")
        body = "\n".join(text.splitlines()[2:])
        for n in m.names:
            for part in (n.first, n.last):
                if re.search(rf"\b{part}\b", body):
                    c.fail(f"resume {rid}: body mentions {part!r}")
    c.note(
        "12 names, 3 per group: "
        + "; ".join(
            f"{g}: " + ", ".join(n.name for n in m.names if n.group == g) for g in sorted(groups)
        )
    )
    c.note(
        "No resume uses a pronoun or refers to the candidate by name outside the header, "
        "so no sentence has to agree with the name."
    )
    longest = max(m.names, key=lambda n: len(n.email))
    c.note(f"Longest email: {longest.email}. Emails follow first.last@gmail.com for every name.")
    return c


def experience_years(text: str, grad_year: int) -> float:
    starts = []
    for line in sections(text).get("EXPERIENCE", []):
        match = JOB_LINE.match(line)
        if match and int(match["start"].split()[1]) >= grad_year:
            starts.append(month_index(match["start"]))
    return (month_index("Present") - min(starts)) / 12 if starts else 0.0


def check_spread(m: Materials, tiers: dict[int, dict[str, str]]) -> Check:
    c = Check("4. A spread of strong, borderline and weak candidates")
    by_tier = Counter(tiers[rid]["tier"] for rid in m.resumes)
    if set(tiers) != set(m.resumes):
        c.fail("index.csv and the resume files list different ids")
    if min(by_tier.get(t, 0) for t in ("strong", "borderline", "weak")) < 10:
        c.fail(f"tier counts are uneven: {dict(by_tier)}")
    c.note(
        f"Planned tiers: {by_tier['strong']} strong, {by_tier['borderline']} borderline, "
        f"{by_tier['weak']} weak."
    )
    c.note(
        "| tier | resumes | years since graduation in jobs (median) | SQL used in a job "
        "| BI tool used in a job | Python or R used in a job |"
    )
    c.note("|---|---|---|---|---|---|")
    for tier in ("strong", "borderline", "weak"):
        ids = [rid for rid in m.resumes if tiers[rid]["tier"] == tier]
        years, sql, bi, code = [], 0, 0, 0
        for rid in ids:
            text = m.resumes[rid]
            exp = "\n".join(sections(text).get("EXPERIENCE", []))
            years.append(experience_years(text, int(tiers[rid]["graduation_year"])))
            sql += bool(re.search(r"\bSQL\b", exp))
            bi += bool(re.search(r"Power BI|Tableau|Looker|Metabase|SSRS", exp))
            code += bool(re.search(r"\bPython\b|\bR\b", exp))
        years.sort()
        c.note(
            f"| {tier} | {len(ids)} | {years[len(years) // 2]:.1f} | {sql}/{len(ids)} "
            f"| {bi}/{len(ids)} | {code}/{len(ids)} |"
        )
    return c


def run(m: Materials) -> list[Check]:
    tiers = load_tiers()
    return [
        check_realism(m),
        check_leaks(m),
        check_names(m),
        check_spread(m, tiers),
        check_format_and_slots(m, tiers),
    ]


def render(checks: list[Check]) -> str:
    lines = ["## Automated checks", ""]
    for c in checks:
        lines.append(f"### {c.title}: {'PASS' if c.passed else 'FAIL'}")
        lines.append("")
        previous_table = False
        for d in c.details:
            table = d.startswith("|")
            if table and not previous_table:
                lines.append("")
            lines.append(d if table else f"- {d}")
            previous_table = table
        lines.append("")
    return "\n".join(lines)
