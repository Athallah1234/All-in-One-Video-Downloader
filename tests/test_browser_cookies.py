import logging
from PySide6.QtCore import QSettings
from models.download import DownloadRequest
from services.cookie_service import BrowserCookieSource,cookie_file_from_settings,cookie_source_from_settings,validate_netscape_cookie_file
from services.ytdlp_service import YTDLPService
from utils.security import redact


def test_browser_cookie_tuple_matches_ytdlp_api():
    assert BrowserCookieSource("chrome").as_ytdlp_tuple()==("chrome",None,None,None)
    assert BrowserCookieSource("firefox","work","Personal").as_ytdlp_tuple()==("firefox","work",None,"Personal")


def test_cookie_source_rejects_unsupported_browser_and_cross_browser_container():
    try:BrowserCookieSource("safari")
    except ValueError:pass
    else:raise AssertionError("unsupported browser accepted")
    try:BrowserCookieSource("edge",firefox_container="Personal")
    except ValueError:pass
    else:raise AssertionError("Firefox container accepted for Edge")


def test_cookie_settings_are_opt_in(tmp_path):
    settings=QSettings(str(tmp_path/"cookies.ini"),QSettings.IniFormat)
    settings.setValue("cookies/browser","chrome")
    assert cookie_source_from_settings(settings) is None
    settings.setValue("cookies/enabled",True);settings.setValue("cookies/profile","Profile 2")
    assert cookie_source_from_settings(settings)==BrowserCookieSource("chrome","Profile 2")


def test_cookie_option_reaches_analysis_estimation_and_download_options(tmp_path):
    service=YTDLPService(logging.getLogger("test"));source=BrowserCookieSource("edge","Default");service.set_cookie_source(source)
    assert service.base_options()["cookiesfrombrowser"]==source.as_ytdlp_tuple()
    assert service.base_options()["extractor_args"]["youtube"]["player_client"]==["default","web_embedded"]
    request=DownloadRequest("https://example.com","Example",str(tmp_path))
    assert service.build_options(request)["cookiesfrombrowser"]==source.as_ytdlp_tuple()
    service.set_cookie_source(None)
    assert "cookiesfrombrowser" not in service.base_options()


def test_complete_cookie_and_authorization_headers_are_redacted():
    value=redact("Cookie: SID=secret; session=also-secret\nAuthorization: Bearer token-value\nSafe: visible")
    assert "secret" not in value and "token-value" not in value and "Safe: visible" in value


def test_valid_netscape_cookie_file_and_manual_mode(tmp_path):
    cookie_file=tmp_path/"cookies.txt"
    cookie_file.write_text("# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tTRUE\t2147483647\tSID\tsecret\n#HttpOnly_.example.com\tTRUE\t/\tFALSE\t0\tSESSION\tsecret2\n",encoding="utf-8")
    report=validate_netscape_cookie_file(cookie_file)
    assert report.valid and report.cookie_count==2 and "secret" not in report.error
    settings=QSettings(str(tmp_path/"manual.ini"),QSettings.IniFormat);settings.setValue("cookies/enabled",True);settings.setValue("cookies/mode","file");settings.setValue("cookies/file",str(cookie_file));settings.setValue("cookies/browser","chrome")
    assert cookie_file_from_settings(settings)==str(cookie_file.resolve())
    assert cookie_source_from_settings(settings) is None


def test_invalid_netscape_cookie_files_are_rejected(tmp_path):
    wrong_extension=tmp_path/"cookies.json";wrong_extension.write_text("{}",encoding="utf-8")
    assert not validate_netscape_cookie_file(wrong_extension).valid
    malformed=tmp_path/"cookies.txt";malformed.write_text("# Netscape HTTP Cookie File\nonly\tthree\tfields\n",encoding="utf-8")
    report=validate_netscape_cookie_file(malformed)
    assert not report.valid and "line 2" in report.error


def test_service_uses_exactly_one_cookie_source(tmp_path):
    cookie_file=tmp_path/"cookies.txt";cookie_file.write_text("# Netscape HTTP Cookie File\n.example.com\tTRUE\t/\tTRUE\t0\tSID\tsecret\n",encoding="utf-8")
    service=YTDLPService(logging.getLogger("test"));service.set_cookie_source(BrowserCookieSource("chrome"));service.set_cookie_file(str(cookie_file));options=service.base_options()
    assert options["cookiefile"]==str(cookie_file) and "cookiesfrombrowser" not in options
    service.set_cookie_source(BrowserCookieSource("edge"));options=service.base_options()
    assert options["cookiesfrombrowser"][0]=="edge" and "cookiefile" not in options


def test_manual_cookie_file_enables_authenticated_youtube_clients(tmp_path):
    cookie_file=tmp_path/"cookies.txt";cookie_file.write_text("# Netscape HTTP Cookie File\n.youtube.com\tTRUE\t/\tTRUE\t0\tSAPISID\tsecret\n",encoding="utf-8")
    service=YTDLPService(logging.getLogger("test"));service.set_cookie_file(str(cookie_file));options=service.base_options()
    assert options["cookiefile"]==str(cookie_file)
    assert options["extractor_args"]["youtube"]["player_client"]==["default","web_embedded"]


def test_unauthenticated_requests_keep_ytdlp_default_clients():
    service=YTDLPService(logging.getLogger("test"))
    assert "extractor_args" not in service.base_options()
