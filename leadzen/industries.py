"""Map an employee's industry words to AI Ark's fixed industry list.

AI Ark matches `account.industries` against 919 published values
(https://ai-ark.com/static/industries.csv?v=1, copied October 12, 2026 into
`data/ai_ark_industries.txt`). Free text such as "Dental practices" is not on that
list, so a search on it would return nobody. Matching is deterministic and offline.
"""
import math
import re
from functools import lru_cache
from pathlib import Path

MINIMUM = .5
# Business-form words say nothing about the industry ("dental practices" -> dental).
STOP = {"and", "or", "the", "of", "for", "in", "a", "an", "service", "company", "business", "industry", "firm",
        "agency", "practice", "shop", "store", "center", "centre", "clinic", "contractor", "provider", "organization",
        "group", "studio", "office", "owner", "local", "small"}
SYNONYMS = {"dentist": "dental", "dentistry": "dental", "lawyer": "law", "attorney": "law", "legal": "law",
            "doctor": "medical", "physician": "medical", "realtor": "real", "plumber": "plumbing", "roofer": "roofing",
            "gym": "fitness", "salon": "beauty", "auto": "automotive", "car": "automotive"}


def words(text):
    text = re.sub(r"(?<=[a-z])-(?=[a-z])", "", (text or "").lower()).replace("&", " and ")
    stems = []
    for token in re.findall(r"[a-z0-9]+", text):
        if token.endswith("ies") and len(token) > 4:
            token = token[:-3] + "y"
        elif token.endswith("s") and len(token) > 3 and not token.endswith("ss"):
            token = token[:-1]
        stems.append(SYNONYMS.get(token, token))
    return [t for t in stems if t not in STOP] or stems


@lru_cache(maxsize=1)
def catalogue():
    values = [line.strip() for line in (Path(__file__).parent / "data" / "ai_ark_industries.txt").read_text().splitlines() if line.strip()]
    sets = [set(words(v)) for v in values]
    frequency = {}
    for tokens in sets:
        for token in tokens:
            frequency[token] = frequency.get(token, 0) + 1
    weight = {token: math.log(1 + len(values) / count) for token, count in frequency.items()}
    return values, sets, weight


def closest(text, limit=3):
    """Up to `limit` supported values covering the text (AI Ark ORs them), best first.

    Empty when nothing fits; callers then search company keywords instead.
    """
    values, sets, weight = catalogue()
    remaining = set(words(text))
    rare = max(weight.values())
    chosen = []
    while remaining and len(chosen) < limit:
        total = sum(weight.get(t, rare) for t in remaining)
        best, score, covered = None, 0.0, set()
        for value, tokens in zip(values, sets):
            hit = remaining & tokens
            if not hit or value in chosen:
                continue
            shared = sum(weight.get(t, rare) for t in hit)
            precision = shared / sum(weight.get(t, rare) for t in tokens)
            # Accept a value made mostly of the employee's words, or one covering
            # most of what is left ("hvac" inside the long HVAC entry).
            if precision < MINIMUM and shared / total < MINIMUM:
                continue
            candidate = shared * (.75 + .25 * precision)
            if candidate > score or (candidate == score and len(value) < len(best)):
                best, score, covered = value, candidate, hit
        if not best:
            break
        chosen.append(best)
        remaining -= covered
    return chosen
