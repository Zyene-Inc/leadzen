# Copyright 2026 Mindroot Ltd
# Modifications copyright 2026 Zyene
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not
# use this file except in compliance with the License. You may obtain a copy of
# the License at http://www.apache.org/licenses/LICENSE-2.0. Unless required by
# applicable law or agreed to in writing, software distributed under the License
# is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY
# KIND, either express or implied.
#
# Derived from Warmbly (https://github.com/warmbly/warmbly), commit
# 0df02b570cdca6ea567bd70887a4da6f5cc170a1, files in internal/app/replyclassify/:
# classifier.go (layer order and classes), headers.go (automated-message
# signals), lexicon.go (opt-out, declined, positive and negative phrases, quote
# stripping), optout_command.go (a reply that is only "STOP"),
# optout_languages.go (opt-out matching and folding), returndate.go (return
# dates) and the base and German rules of languages.go. Translated from Go to
# Python and modified by Zyene for LeadZen: only the offline rule layers are
# ported (no model call), the per-language sentiment vocabularies other than the
# base set and German are left out, and the sender's own opt-out footer is
# removed before reading. See THIRD_PARTY_NOTICES.md.
"""Sort a reply into interested, not interested, out of office, unsubscribe and more.

Rules only, no AI and no network: headers first (machine replies), then the
reply's own words without its quoted history. An unclear reply is "unknown"
(shown as "Needs review"); nothing here sends, and every outgoing reply still
needs the employee's approval.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta

from leadzen import dsn
from leadzen.reply_phrases import OPT_OUT_PHRASES, UNSUBSCRIBE_KEYWORDS

POSITIVE, NEGATIVE, NEUTRAL = "positive", "negative", "neutral"
AUTO_REPLY, OUT_OF_OFFICE, UNSUBSCRIBE, UNKNOWN = "auto_reply", "out_of_office", "unsubscribe", "unknown"
SOURCE_HEADER, SOURCE_LEXICON = "header", "lexicon"


@dataclass(frozen=True)
class Result:
    label: str
    confidence: float = 0.0
    source: str = ""


# ── Folding ──────────────────────────────────────────────────────────

_ACCENTS = (
    "’'", "‘'", "ʼ'", "´'", "`'",
    "ä|ae", "ö|oe", "ü|ue", "ß|ss",
    "áa", "àa", "âa", "ãa", "åa", "ée", "èe", "êe", "ëe", "íi", "ìi", "îi", "ïi",
    "óo", "òo", "ôo", "õo", "úu", "ùu", "ûu", "çc", "ñn",
    "łl", "ąa", "ęe", "ćc", "śs", "źz", "żz", "ńn", "øo", "æ|ae",
    "čc", "řr", "šs", "žz", "ýy", "ůu", "ěe", "ňn", "ťt", "ďd", "ľl", "ĺl", "ŕr",
    "ăa", "șs", "şs", "țt", "ţt", "őo", "űu", "ıi", "ğg",
    "̇|", "άα", "έε", "ήη", "ίι", "όο", "ύυ", "ώω", "ϊι", "ϋυ", "ёе", "  ",
)
_ACCENT_MAP = {}
for _pair in _ACCENTS:
    _key, _, _value = _pair.partition("|") if "|" in _pair else (_pair[0], "", _pair[1:])
    _ACCENT_MAP[_key] = _value
_ACCENT_TABLE = str.maketrans(_ACCENT_MAP)
_QUOTE_TABLE = str.maketrans({"’": "'", "‘": "'", "ʼ": "'", "´": "'", "`": "'"})
_OPT_OUT_TABLE = str.maketrans({"ς": "σ", "đ": "d", "أ": "ا", "إ": "ا", "آ": "ا", "ي": "ی", "ك": "ک", "ى": "ی"})


def fold_accents(text: str) -> str:
    """Lower-case, flatten accents and quotes, collapse whitespace."""
    return " ".join((text or "").lower().translate(_ACCENT_TABLE).split())


def _latin_or_greek(ch: str) -> bool:
    name = unicodedata.name(ch, "")
    return name.startswith(("LATIN", "GREEK"))


def fold_opt_out(text: str) -> str:
    """What both a phrase and a reply are matched as."""
    text = unicodedata.normalize("NFC", text or "").lower().translate(_ACCENT_TABLE)
    out, strip = [], False
    for ch in unicodedata.normalize("NFD", text):
        if unicodedata.category(ch) == "Mn":
            if strip:
                continue
        else:
            strip = _latin_or_greek(ch)
        out.append(ch)
    return " ".join(unicodedata.normalize("NFC", "".join(out)).translate(_OPT_OUT_TABLE).split())


def _unspaced(ch: str) -> bool:
    """A script that runs its words together, where a phrase has no boundary."""
    return unicodedata.name(ch, "").startswith(("CJK", "HIRAGANA", "KATAKANA", "HANGUL", "THAI"))


def _word_patterns(phrases):
    boundary = r"[^\w]"
    out = []
    for phrase in phrases:
        open_start, open_end = phrase.startswith("*"), phrase.endswith("*")
        folded = fold_opt_out(phrase.strip("*"))
        if not folded:
            continue
        pattern = re.escape(folded)
        if not open_start and not _unspaced(folded[0]):
            pattern = f"(?:^|{boundary})" + pattern
        if not open_end and not _unspaced(folded[-1]):
            pattern += f"(?:$|{boundary})"
        out.append(re.compile(pattern))
    return out


OPT_OUT_PATTERNS = _word_patterns(UNSUBSCRIBE_KEYWORDS + tuple(p for code in sorted(OPT_OUT_PHRASES) for p in OPT_OUT_PHRASES[code]))

# A GDPR Art. 21 objection, first person only, followed by what it objects to.
GDPR_OBJECTION = re.compile(
    r"(^|[^a-z0-9])(widerspreche|wir widersprechen|widersprechen wir)([^a-z0-9]|$)"
    r"(?:[^.!?:;,]|\b(?:gem|art|abs|nr|lit|i\.v\.m|z\.b|bzw|ggf)\.){0,90}?"
    r"\b(der|dem|den|einer|jeder|jede|jeglicher|jeglichen) (?:[a-z-]+ ){0,2}?[a-z-]*"
    r"(verarbeitung|nutzung|verwendung|speicherung|weitergabe|zusendung|kontaktaufnahme|werbung|mails|nachrichten|newsletter)")


def matches_opt_out(lower_text: str) -> bool:
    folded = fold_opt_out(lower_text)
    return any(p.search(folded) for p in OPT_OUT_PATTERNS) or bool(GDPR_OBJECTION.search(folded))


# ── Quoted history ──────────────────────────────────────────────────


def _attribution(lead, tail):
    return re.compile(r"(?is)(^|\s)" + lead + r"\s[^\n]{0,250}?(\d{4}|\d{1,2}[:.]\d{2}|@)[^\n]{0,250}?\n?[^\n]{0,250}?\s" + tail)


def _header_block(sender, sent):
    return re.compile(r"(?is)(^|\s)(" + sender + r"):\s.{1,300}?\s(" + sent + r"):\s")


# (pattern, cut from the start of the matched line)
QUOTE_MARKERS = (
    (_attribution("on", "wrote:"), False),
    (re.compile(r"(?i)_{10,}"), False),
    (re.compile(r"(?im)^\s*from:\s.+$"), False),
    (_header_block("from", "sent|date"), False),
    (_attribution("le", r"a écrit\s*:"), False),
    (_attribution("am", r"schrieb\b"), False),
    (_attribution("el", r"escribió\s*:"), False),
    (_attribution("op", r"schreef\b"), False),
    (_attribution("il", r"ha scritto\s*:"), False),
    # German, always cut because the opt-out phrases include German.
    (_header_block("von", "gesendet|datum"), False),
    (_header_block("gesendet", "von"), False),
    (re.compile(r"(?i)-{2,}\s*(original message|forwarded message|ursprüngliche nachricht|original-nachricht|weitergeleitete nachricht)\s*-{2,}"), False),
)


def strip_quoted(body: str) -> str:
    """Drop the quoted history: everything from the first reply marker, and ">" lines."""
    if not body:
        return ""
    cut = len(body)
    for pattern, line_start in QUOTE_MARKERS:
        match = pattern.search(body)
        if not match:
            continue
        at = match.start()
        if line_start and (nl := body.rfind("\n", 0, at)) >= 0:
            at = nl + 1
        cut = min(cut, at)
    lines = [ln for ln in body[:cut].split("\n") if not ln.strip().startswith(">")]
    return "\n".join(lines).strip()


# ── Layer 1: headers ────────────────────────────────────────────────

OOO_SUBJECTS = tuple(fold_accents(m) for m in (
    "out of office", "out of the office", "automatic reply", "automated reply",
    "autoreply", "auto-reply", "auto reply", "auto:", "away:", "on vacation:", "vacation reply",
    "abwesenheit", "abwesend", "automatische antwort", "autom. antwort", "ausser haus", "nicht im buero", "im urlaub:",
    "reponse automatique", "absence du bureau", "message d'absence",
    "respuesta automatica", "ausencia de la oficina", "ausencia temporal", "resposta automatica", "fora do escritorio",
    "risposta automatica", "fuori sede:", "assente dall'ufficio",
    "automatisch antwoord", "afwezigheid", "afwezigheidsbericht",
    "automatiskt svar", "automatisk svar", "autosvar", "fravaer", "fravaersmelding", "automatyczna odpowiedz",
))


def _header(headers, name):
    value = headers.get(name) if headers is not None else None
    return str(value).strip() if value is not None else ""


def _has(headers, name):
    return headers is not None and headers.get(name) is not None


def is_delivery_failure(headers, subject: str) -> bool:
    content_type = _header(headers, "Content-Type").lower()
    if "multipart/report" in content_type and "delivery-status" in content_type:
        return True
    if _header(headers, "X-Failed-Recipients"):
        return True
    return dsn.is_bounce_sender(_header(headers, "From")) or dsn.has_bounce_subject(subject)


def is_bulk_mail(headers) -> bool:
    """A list, newsletter or notification: its "unsubscribe" is the sender's own."""
    return bool(_header(headers, "List-Unsubscribe") or _header(headers, "List-Id"))


def classify_headers(headers, subject: str) -> Result | None:
    """Recognise a machine reply. Out of office is read from the SUBJECT only, as a prefix."""
    lowered = (subject or "").strip().lower()
    if lowered.startswith("report domain:") and " submitter:" in lowered and " report-id:" in lowered:
        return Result(AUTO_REPLY, 0.99, SOURCE_HEADER)
    content_type = _header(headers, "Content-Type").lower()
    if "tlsrpt" in content_type:
        return Result(AUTO_REPLY, 0.99, SOURCE_HEADER)
    # A bounce also carries Auto-Submitted: auto-replied; decide it first.
    if is_delivery_failure(headers, lowered):
        return Result(AUTO_REPLY, 0.95, SOURCE_HEADER)
    folded = fold_accents(lowered)
    if folded and any(folded.startswith(m) for m in OOO_SUBJECTS):
        return Result(OUT_OF_OFFICE, 0.98, SOURCE_HEADER)
    auto = _header(headers, "Auto-Submitted").lower()
    if auto and auto != "no":
        return Result(OUT_OF_OFFICE if "auto-replied" in auto else AUTO_REPLY, 0.95, SOURCE_HEADER)
    if _has(headers, "X-Autoreply") or _has(headers, "X-Autorespond"):
        return Result(OUT_OF_OFFICE, 0.93, SOURCE_HEADER)
    if _header(headers, "X-Auto-Response-Suppress"):
        return Result(AUTO_REPLY, 0.9, SOURCE_HEADER)
    precedence = _header(headers, "Precedence").lower()
    if precedence == "auto_reply":
        return Result(AUTO_REPLY, 0.9, SOURCE_HEADER)
    if precedence in ("bulk", "junk", "list"):
        return Result(AUTO_REPLY, 0.75, SOURCE_HEADER)
    if "multipart/report" in content_type and "disposition-notification" in content_type:
        return Result(AUTO_REPLY, 0.95, SOURCE_HEADER)
    if _has(headers, "Return-Path") and _header(headers, "Return-Path") in ("<>", ""):
        return Result(AUTO_REPLY, 0.85, SOURCE_HEADER)
    sender = _header(headers, "From").lower()
    if any(m in sender for m in ("no-reply@", "noreply@", "donotreply@")):
        return Result(AUTO_REPLY, 0.8, SOURCE_HEADER)
    return None


# ── Layer 2: lexicon ────────────────────────────────────────────────

POSITIVE_KEYWORDS = (
    "interested", "sounds good", "sounds great", "let's chat", "lets chat", "let's talk", "lets talk",
    "happy to chat", "happy to talk", "set up a call", "book a call", "schedule a call", "schedule a demo",
    "book a demo", "send me more", "tell me more", "would love to", "count me in", "sign me up",
    "how much does it cost", "what's the pricing", "whats the pricing", "send pricing",
)
DECLINED_KEYWORDS = (
    "not interested", "n't interested", "not really interested", "not very interested", "not that interested",
    "not too interested", "not particularly interested", "not currently interested", "no longer interested",
    "not be interested", "n't be interested", "uninterested", "disinterested",
)
NEGATIVE_KEYWORDS = (
    "no thanks", "no thank you", "not a fit", "not the right", "not relevant", "no need", "we already have",
    "we have a solution", "not looking", "wrong person", "wrong contact", "please don't", "leave me alone", "go away",
)
# German, whole words only (languages.go "de").
GERMAN_DECLINED = ("kein interesse", "keinerlei interesse", "nicht interessiert", "nicht mehr interessiert",
                   "interessiert uns nicht", "interessiert mich nicht")
GERMAN_NEGATIVE = ("nein danke", "nein, danke", "kein bedarf", "keinen bedarf", "falscher ansprechpartner",
                   "falschen ansprechpartner", "nicht der richtige ansprechpartner",
                   "nicht die richtige ansprechpartnerin", "nicht zustaendig")


def _bounded(phrase, text):
    return re.search(r"(?<!\w)" + re.escape(phrase) + r"(?!\w)", text) is not None


COMMAND_WORDS = r"(?:stop|stopp|remove|remove me|unsubscribe|unsubscribe me|opt out|optout|abmelden|austragen|afmelden|baja)"
COMMAND_POLITE = r"(?:please|pls|plz|now|thanks|thank you|thx|ty|bitte|danke|graag|alstublieft|aub|por favor|gracias|svp|merci|tack)"
OPT_OUT_COMMAND = re.compile(rf"^(?:{COMMAND_POLITE} )*{COMMAND_WORDS}(?: (?:{COMMAND_WORDS}|{COMMAND_POLITE}))*$")
COMMAND_GREETINGS = frozenset(("hi", "hello", "hey", "dear", "hallo", "hola", "bonjour", "hej", "good morning",
                               "good afternoon", "guten tag", "moin"))
COMMAND_SIGN_OFFS = frozenset((
    "thanks", "thank you", "thx", "ty", "many thanks", "cheers", "regards", "best", "best regards", "kind regards",
    "warm regards", "sincerely", "br", "kr", "mfg", "lg", "vg", "viele gruesse", "beste gruesse", "freundliche gruesse",
    "mit freundlichen gruessen", "gruss", "gruesse", "saludos", "cordialement", "bien a vous", "met vriendelijke groet",
    "groeten", "mvh", "hilsen", "med vanlig halsning"))
COMMAND_FOOTERS = frozenset((
    "sent from my iphone", "sent from my ipad", "sent from my android", "sent from my android phone", "sent from my mobile",
    "sent from my mobile device", "sent from my phone", "sent from my samsung galaxy smartphone", "sent from my blackberry",
    "sent from mail for windows", "sent from mail for windows 10", "sent from outlook for ios", "sent from outlook for android",
    "get outlook for ios", "get outlook for android", "sent from yahoo mail for iphone", "sent from yahoo mail on android",
    "sent from gmail mobile", "von meinem iphone gesendet", "von meinem ipad gesendet", "von meinem smartphone gesendet",
    "enviado desde mi iphone", "enviado desde mi ipad", "envoye de mon iphone", "envoye de mon ipad",
    "verzonden vanaf mijn iphone", "verstuurd vanaf mijn iphone", "skickat fran min iphone", "sendt fra min iphone"))
PROSE_WORDS = frozenset((
    "i", "me", "my", "we", "us", "our", "you", "your", "it", "is", "are", "am", "was", "be", "but", "not",
    "do", "would", "could", "can", "will", "if", "so", "just", "actually", "love", "like", "want", "let", "lets",
    "interested", "please", "call", "send", "tell", "talk", "great", "sounds", "meeting", "demo", "price", "pricing",
    "yes", "no", "sure", "ok", "okay", "maybe", "later", "today", "tomorrow", "monday", "tuesday", "wednesday", "thursday",
    "friday", "saturday", "sunday", "noon", "next", "week", "month", "year", "soon", "now", "asap", "time", "here", "there",
    "the", "a", "an", "at", "of", "and", "for", "to", "in", "on", "with", "ich", "wir", "sie", "ist", "aber", "nicht"))
COMMAND_PRONOUNS = re.compile(r"(?i)^\((?:she|he|they|ze|xe)/(?:her|him|them|hers|his|theirs|zir|xem)(?:/[a-z]+)?\)$")
COMMAND_MAX_LINES = 4


def _command_text(line):
    folded = fold_opt_out(line)
    return " ".join("".join(ch if ch.isalnum() else " " for ch in folded).split())


def _name_word(token):
    if token.endswith(".") and len(token) == 2:
        token = token[:-1]
    if not token or not token[0].isupper() or token.lower() in PROSE_WORDS:
        return False
    return all(ch.isalpha() or unicodedata.category(ch) == "Mn" for ch in token)


def _name_line(tokens):
    if tokens and COMMAND_PRONOUNS.match(tokens[-1].rstrip(",.")):
        tokens = tokens[:-1]
    if not tokens or len(tokens) > 3:
        return False
    return all(_name_word(t.rstrip(",.") if i == len(tokens) - 1 else t) for i, t in enumerate(tokens))


def _led_by_name(raw, phrases):
    tokens = raw.split()
    for k in range(min(len(tokens), 4), 0, -1):
        if _command_text(" ".join(tokens[:k])) in phrases:
            return k == len(tokens) or _name_line(tokens[k:])
    return False


def _signature_only(lines):
    count = 0
    for raw in lines:
        line = raw.strip()
        if not line or _command_text(line) in COMMAND_FOOTERS:
            continue
        if line == "--":
            return True
        count += 1
        if count > COMMAND_MAX_LINES:
            return False
        if not _led_by_name(line, COMMAND_SIGN_OFFS) and not _name_line(line.split()):
            return False
    return True


def is_opt_out_command(body: str) -> bool:
    """A reply that says nothing but an opt-out command: "STOP", "Remove me please"."""
    lines = (body or "").replace("\r\n", "\n").split("\n")
    for i, raw in enumerate(lines):
        if OPT_OUT_COMMAND.match(_command_text(raw)):
            return _signature_only(lines[i + 1:])
        if not raw.strip() or _led_by_name(raw, COMMAND_GREETINGS):
            continue
        return False
    return False


def classify_lexicon(subject: str, body: str) -> Result | None:
    """Clear signals only. Compliance first, then declined, negative and interest."""
    reply = strip_quoted(body)
    text = (subject or "").strip().lower().translate(_QUOTE_TABLE) + ".\n" + reply.lower().translate(_QUOTE_TABLE)
    if not text.strip(". \n"):
        return None
    if matches_opt_out(text) or is_opt_out_command(reply):
        return Result(UNSUBSCRIBE, 0.9, SOURCE_LEXICON)
    folded = text.translate(_ACCENT_TABLE)
    if any(k in text for k in DECLINED_KEYWORDS) or any(_bounded(k, folded) for k in GERMAN_DECLINED):
        return Result(NEGATIVE, 0.8, SOURCE_LEXICON)
    if any(_bounded(k, folded) for k in GERMAN_NEGATIVE):
        return Result(NEGATIVE, 0.8, SOURCE_LEXICON)
    if any(k in text for k in POSITIVE_KEYWORDS):
        return Result(POSITIVE, 0.8, SOURCE_LEXICON)
    if any(k in text for k in NEGATIVE_KEYWORDS):
        return Result(NEGATIVE, 0.8, SOURCE_LEXICON)
    return None


def classify(headers, subject: str, body: str) -> Result:
    """Headers, then lexicon. Inconclusive is UNKNOWN; no model is called."""
    return classify_headers(headers, subject) or classify_lexicon(subject, body) or Result(UNKNOWN)


def is_opt_out(subject: str, body: str) -> bool:
    """The reply, without its quoted history, asks to stop being emailed."""
    reply = strip_quoted(body)
    text = ((subject or "") + "\n" + reply).strip().lower()
    return bool(text) and (matches_opt_out(text) or is_opt_out_command(reply))


# ── Return date ─────────────────────────────────────────────────────

RETURN_WINDOW_DAYS = 92
RETURN_CUE_WINDOW = 48
CUES = (
    "back on", "back in the office on", "back at my desk on", "be back on", "return on", "returning on",
    "will return on", "i return on", "my return on", "returns on", "available again on", "reachable again on",
    "back from", "until", "till", "through",
    "zurueck am", "zurueck ab", "wieder am", "wieder ab", "ab dem",
    "ab (?:montag|dienstag|mittwoch|donnerstag|freitag)(?:,? de[nm]|, ?)",
    "wieder erreichbar am", "wieder erreichbar ab", "wieder im buero am", "bis einschliesslich", "bis zum", "bis",
    "ab kw", "ab der kw",
    "de retour le", "jusqu'au", "jusqu au", "a partir du", "de vuelta el", "regreso el", "hasta el", "a partir del",
    "de volta a", "ate o dia", "a partir de", "terug op", "weer aanwezig op", "tot en met",
    "di ritorno il", "fino al", "rientro il",
)
INCLUSIVE_CUES = frozenset(("through", "bis einschliesslich", "tot en met"))
END_CUES = frozenset(("bis", "bis zum", "bis einschliesslich"))
MONTHS = {}
for _month, _names in {
    1: "january jan januar janvier enero ene janeiro januari gennaio", 2: "february feb februar fevrier febrero fevereiro februari febbraio",
    3: "march mar maerz marz mars marzo marco maart", 4: "april apr avril abril aprile", 5: "may mai mayo maio mei maggio",
    6: "june jun juni juin junio junho giugno", 7: "july jul juli juillet julio julho luglio", 8: "august aug aout agosto augustus ago",
    9: "september sep sept septembre septiembre setembro settembre", 10: "october oct oktober octobre octubre outubro okt ottobre",
    11: "november nov novembre noviembre novembro", 12: "december dec dezember decembre diciembre dezembro dez dicembre",
}.items():
    for _name in _names.split():
        MONTHS[_name] = _month
CUE = re.compile(r"(?i)\b(" + "|".join(sorted(CUES, key=len, reverse=True)) + r")\b")
SENTENCE_MARK = "\x00"
_SENTENCE_START_BIS = re.compile(r"([.!?;:])(\s+)Bis\b")
_RANGE_BREAK = re.compile(SENTENCE_MARK + r"|[a-z][.!?;:](\s|$)|[!?;]|\b(wieder|zurueck|erreichbar|buero|da)\b")
_RANGE_NOISE = re.compile(r"\bnicht (mehr )?(im )?(buero|erreichbar|da)\b|\b(jan|feb|mrz|apr|jun|jul|aug|sep|sept|okt|nov|dez)\.")
_WEEK_DIGITS = re.compile(r"\bkw(\d)")
ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
DOTTED_DATE = re.compile(r"\b(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4}|\d{2})?")
DAY_THEN_NAME = re.compile(r"\b(\d{1,2})(?:st|nd|rd|th|\.)?\s+(?:of\s+|de\s+|di\s+)?([a-z]{3,12})\.?(?:\s+(\d{4}))?")
NAME_THEN_DAY = re.compile(r"\b([a-z]{3,12})\.?\s+(\d{1,2})\b(?:st|nd|rd|th|\.)?(?:,?\s+(\d{4}))?")
CALENDAR_WEEK = re.compile(r"\bkw\s?(\d{1,2})(?:\s?[-/–]\s?(\d{1,2}))?\b")


def _resolve(day, month, year, today, explicit_year):
    if not (1 <= day <= 31 and 1 <= month <= 12):
        return None
    limit = today + timedelta(days=RETURN_WINDOW_DAYS)
    years = (year,) if explicit_year else (today.year, today.year + 1)
    for y in years:
        try:
            d = date(y, month, day)
        except ValueError:
            continue
        if today <= d <= limit:
            return d
    return None


def _resolve_week(week, today):
    if not 1 <= week <= 53:
        return None
    for y in (today.isocalendar()[0], today.isocalendar()[0] + 1):
        try:
            monday = date.fromisocalendar(y, week, 1)
        except ValueError:
            continue
        if monday + timedelta(days=6) < today or monday > today + timedelta(days=RETURN_WINDOW_DAYS):
            continue
        return monday
    return None


def _year(text):
    if not text:
        return 0
    return int(text) + 2000 if len(text) == 2 else int(text)


def _first_date(span, today, last_week):
    """The EARLIEST date in text order: ``(date, is_week, end)`` or None."""
    hits = []
    for m in ISO_DATE.finditer(span):
        if d := _resolve(int(m[3]), int(m[2]), int(m[1]), today, True):
            hits.append((m.start(), m.end(), d, False))
    for m in DOTTED_DATE.finditer(span):
        if d := _resolve(int(m[1]), int(m[2]), _year(m[3]), today, bool(m[3])):
            hits.append((m.start(), m.end(), d, False))
    for m in DAY_THEN_NAME.finditer(span):
        if m[2] in MONTHS and (d := _resolve(int(m[1]), MONTHS[m[2]], _year(m[3]), today, bool(m[3]))):
            hits.append((m.start(), m.end(), d, False))
    for m in NAME_THEN_DAY.finditer(span):
        if m[1] in MONTHS and (d := _resolve(int(m[2]), MONTHS[m[1]], _year(m[3]), today, bool(m[3]))):
            hits.append((m.start(), m.end(), d, False))
    for m in CALENDAR_WEEK.finditer(span):
        week = int(m[2]) if last_week and m[2] else int(m[1])
        if d := _resolve_week(week, today):
            hits.append((m.start(), m.end(), d, True))
    if not hits:
        return None
    _, end, d, is_week = min(hits, key=lambda h: h[0])
    return d, is_week, end


def find_return_date(subject: str, body: str, today: date):
    """The first day an out-of-office sender is back, or None when unsure."""
    text = _SENTENCE_START_BIS.sub(r"\1" + SENTENCE_MARK + r"\2Bis", (subject or "") + "\n" + strip_quoted(body))
    text = _WEEK_DIGITS.sub(r"kw \1", fold_accents(text).replace("kalenderwoche", "kw"))
    if not text:
        return None

    def at(match):
        cue = match.group(1).lower()
        start = match.end() - (2 if cue.endswith("kw") else 0)
        found = _first_date(text[start:match.end() + RETURN_CUE_WINDOW], today, cue in END_CUES)
        if not found:
            return None
        d, is_week, _ = found
        if is_week and cue in END_CUES:
            return d + timedelta(days=7)
        if is_week:
            return max(d, today)
        return d + timedelta(days=1) if cue in INCLUSIVE_CUES else d

    cues = list(CUE.finditer(text))
    for i, match in enumerate(cues):
        back = at(match)
        if back is None:
            continue
        # "ab Freitag, 4.9., bis 18.9." is a range: back after its end.
        if match.group(1).lower().startswith("ab ") and i + 1 < len(cues):
            nxt = cues[i + 1]
            gap = _RANGE_NOISE.sub("", text[match.end():nxt.start()])
            if nxt.start() < match.end() + RETURN_CUE_WINDOW and nxt.group(1).lower() in END_CUES and not _RANGE_BREAK.search(gap):
                end = at(nxt)
                if end and end > back:
                    return end
        return back
    return None


def next_business_day(d: date) -> date:
    """The day after ``d``, skipping the weekend: the backlog day is not a send day."""
    d += timedelta(days=1)
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d
