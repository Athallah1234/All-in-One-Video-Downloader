from dataclasses import dataclass
from urllib.parse import urlparse

SPONSORBLOCK_CATEGORIES=(
    ("sponsor","Sponsor / paid promotion",True),
    ("selfpromo","Unpaid self-promotion",True),
    ("interaction","Interaction reminder",True),
    ("intro","Intro / intermission",True),
    ("outro","End cards / credits",True),
    ("preview","Preview / recap",True),
    ("hook","Hook / greeting",True),
    ("filler","Filler tangent (aggressive)",True),
    ("music_offtopic","Non-music section",True),
    ("poi_highlight","Point of interest / highlight",False),
    ("chapter","Community chapter",False),
)
ALL_CATEGORIES={key for key,_,_ in SPONSORBLOCK_CATEGORIES}
REMOVABLE_CATEGORIES={key for key,_,removable in SPONSORBLOCK_CATEGORIES if removable}

@dataclass(frozen=True)
class SponsorBlockValidation:
    valid: bool
    error: str=""

def validate_sponsorblock(mark:set[str],remove:set[str],api:str,title:str) -> SponsorBlockValidation:
    unknown=(mark|remove)-ALL_CATEGORIES
    if unknown:return SponsorBlockValidation(False,f"Unknown categories: {', '.join(sorted(unknown))}")
    invalid_remove=remove-REMOVABLE_CATEGORIES
    if invalid_remove:return SponsorBlockValidation(False,f"These categories can only be marked: {', '.join(sorted(invalid_remove))}")
    parsed=urlparse(api.strip())
    if parsed.scheme not in {"http","https"} or not parsed.netloc:return SponsorBlockValidation(False,"API endpoint must be a complete HTTP or HTTPS URL")
    if parsed.username or parsed.password:return SponsorBlockValidation(False,"API endpoint must not contain credentials")
    if len(api)>2048:return SponsorBlockValidation(False,"API endpoint is too long")
    if not title.strip() or len(title)>512:return SponsorBlockValidation(False,"Chapter title template must contain 1–512 characters")
    allowed={"start_time","end_time","category","categories","name","category_names"}
    import re
    fields=set(re.findall(r"%\(([^)]+)\)",title))
    if fields-allowed:return SponsorBlockValidation(False,f"Unsupported chapter-title fields: {', '.join(sorted(fields-allowed))}")
    return SponsorBlockValidation(True)
