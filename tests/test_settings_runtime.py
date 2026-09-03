import logging
from PySide6.QtCore import QSettings
from services.ytdlp_service import YTDLPService


def test_network_download_and_advanced_settings_reach_ytdlp(tmp_path):
    settings=QSettings(str(tmp_path/"runtime.ini"),QSettings.IniFormat)
    values={"network/proxy":"socks5://127.0.0.1:1080","network/timeout":45,"network/retries":8,"network/fragment_retries":9,"network/fragments":4,"network/rate_limit_kib":512,"network/ip_family":"IPv4","downloads/overwrite":True,"downloads/keep_fragments":True,"advanced/restrict_filenames":True,"advanced/use_cache":False,"ytdlp/prefer_free_formats":True}
    for key,value in values.items():settings.setValue(key,value)
    service=YTDLPService(logging.getLogger("test"));service.configure(settings);options=service.base_options()
    assert options["proxy"]==values["network/proxy"]
    assert options["socket_timeout"]==45 and options["retries"]==8 and options["fragment_retries"]==9
    assert options["concurrent_fragment_downloads"]==4 and options["ratelimit"]==512*1024
    assert options["source_address"]=="0.0.0.0"
    assert options["overwrites"] and options["keep_fragments"] and options["restrictfilenames"]
    assert options["cachedir"] is False and options["prefer_free_formats"]


def test_subtitle_and_playlist_settings(tmp_path):
    settings=QSettings(str(tmp_path/"runtime.ini"),QSettings.IniFormat)
    settings.setValue("subtitles/languages","id, en");settings.setValue("subtitles/automatic",False);settings.setValue("subtitles/embed",True);settings.setValue("subtitles/format","srt");settings.setValue("ytdlp/flat_playlist",False)
    service=YTDLPService(logging.getLogger("test"));service.configure(settings)
    assert service.subtitle_options=={"subtitleslangs":["id","en"],"writesubtitles":True,"writeautomaticsub":False,"embedsubtitles":True,"subtitlesformat":"srt"}
    assert service.flat_playlist is False


def test_extended_runtime_settings(tmp_path):
    settings=QSettings(str(tmp_path/"extended.ini"),QSettings.IniFormat)
    values={"downloads/max_filename":120,"downloads/temp_folder":str(tmp_path),"video/multiple_streams":True,"audio/multiple_streams":True,"network/http_chunk_kib":2048,"network/sleep_interval":2,"ffmpeg/preserve_timestamps":False,"ytdlp/check_formats":True,"ytdlp/extractor_retries":6,"ytdlp/ignore_playlist_errors":False,"advanced/use_part_files":False,"advanced/write_description":True,"advanced/write_xattrs":True,"subtitles/manual":False}
    for key,value in values.items():settings.setValue(key,value)
    service=YTDLPService(logging.getLogger("test"));service.configure(settings);options=service.base_options()
    assert options["trim_file_name"]==120 and options["paths"]["temp"]==str(tmp_path)
    assert options["allow_multiple_video_streams"] and options["allow_multiple_audio_streams"]
    assert options["http_chunk_size"]==2048*1024 and options["sleep_interval"]==2
    assert options["updatetime"] is False and options["check_formats"] is True and options["extractor_retries"]==6
    assert options["ignoreerrors"] is False and options["nopart"] is True and options["writedescription"] and options["xattrs"]
    assert service.subtitle_options["writesubtitles"] is False


def test_second_wave_runtime_settings(tmp_path):
    settings=QSettings(str(tmp_path/"second.ini"),QSettings.IniFormat)
    values={"downloads/archive":str(tmp_path/"archive.txt"),"network/user_agent":"Downloader-Test/1.0","network/geo_bypass":False,"subtitles/convert":"srt","ffmpeg/threads":4,"ytdlp/show_warnings":False}
    for key,value in values.items():settings.setValue(key,value)
    service=YTDLPService(logging.getLogger("test"));service.configure(settings);options=service.base_options()
    assert options["download_archive"]==values["downloads/archive"]
    assert options["http_headers"]["User-Agent"]==values["network/user_agent"] and options["geo_bypass"] is False
    assert options["no_warnings"] is True and service.subtitle_options["convertsubtitles"]=="srt" and service.ffmpeg_threads==4
