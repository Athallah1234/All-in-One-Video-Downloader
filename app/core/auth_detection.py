"""Conservative, offline hints that a media URL may require authentication."""
from urllib.parse import parse_qs, urlsplit


ACCOUNT_DOMAINS = {
    "onlyfans.com": (85, "This platform normally requires an account."),
    "fansly.com": (85, "This platform normally requires an account."),
    "patreon.com": (70, "Creator posts may be limited to members."),
    "linkedin.com": (45, "LinkedIn content may require a signed-in session."),
    "instagram.com": (40, "Instagram may require a signed-in browser session."),
    "facebook.com": (40, "Facebook may require a signed-in browser session."),
}

PRIVATE_SEGMENTS = {
    "private": "The URL path is marked private.",
    "premium": "The URL path is marked premium.",
    "members": "The URL points to member content.",
    "member": "The URL points to member content.",
    "subscriber": "The URL points to subscriber content.",
    "subscribers": "The URL points to subscriber content.",
    "subscription": "The URL points to subscription content.",
}
LOGIN_SEGMENTS = {"login", "signin", "sign-in", "account", "dashboard", "manage"}
SIGNED_QUERY_KEYS = {"access_token", "auth", "authorization", "expires", "hash", "signature", "sig", "secret_token", "token"}


def configured_auth_methods(preferences):
    preferences = preferences or {}
    methods = []
    if preferences.get("site_login") and str(preferences.get("username", "")).strip() and preferences.get("password"):
        methods.append("username/password")
    if preferences.get("use_netrc"):
        methods.append("netrc")
    cookies = preferences.get("cookies", "No Cookies")
    if cookies == "Cookie File":
        methods.append("cookie file")
    elif cookies == "Cookies from Browser":
        methods.append("browser cookies")
    return tuple(methods)


def detect_auth_requirement(url, extractor=None, preferences=None):
    """Estimate login likelihood from URL/extractor signals without network access."""
    try:
        parsed = urlsplit(url.strip())
    except (AttributeError, ValueError):
        parsed = urlsplit("")
    host = (parsed.hostname or "").casefold().rstrip(".")
    segments = {segment.casefold() for segment in parsed.path.split("/") if segment}
    query_keys = {key.casefold() for key in parse_qs(parsed.query, keep_blank_values=True)}
    reasons = []
    score = 0

    for domain, (domain_score, reason) in ACCOUNT_DOMAINS.items():
        if host == domain or host.endswith("." + domain):
            score = max(score, domain_score)
            reasons.append(reason)
            break
    private = segments & PRIVATE_SEGMENTS.keys()
    if private:
        score = max(score, 85)
        reasons.append(PRIVATE_SEGMENTS[sorted(private)[0]])
    if segments & LOGIN_SEGMENTS:
        score = max(score, 90)
        reasons.append("The URL points to an account, login, or management area.")
    if host.endswith("linkedin.com") and "learning" in segments:
        score = max(score, 70)
        reasons.append("LinkedIn Learning commonly requires an authenticated session.")
    if host.endswith("instagram.com") and "stories" in segments:
        score = max(score, 65)
        reasons.append("Instagram Stories commonly require an authenticated session.")
    if host.endswith("facebook.com") and "groups" in segments:
        score = max(score, 65)
        reasons.append("Facebook group media may require membership and browser cookies.")
    if host.endswith("vimeo.com") and "ondemand" in segments:
        score = max(score, 70)
        reasons.append("Vimeo On Demand may require purchase or account access.")

    signed_keys = sorted(query_keys & SIGNED_QUERY_KEYS)
    if signed_keys:
        reasons.append("The URL includes an access token or signature that may already grant temporary access.")

    extractor_name = str((extractor or {}).get("extractor", ""))
    login_capable = bool((extractor or {}).get("supports_authentication")) or extractor_name.casefold() not in {"", "generic"} and any(
        marker in extractor_name.casefold() for marker in
        ("instagram", "facebook", "patreon", "onlyfans", "linkedin", "vimeo", "soundcloud", "twitch", "youtube")
    )
    if login_capable and score == 0:
        reasons.append(f"The {extractor_name} extractor supports content that can be account-restricted.")
        score = 25

    likelihood = "likely" if score >= 65 else "possible" if score >= 25 else "unlikely"
    methods = configured_auth_methods(preferences)
    return {
        "likelihood": likelihood,
        "score": score,
        "reasons": tuple(dict.fromkeys(reasons)),
        "auth_configured": bool(methods),
        "configured_methods": methods,
        "signed_access_url": bool(signed_keys),
        "extractor_supports_auth": login_capable,
    }
