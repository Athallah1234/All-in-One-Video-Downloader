from models.download import DownloadRequest
from utils.duplicates import canonicalize_url,find_duplicates,media_identity

def queued(url,items=None,identity=None):
    request=DownloadRequest(url,"Title",".",playlist_items=items or [])
    return {"request":request,"canonical_url":canonicalize_url(url),"media_identity":identity}

def test_canonical_url_normalizes_safe_components():
    first="HTTPS://Exämple.com:443/watch/?b=2&utm_source=x&a=1#chapter"
    second="https://xn--exmple-cua.com/watch?a=1&b=2"
    assert canonicalize_url(first)==canonicalize_url(second)

def test_exact_single_url_duplicate():
    report=find_duplicates([queued("https://example.com/v?id=1")],"https://EXAMPLE.com/v?id=1#x",{"id":"1"},[])
    assert report.exact and report.matching_rows==(0,)

def test_media_identity_detects_alias_url():
    identity=("youtube","abc"); queue=[queued("https://youtu.be/abc",identity=identity)]
    report=find_duplicates(queue,"https://www.youtube.com/watch?v=abc",{"extractor_key":"Youtube","id":"abc"},[])
    assert report.exact and report.matching_rows==(0,)

def test_playlist_overlap_and_new_items():
    queue=[queued("https://example.com/list",[1,2,3]),queued("https://example.com/list",[5])]
    report=find_duplicates(queue,"https://example.com/list",{"id":"list"},[2,3,4,5,6])
    assert report.overlapping_items==(2,3,5)
    assert report.new_items==(4,6)
    assert not report.exact

def test_disjoint_playlist_selection_is_not_content_duplicate():
    report=find_duplicates([queued("https://example.com/list",[1,2])],"https://example.com/list",{},[3,4])
    assert report.matching_rows==(0,) and report.overlapping_items==() and report.new_items==(3,4)

def test_media_identity_requires_both_parts():
    assert media_identity({"extractor":"youtube","id":"abc"})==("youtube","abc")
    assert media_identity({"id":"abc"}) is None

