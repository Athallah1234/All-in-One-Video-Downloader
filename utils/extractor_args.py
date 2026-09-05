import re
from dataclasses import dataclass


_NAME=re.compile(r"^[\w-]+$",re.UNICODE)
_COMMA=re.compile(r"(?<!\\),")


@dataclass(frozen=True)
class ExtractorArgsResult:
    value: dict[str,dict[str,list[str]]]
    specifications: int
    arguments: int


def _payload(line:str) -> str:
    value=line.strip()
    if value.startswith("--extractor-args"):
        value=value[len("--extractor-args"):].strip()
        if not value:return ""
    if len(value)>=2 and value[0]==value[-1] and value[0] in {'"',"'"}:value=value[1:-1]
    return value


def parse_extractor_args(text:str) -> ExtractorArgsResult:
    """Parse one yt-dlp IE_KEY:ARGS specification per line, without invoking a shell."""
    if len(text)>16384:raise ValueError("Extractor arguments exceed the 16 KiB safety limit")
    parsed={};specifications=arguments=0
    for line_number,raw in enumerate(text.splitlines(),1):
        if not raw.strip() or raw.lstrip().startswith("#"):continue
        line=_payload(raw)
        extractor,separator,arg_text=line.partition(":")
        extractor=extractor.strip().lower()
        if not separator or not _NAME.fullmatch(extractor):raise ValueError(f"Line {line_number}: expected EXTRACTOR:ARG=VALUE")
        if extractor in parsed:raise ValueError(f"Line {line_number}: duplicate extractor '{extractor}'")
        if specifications>=32:raise ValueError("At most 32 extractor specifications are allowed")
        result={}
        for expression in arg_text.split(";"):
            key,has_value,values=expression.partition("=");key=key.strip().lower().replace("-","_")
            if not key or not _NAME.fullmatch(key):raise ValueError(f"Line {line_number}: invalid argument name")
            if key in result:raise ValueError(f"Line {line_number}: duplicate argument '{key}'")
            items=[value.replace(r"\,",",").strip() for value in _COMMA.split(values if has_value else "")]
            if any(len(value)>2048 for value in items):raise ValueError(f"Line {line_number}: argument value exceeds 2048 characters")
            result[key]=items;arguments+=1
            if arguments>256:raise ValueError("At most 256 extractor arguments are allowed")
        parsed[extractor]=result;specifications+=1
    return ExtractorArgsResult(parsed,specifications,arguments)


def parse_batch_url_specs(text:str):
    """Parse URL<TAB>extractor-args lines while preserving legacy URL-only input."""
    from utils.duplicates import canonicalize_url
    from utils.validators import is_valid_url
    valid=[];invalid=[];seen=set();duplicates=0
    for raw in text.splitlines():
        value=raw.strip().lstrip("\ufeff")
        if not value or value.startswith("#"):continue
        url,separator,args=value.partition("\t");url=url.strip();args=args.strip() if separator else ""
        if not is_valid_url(url):invalid.append(value);continue
        try:parsed=parse_extractor_args(args).value
        except ValueError as exc:invalid.append(f"{url} — {exc}");continue
        key=canonicalize_url(url)
        if key in seen:duplicates+=1;continue
        seen.add(key);valid.append((url,args,parsed))
    return valid,invalid,duplicates
