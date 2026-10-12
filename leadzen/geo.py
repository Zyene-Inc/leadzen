"""Plain place names that lead providers match, from saved ISO country codes."""
from pytz import country_names

# pytz writes several countries the way a time-zone picker does ("Britain (UK)").
# Providers match common English names, so those are normalized here.
COMMON = {
    "AG": "Antigua and Barbuda", "AS": "American Samoa", "BA": "Bosnia and Herzegovina",
    "BL": "Saint Barthelemy", "CC": "Cocos (Keeling) Islands", "CD": "Democratic Republic of the Congo",
    "CG": "Republic of the Congo", "CI": "Cote d'Ivoire", "CZ": "Czechia", "GB": "United Kingdom",
    "GS": "South Georgia and the South Sandwich Islands", "HM": "Heard Island and McDonald Islands",
    "KN": "Saint Kitts and Nevis", "KP": "North Korea", "KR": "South Korea", "LC": "Saint Lucia",
    "MF": "Saint Martin", "MM": "Myanmar", "PM": "Saint Pierre and Miquelon", "SH": "Saint Helena",
    "SJ": "Svalbard and Jan Mayen", "ST": "Sao Tome and Principe", "SX": "Sint Maarten", "SZ": "Eswatini",
    "TC": "Turks and Caicos Islands", "TT": "Trinidad and Tobago", "VC": "Saint Vincent and the Grenadines",
    "VG": "British Virgin Islands", "VI": "U.S. Virgin Islands", "WF": "Wallis and Futuna", "WS": "Samoa",
}


def country_name(code):
    return COMMON.get(code) or country_names[code]


def countries():
    return [{"code": code, "name": country_name(code)} for code in sorted(country_names, key=country_name)]


def place(audience):
    """The searched location: an optional state/city within the saved country."""
    country = country_name(audience["country"])
    region = (audience.get("region") or "").strip()
    return f"{region}, {country}" if region else country
