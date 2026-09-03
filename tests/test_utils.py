from utils.formatters import format_duration,format_size
from utils.validators import is_valid_url,parse_batch_urls,validate_output_template

def test_url_validation():
    assert is_valid_url("https://example.com/watch?v=1")
    assert not is_valid_url("javascript:alert(1)")
    assert not is_valid_url("https://bad host")

def test_formatters():
    assert format_size(1024)=="1.00 KB"
    assert format_size(None)=="—"
    assert format_duration(3661)=="1:01:01"

def test_template_validation():
    assert validate_output_template("%(title)s.%(ext)s")
    assert not validate_output_template("plain-name.mp4")

def test_batch_url_parsing():
    urls,invalid,duplicates=parse_batch_urls("# list\nHTTPS://Example.com/A\nhttps://example.com/A\nnot-a-url\nhttps://example.com/B\n")
    assert urls==["HTTPS://Example.com/A","https://example.com/B"]
    assert invalid==["not-a-url"]
    assert duplicates==1

