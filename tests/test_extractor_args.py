import logging
from models.download import DownloadRequest
from services.ytdlp_service import YTDLPService
from utils.extractor_args import parse_batch_url_specs,parse_extractor_args
from utils.security import redact


def test_cli_compatible_extractor_arg_parsing():
    result=parse_extractor_args('youtube:player-client=web,android;player_skip=configs;po_token=web.gvs+abc\\,def\n--extractor-args "generic:impersonate=chrome"')
    assert result.specifications==2 and result.arguments==4
    assert result.value["youtube"]["player_client"]==["web","android"]
    assert result.value["youtube"]["po_token"]==["web.gvs+abc,def"]
    assert result.value["generic"]["impersonate"]==["chrome"]


def test_flags_without_values_and_comments():
    assert parse_extractor_args("# comment\nyoutubetab:skip=webpage;approximate_date").value=={"youtubetab":{"skip":["webpage"],"approximate_date":[""]}}


def test_invalid_and_duplicate_specs_are_rejected():
    for value in ("youtube",":x=y","youtube:bad key=x","youtube:a=1\nyoutube:b=2","youtube:a=1;a=2"):
        try:parse_extractor_args(value)
        except ValueError:pass
        else:raise AssertionError(f"invalid input accepted: {value}")


def test_batch_url_tab_syntax_and_duplicate_handling():
    specs,invalid,duplicates=parse_batch_url_specs("https://example.com/a\tgeneric:impersonate=chrome\nhttps://example.com/b\nhttps://EXAMPLE.com/a\ninvalid")
    assert len(specs)==2 and specs[0][2]=={"generic":{"impersonate":["chrome"]}}
    assert specs[1][2]=={} and duplicates==1 and invalid==["invalid"]


def test_download_request_passes_extractor_args_to_ytdlp(tmp_path):
    args={"youtube":{"player_client":["web"]}};request=DownloadRequest("https://example.com","Example",str(tmp_path),extractor_args=args)
    assert YTDLPService(logging.getLogger("test")).build_options(request)["extractor_args"]==args


def test_extractor_args_are_redacted_from_logs():
    value=redact("extractor_args={'site': {'api_key': ['secret']}}\nSafe")
    assert "secret" not in value and "Safe" in value


def test_custom_args_merge_with_authenticated_defaults_and_take_precedence(tmp_path):
    from services.cookie_service import BrowserCookieSource
    service=YTDLPService(logging.getLogger("test"));service.set_cookie_source(BrowserCookieSource("chrome"))
    request=DownloadRequest("https://example.com","Example",str(tmp_path),extractor_args={"youtube":{"lang":["id"]},"generic":{"impersonate":["chrome"]}})
    args=service.build_options(request)["extractor_args"]
    assert args["youtube"]["player_client"]==["default","web_embedded"] and args["youtube"]["lang"]==["id"]
    assert args["generic"]["impersonate"]==["chrome"]
    override=DownloadRequest("https://example.com","Example",str(tmp_path),extractor_args={"youtube":{"player_client":["web"]}})
    assert service.build_options(override)["extractor_args"]["youtube"]["player_client"]==["web"]
