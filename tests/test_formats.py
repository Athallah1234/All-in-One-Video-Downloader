from utils.formats import AUDIO_CODEC_PRESETS,BIT_DEPTH_PRESETS,CODEC_PRESETS,DYNAMIC_RANGE_PRESETS,FPS_PRESETS,RESOLUTION_PRESETS,available_audio_codec_counts,available_bit_depth_counts,available_codec_counts,available_dynamic_range_counts,available_fps_counts,available_resolution_counts,build_explicit_bit_depth_selector,build_explicit_video_selector,build_resolution_selector,build_video_selector,detect_bit_depth,dynamic_range_filter,dynamic_range_matches,fps_filter,normalize_audio_codec,normalize_dynamic_range,normalize_frame_rate,normalize_video_codec

def test_all_requested_resolution_presets_exist():
    assert [height for _label,height in RESOLUTION_PRESETS]==[None,144,240,360,480,720,1080,1440,2160,4320]

def test_resolution_availability_ignores_audio_formats():
    counts=available_resolution_counts([{"height":720,"vcodec":"avc1"},{"height":720,"vcodec":"vp9"},{"height":1080,"vcodec":"none"},{"height":2160,"vcodec":"av01"}])
    assert counts[720]==2 and counts[1080]==0 and counts[2160]==1

def test_exact_video_audio_selector():
    assert build_resolution_selector(1080)=="bestvideo[height=1080]+bestaudio/best[height=1080]"

def test_playlist_uses_maximum_height_fallback():
    assert build_resolution_selector(2160,maximum=True)=="bestvideo[height<=2160]+bestaudio/best[height<=2160]"

def test_video_only_never_falls_back_to_audio_format():
    assert build_resolution_selector(720,video_only=True)=="bestvideo[height=720]"

def test_requested_codec_presets_exist():
    assert [codec for _label,codec in CODEC_PRESETS]==[None,"h264","h265","vp9","av1"]

def test_codec_name_normalization():
    assert normalize_video_codec("avc1.640028")=="h264"
    assert normalize_video_codec("hvc1.2.4.L153")=="h265"
    assert normalize_video_codec("vp09.00.51.08")=="vp9"
    assert normalize_video_codec("av01.0.08M.08")=="av1"
    assert normalize_video_codec("none") is None

def test_codec_counts_can_be_filtered_by_resolution():
    formats=[{"height":1080,"vcodec":"avc1.640028"},{"height":1080,"vcodec":"vp09"},{"height":2160,"vcodec":"av01"}]
    counts=available_codec_counts(formats,1080)
    assert counts=={"h264":1,"h265":0,"vp9":1,"av1":0}

def test_explicit_codec_selector_and_video_only():
    selector=build_video_selector(1080,"h264")
    assert "height=1080" in selector and "avc1|avc|h264" in selector and "+bestaudio" in selector
    video_only=build_video_selector(None,"av1",video_only=True)
    assert video_only.startswith("bestvideo") and "+bestaudio" not in video_only and "av01|av1" in video_only

def test_requested_audio_codec_presets_exist():
    assert [codec for _label,codec in AUDIO_CODEC_PRESETS]==[None,"aac","opus","vorbis","mp3","flac"]

def test_audio_codec_normalization_and_counts():
    assert normalize_audio_codec("mp4a.40.2")=="aac"
    assert normalize_audio_codec("opus")=="opus"
    assert normalize_audio_codec("vorbis")=="vorbis"
    assert normalize_audio_codec("mp3")=="mp3"
    assert normalize_audio_codec("flac")=="flac"
    counts=available_audio_codec_counts([{"acodec":"mp4a.40.2"},{"acodec":"aac"},{"acodec":"opus"},{"acodec":"none"}])
    assert counts=={"aac":2,"opus":1,"vorbis":0,"mp3":0,"flac":0}

def test_explicit_source_audio_codec_selector():
    selector=build_video_selector(1080,"h264","aac")
    assert "acodec~='^(?:mp4a|aac)'" in selector and "+bestaudio[" in selector
    assert "acodec" not in build_video_selector(1080,"h264",None,video_only=True)

def test_frame_rate_presets_are_comprehensive():
    assert [fps for _label,fps in FPS_PRESETS]==[None,24,25,30,48,50,60,100,120,144,240]

def test_fractional_frame_rates_map_to_standard_family():
    assert normalize_frame_rate(23.976)==24
    assert normalize_frame_rate(29.97)==30
    assert normalize_frame_rate(59.94)==60
    assert normalize_frame_rate(119.88)==120
    assert normalize_frame_rate(None) is None

def test_fps_availability_respects_resolution_and_codec():
    formats=[{"height":1080,"vcodec":"avc1","fps":29.97},{"height":1080,"vcodec":"vp09","fps":60},{"height":2160,"vcodec":"avc1","fps":60}]
    counts=available_fps_counts(formats,1080,"h264")
    assert counts[30]==1 and counts[60]==0

def test_frame_rate_selector_uses_safe_fractional_range():
    assert fps_filter(30)=="[fps>=29.5][fps<30.5]"
    selector=build_video_selector(1080,"h264","aac",fps=60)
    assert "[fps>=59.5][fps<60.5]" in selector
    assert "+bestaudio" in selector

def test_bit_depth_presets_exist():
    assert [depth for _label,depth in BIT_DEPTH_PRESETS]==[None,8,10,12]

def test_bit_depth_detection_uses_strong_evidence():
    assert detect_bit_depth({"bit_depth":12})==(12,"explicit")
    assert detect_bit_depth({"vcodec":"av01.0.08M.10"})==(10,"codec")
    assert detect_bit_depth({"vcodec":"vp09.02.10.12"})==(12,"codec")
    assert detect_bit_depth({"vcodec":"hev1.2.4.L153.B0"})==(10,"profile")
    assert detect_bit_depth({"vcodec":"avc1.640028"})==(8,"profile")
    assert detect_bit_depth({"vcodec":"unknown","dynamic_range":"DV"})==(None,"unknown")
    assert detect_bit_depth({"vcodec":"unknown","dynamic_range":"HDR10"})==(10,"dynamic-range")

def test_bit_depth_counts_respect_other_video_filters():
    formats=[{"height":1080,"vcodec":"av01.0.08M.10","fps":60},{"height":1080,"vcodec":"avc1","fps":30},{"height":2160,"vcodec":"av01.0.08M.10","fps":60}]
    counts=available_bit_depth_counts(formats,1080,"av1",60)
    assert counts=={8:0,10:1,12:0}

def test_explicit_bit_depth_uses_matching_format_id():
    formats=[{"format_id":"av1-8","height":1080,"vcodec":"av01.0.08M.08","acodec":"none","fps":60,"tbr":1000},{"format_id":"av1-10","height":1080,"vcodec":"av01.0.08M.10","acodec":"none","fps":60,"tbr":2000}]
    selector=build_explicit_bit_depth_selector(formats,10,1080,"av1",60,"opus",False)
    assert selector=="av1-10+bestaudio[acodec~='^opus']"
    assert build_explicit_bit_depth_selector(formats,12,1080,"av1",60,None,False) is None

def test_video_only_bit_depth_selector_has_no_audio():
    formats=[{"format_id":"hevc10","height":2160,"vcodec":"hev1.2.4.L153","acodec":"none","fps":30}]
    assert build_explicit_bit_depth_selector(formats,10,2160,"h265",30,None,True)=="hevc10"

def test_dynamic_range_presets_cover_hdr_and_dolby_vision():
    assert [value for _label,value in DYNAMIC_RANGE_PRESETS]==[None,"HDR","SDR","HDR10","HDR10+","HDR12","HLG","DV"]

def test_dynamic_range_normalization_and_matching():
    assert normalize_dynamic_range("Dolby Vision")=="DV"
    assert normalize_dynamic_range(None)=="SDR"
    assert dynamic_range_matches("HDR10+","HDR")
    assert not dynamic_range_matches("SDR","HDR")

def test_dynamic_range_counts_respect_video_filters():
    formats=[{"height":2160,"vcodec":"av01.0.08M.10","fps":60,"dynamic_range":"HDR10"},{"height":2160,"vcodec":"dvhe.05.06","fps":60,"dynamic_range":"DV"},{"height":1080,"vcodec":"avc1","fps":30,"dynamic_range":"SDR"}]
    counts=available_dynamic_range_counts(formats,2160,None,60,None)
    assert counts["HDR"]==2 and counts["HDR10"]==1 and counts["DV"]==1 and counts["SDR"]==0

def test_exact_dolby_vision_selector():
    formats=[{"format_id":"dv-2160","height":2160,"vcodec":"dvhe.05.06","acodec":"none","fps":60,"dynamic_range":"DV"},{"format_id":"hdr10","height":2160,"vcodec":"hev1.2.4","acodec":"none","fps":60,"dynamic_range":"HDR10"}]
    assert build_explicit_video_selector(formats,2160,"h265",60,None,"DV","aac",False)=="dv-2160+bestaudio[acodec~='^(?:mp4a|aac)']"

def test_playlist_hdr_filter_is_strict():
    assert dynamic_range_filter("HDR")=="[dynamic_range!='SDR']"
    selector=build_video_selector(2160,"h265","aac",maximum=True,fps=60,dynamic_range="HDR10+")
    assert "[dynamic_range='HDR10+']" in selector
