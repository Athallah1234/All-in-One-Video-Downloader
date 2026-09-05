from pathlib import Path
from threading import Event
from typing import Any, Callable
import yt_dlp
from models.download import DownloadRequest
from services.integrity_service import IntegrityService
from services.cookie_service import BrowserCookieSource

class DownloadCancelled(Exception): pass

class YTDLPLogger:
    def __init__(self, logger): self.logger=logger
    def debug(self,msg):
        if not str(msg).startswith("[debug]"): self.logger.debug(msg)
    def info(self,msg): self.logger.info(msg)
    def warning(self,msg): self.logger.warning(msg)
    def error(self,msg): self.logger.error(msg)

class YTDLPService:
    def __init__(self, logger): self.logger=logger;self.integrity=IntegrityService(logger);self.cookie_source:BrowserCookieSource|None=None;self.cookie_file:str|None=None;self.runtime_options={};self.flat_playlist=True;self.channel_analysis_limit=500;self.subtitle_options={};self.ffmpeg_threads=0
    def configure(self,settings) -> None:
        def enabled(key,default=False):return str(settings.value(key,default)).lower() in {"true","1","yes"}
        def number(key,default):
            try:return int(settings.value(key,default))
            except (TypeError,ValueError):return default
        proxy=str(settings.value("network/proxy","") or "").strip()
        self.runtime_options={
            "retries":number("network/retries",3),"fragment_retries":number("network/fragment_retries",3),
            "socket_timeout":number("network/timeout",20),"concurrent_fragment_downloads":number("network/fragments",1),
            "overwrites":enabled("downloads/overwrite",False),"keep_fragments":enabled("downloads/keep_fragments",False),
            "restrictfilenames":enabled("advanced/restrict_filenames",False),"cachedir":None if enabled("advanced/use_cache",True) else False,
            "nopart":not enabled("advanced/use_part_files",True),"writedescription":enabled("advanced/write_description",False),"xattrs":enabled("advanced/write_xattrs",False),
            "trim_file_name":number("downloads/max_filename",180),"allow_multiple_video_streams":enabled("video/multiple_streams",False),"allow_multiple_audio_streams":enabled("audio/multiple_streams",False),
            "updatetime":enabled("ffmpeg/preserve_timestamps",True),"check_formats":enabled("ytdlp/check_formats",False),"extractor_retries":number("ytdlp/extractor_retries",3),"ignoreerrors":"only_download" if enabled("ytdlp/ignore_playlist_errors",True) else False,
            "no_warnings":not enabled("ytdlp/show_warnings",True),"geo_bypass":enabled("network/geo_bypass",True),
        }
        rate=number("network/rate_limit_kib",0)
        if proxy:self.runtime_options["proxy"]=proxy
        user_agent=str(settings.value("network/user_agent","") or "").strip()
        if user_agent:self.runtime_options["http_headers"]={"User-Agent":user_agent}
        if rate>0:self.runtime_options["ratelimit"]=rate*1024
        chunk=number("network/http_chunk_kib",0);sleep=number("network/sleep_interval",0);temp=str(settings.value("downloads/temp_folder","") or "").strip()
        if chunk>0:self.runtime_options["http_chunk_size"]=chunk*1024
        if sleep>0:self.runtime_options["sleep_interval"]=sleep
        if temp:self.runtime_options["paths"]={"temp":temp}
        archive=str(settings.value("downloads/archive","") or "").strip()
        if archive:self.runtime_options["download_archive"]=archive
        family=str(settings.value("network/ip_family","Auto"))
        if family=="IPv4":self.runtime_options["source_address"]="0.0.0.0"
        elif family=="IPv6":self.runtime_options["source_address"]="::"
        if enabled("ytdlp/prefer_free_formats",False):self.runtime_options["prefer_free_formats"]=True
        backend=str(settings.value("downloads/backend","Native"))
        if backend=="aria2c":
            from services.aria2_service import Aria2Service
            try:self.runtime_options.update(Aria2Service.build_options(str(settings.value("downloads/aria2_location","") or ""),number("downloads/aria2_connections",16),number("downloads/aria2_split",16),number("downloads/aria2_min_split_mib",1),number("downloads/aria2_max_tries",5),number("downloads/aria2_retry_wait",1),number("downloads/aria2_timeout",20),str(settings.value("downloads/aria2_file_allocation","none")),enabled("downloads/aria2_fragments",False)));self.logger.info("aria2c external download backend enabled")
            except ValueError as exc:self.logger.error("aria2c backend disabled: %s",exc)
        self.flat_playlist=enabled("ytdlp/flat_playlist",True)
        self.channel_analysis_limit=number("ytdlp/channel_analysis_limit",500)
        languages=[value.strip() for value in str(settings.value("subtitles/languages","all")).split(",") if value.strip()]
        subtitle_format=str(settings.value("subtitles/format","best"));convert=str(settings.value("subtitles/convert","none"))
        self.subtitle_options={"subtitleslangs":languages or ["all"],"writesubtitles":enabled("subtitles/manual",True),"writeautomaticsub":enabled("subtitles/automatic",True),"embedsubtitles":enabled("subtitles/embed",False),"subtitlesformat":subtitle_format}
        if convert!="none":self.subtitle_options["convertsubtitles"]=convert
        self.ffmpeg_threads=number("ffmpeg/threads",0)
    def set_cookie_source(self,source:BrowserCookieSource|None) -> None:
        self.cookie_source=source;self.cookie_file=None if source else self.cookie_file
        self.logger.info("Browser cookies %s",f"enabled for {source.browser}" if source else "disabled")
    def set_cookie_file(self,path:str|None) -> None:
        self.cookie_file=path;self.cookie_source=None if path else self.cookie_source
        self.logger.info("Manual Netscape cookie file %s","enabled" if path else "disabled")
    def base_options(self) -> dict[str,Any]:
        opts={"quiet":True,"no_warnings":False,"logger":YTDLPLogger(self.logger),"noplaylist":False}|self.runtime_options
        if self.cookie_file:opts["cookiefile"]=self.cookie_file
        elif self.cookie_source:opts["cookiesfrombrowser"]=self.cookie_source.as_ytdlp_tuple()
        if self.cookie_file or self.cookie_source:
            # Logged-in YouTube's current default tv client can return "The
            # page needs to be reloaded" and fail age-gated extraction. Keep
            # the normal client set and add the cookie-compatible embedded web
            # fallback recommended by yt-dlp for authenticated requests.
            extractor_args=dict(opts.get("extractor_args") or {})
            youtube_args=dict(extractor_args.get("youtube") or {})
            youtube_args.setdefault("player_client",["default","web_embedded"])
            extractor_args["youtube"]=youtube_args
            opts["extractor_args"]=extractor_args
        return opts
    @staticmethod
    def merge_extractor_args(defaults:dict|None,custom:dict|None) -> dict:
        merged={name:{key:list(values) for key,values in arguments.items()} for name,arguments in (defaults or {}).items()}
        for name,arguments in (custom or {}).items():merged.setdefault(name,{}).update({key:list(values) for key,values in arguments.items()})
        return merged
    def extract_info(self,url: str,extractor_args:dict|None=None) -> dict[str,Any]:
        opts=self.base_options()|{"skip_download":True,"extract_flat":"in_playlist" if self.flat_playlist else False,"allow_unplayable_formats":True}
        from utils.channels import looks_like_channel_url,is_channel_info
        channel_hint=looks_like_channel_url(url)
        if channel_hint and self.channel_analysis_limit>0:opts["playlistend"]=self.channel_analysis_limit
        if extractor_args:opts["extractor_args"]=self.merge_extractor_args(opts.get("extractor_args"),extractor_args)
        with yt_dlp.YoutubeDL(opts) as ydl:result=ydl.extract_info(url,download=False)
        if isinstance(result,dict) and (channel_hint or is_channel_info(result,url)):
            entries=result.get("entries");loaded=len(entries) if isinstance(entries,list) else 0;advertised=result.get("playlist_count") or result.get("channel_follower_count")
            result["_app_is_channel"]=True;result["_app_channel_loaded"]=loaded;result["_app_channel_limit"]=self.channel_analysis_limit;result["_app_channel_truncated"]=bool(self.channel_analysis_limit and loaded>=self.channel_analysis_limit and (not isinstance(advertised,int) or advertised>loaded))
        if isinstance(result,dict) and isinstance(result.get("formats"),list):
            from utils.drm import drm_report
            result["_app_drm_report"]=drm_report(result["formats"])
        if not isinstance(result,dict):raise RuntimeError("yt-dlp returned no metadata for this URL")
        return result
    @staticmethod
    def wait_while_paused(pause: Event, cancel: Event, pause_changed: Callable[[bool],None]) -> None:
        if not pause.is_set(): return
        pause_changed(True)
        while pause.is_set():
            if cancel.wait(0.1): raise DownloadCancelled("Download cancelled")
        pause_changed(False)

    def download(self, request: DownloadRequest, progress: Callable[[dict],None], postprocess: Callable[[dict],None], cancel: Event, pause: Event, pause_changed: Callable[[bool],None]) -> dict:
        selected_positions={index: position for position,index in enumerate(request.playlist_items,1)}
        observed_paths=set()
        def hook(data):
            if cancel.is_set(): raise DownloadCancelled("Download cancelled")
            if data.get("filename"):observed_paths.add(str(data["filename"]))
            if request.playlist_items:
                info=data.get("info_dict") or {}
                try: playlist_index=int(info.get("playlist_index"))
                except (TypeError,ValueError): playlist_index=None
                data=dict(data)
                data["selected_item_position"]=selected_positions.get(playlist_index)
                data["selected_item_count"]=len(request.playlist_items)
            progress(data)
            self.wait_while_paused(pause,cancel,pause_changed)
        def postprocess_hook(data):
            if cancel.is_set(): raise DownloadCancelled("Download cancelled")
            post_info=data.get("info_dict") or {}
            for key in ("filepath","_filename"):
                if post_info.get(key):observed_paths.add(str(post_info[key]))
            self.wait_while_paused(pause,cancel,pause_changed)
            postprocess(data)
        opts=self.build_options(request)|{"progress_hooks":[hook],"postprocessor_hooks":[postprocess_hook]}
        with yt_dlp.YoutubeDL(opts) as ydl:
            if request.custom_video_filter or request.custom_audio_filter:
                from services.custom_ffmpeg_filter import CustomFFmpegFilterPP
                ydl.add_post_processor(CustomFFmpegFilterPP(ydl,request.custom_video_filter,request.custom_audio_filter,request.custom_video_encoder,request.custom_audio_encoder,self.ffmpeg_threads),when="post_process")
            result=ydl.extract_info(request.url,download=True)
        if not isinstance(result,dict):raise RuntimeError("yt-dlp returned no download result; every selected item may have failed or become unavailable")
        result["_observed_output_paths"]=sorted(observed_paths)
        return result
    def build_options(self,r: DownloadRequest) -> dict[str,Any]:
        out=str(Path(r.folder) / r.output_template)
        keep_audio_cover=r.download_type=="Audio Only" and r.audio_keep_thumbnail;keep_video_poster=r.download_type in {"Video","Video Only"} and r.video_keep_thumbnail;opts=self.base_options()|{"outtmpl":out,"format":r.format_selector,"continuedl":True,"windowsfilenames":True,"allow_unplayable_formats":False,"writethumbnail":r.embed_thumbnail or keep_audio_cover or keep_video_poster,"writeinfojson":r.write_info_json,"addmetadata":r.embed_metadata}
        from services.ffmpeg_service import FFmpegService
        if FFmpegService._location:opts["ffmpeg_location"]=FFmpegService._location
        if r.extractor_args:opts["extractor_args"]=self.merge_extractor_args(opts.get("extractor_args"),r.extractor_args)
        if self.ffmpeg_threads:opts["postprocessor_args"]={"ffmpeg_o":["-threads",str(self.ffmpeg_threads)]}
        if r.playlist_items:
            opts["playlist_items"]=",".join(str(index) for index in r.playlist_items)
        if r.output_container!="auto" and r.download_type in {"Video","Video Only"}:
            opts["merge_output_format"]=r.output_container
            opts.setdefault("postprocessors",[]).append({"key":"FFmpegVideoRemuxer","preferedformat":r.output_container})
        if r.download_type in {"Video","Video Only"}:
            if r.video_thumbnail_format not in {"auto","jpg","png","webp"}:raise ValueError("Unsupported video thumbnail conversion format")
            if r.embed_thumbnail and r.output_container in {"webm","avi"}:raise ValueError(f"Thumbnail embedding is not supported for {r.output_container.upper()} output")
            processors=opts.setdefault("postprocessors",[])
            if (r.embed_thumbnail or keep_video_poster) and r.video_thumbnail_format!="auto":processors.insert(0,{"key":"FFmpegThumbnailsConvertor","format":r.video_thumbnail_format,"when":"before_dl"})
            if r.embed_metadata or r.video_embed_chapters or r.video_embed_infojson:processors.append({"key":"FFmpegMetadata","add_metadata":r.embed_metadata,"add_chapters":r.video_embed_chapters,"add_infojson":True if r.video_embed_infojson else False})
            if r.embed_thumbnail:processors.append({"key":"EmbedThumbnail","already_have_thumbnail":r.video_keep_thumbnail})
        if r.download_type == "Audio Only":
            preferred=r.audio_codec if r.audio_codec!="auto" else r.audio_format
            if r.audio_thumbnail_format not in {"auto","jpg","png","webp"}:raise ValueError("Unsupported audio thumbnail conversion format")
            if r.embed_thumbnail and preferred not in {"mp3","m4a","flac","opus"}:raise ValueError(f"Cover art embedding is not supported for {preferred.upper()} output")
            processors=[]
            if (r.embed_thumbnail or keep_audio_cover) and r.audio_thumbnail_format!="auto":processors.append({"key":"FFmpegThumbnailsConvertor","format":r.audio_thumbnail_format,"when":"before_dl"})
            processors.append({"key":"FFmpegExtractAudio","preferredcodec":preferred,"preferredquality":r.audio_quality})
            if r.embed_metadata or r.audio_embed_chapters or r.audio_embed_infojson:processors.append({"key":"FFmpegMetadata","add_metadata":r.embed_metadata,"add_chapters":r.audio_embed_chapters,"add_infojson":True if r.audio_embed_infojson else False})
            if r.embed_thumbnail:processors.append({"key":"EmbedThumbnail","already_have_thumbnail":r.audio_keep_thumbnail})
            opts["format"]="bestaudio/best"; opts["postprocessors"]=processors
            filters=[]
            if r.audio_sample_rate:filters.extend(["-ar",str(r.audio_sample_rate)])
            if r.audio_channels:filters.extend(["-ac",str(r.audio_channels)])
            if self.ffmpeg_threads:filters.extend(["-threads",str(self.ffmpeg_threads)])
            if filters:opts["postprocessor_args"]={"FFmpegExtractAudio+ffmpeg_o":filters}
        elif r.download_type == "Video Only": opts["format"]=r.format_selector if "+" not in r.format_selector else "bestvideo"
        elif r.download_type == "Thumbnail Only": opts.update({"skip_download":True,"writethumbnail":True})
        elif r.download_type == "Subtitle Only": opts.update({"skip_download":True,"writesubtitles":True}|self.subtitle_options)
        elif r.download_type == "Metadata Only": opts.update({"skip_download":True,"writeinfojson":True})
        if r.subtitles: opts.update({"writesubtitles":True}|self.subtitle_options)
        if r.sponsorblock_enabled:
            from utils.sponsorblock import validate_sponsorblock
            report=validate_sponsorblock(r.sponsorblock_mark,r.sponsorblock_remove,r.sponsorblock_api,r.sponsorblock_chapter_title)
            if not report.valid:raise ValueError(f"Invalid SponsorBlock configuration: {report.error}")
            categories=set(r.sponsorblock_mark)|set(r.sponsorblock_remove)
            if categories:
                processors=opts.setdefault("postprocessors",[])
                processors.insert(0,{"key":"SponsorBlock","categories":categories,"api":r.sponsorblock_api.rstrip("/"),"when":"after_filter"})
                modify={"key":"ModifyChapters","remove_chapters_patterns":[],"remove_sponsor_segments":set(r.sponsorblock_remove),"remove_ranges":[],"sponsorblock_chapter_title":r.sponsorblock_chapter_title,"force_keyframes":r.sponsorblock_force_keyframes}
                insertion=next((index for index,item in enumerate(processors) if item.get("key") in {"FFmpegMetadata","EmbedThumbnail"}),len(processors))
                processors.insert(insertion,modify)
                if r.sponsorblock_mark:
                    metadata=next((item for item in processors if item.get("key")=="FFmpegMetadata"),None)
                    if metadata:metadata["add_chapters"]=True
                    else:processors.append({"key":"FFmpegMetadata","add_metadata":False,"add_chapters":True,"add_infojson":False})
        return opts

    @staticmethod
    def _format_bytes(format_info: dict,duration: int | float | None=None) -> tuple[int | None, bool]:
        exact=format_info.get("filesize")
        if isinstance(exact,(int,float)) and exact>0:return int(exact),True
        approximate=format_info.get("filesize_approx")
        if isinstance(approximate,(int,float)) and approximate>0:return int(approximate),False
        bitrate=format_info.get("tbr") or format_info.get("vbr") or format_info.get("abr")
        seconds=format_info.get("duration") or duration
        if isinstance(bitrate,(int,float)) and bitrate>0 and isinstance(seconds,(int,float)) and seconds>0:
            return int(bitrate*1000/8*seconds),False
        return None,False

    @classmethod
    def estimate_info_size(cls,info: dict) -> dict[str,Any]:
        """Estimate selected source bytes from a processed yt-dlp info dict."""
        if not info:return {"bytes":None,"confidence":"unknown","known_items":0,"total_items":0}
        entries=info.get("entries")
        if entries is not None:
            entries=list(entries); results=[cls.estimate_info_size(entry or {}) for entry in entries]
            known=[result for result in results if result.get("bytes") is not None]
            if not known:return {"bytes":None,"confidence":"unknown","known_items":0,"total_items":len(entries)}
            confidence="exact" if len(known)==len(entries) and all(result["confidence"]=="exact" for result in known) else ("approximate" if len(known)==len(entries) else "partial")
            return {"bytes":sum(result["bytes"] for result in known),"confidence":confidence,"known_items":len(known),"total_items":len(entries)}
        selected=info.get("requested_downloads") or info.get("requested_formats")
        if isinstance(selected,list) and selected:
            values=[cls._format_bytes(fmt or {},info.get("duration")) for fmt in selected]; known=[value for value in values if value[0] is not None]
            if known:return {"bytes":sum(value[0] for value in known),"confidence":"exact" if len(known)==len(values) and all(value[1] for value in known) else ("approximate" if len(known)==len(values) else "partial"),"known_items":len(known),"total_items":len(values)}
        size,exact=cls._format_bytes(info,info.get("duration"))
        return {"bytes":size,"confidence":"exact" if exact else ("approximate" if size is not None else "unknown"),"known_items":1 if size is not None else 0,"total_items":1}

    def estimate_download_size(self,request: DownloadRequest) -> dict[str,Any]:
        if request.download_type in {"Thumbnail Only","Subtitle Only","Metadata Only"}:
            return {"bytes":None,"confidence":"unknown","known_items":0,"total_items":1,"note":"Auxiliary output size is not advertised by the source"}
        opts=self.build_options(request)
        # Estimation selects formats and metadata only. Conversion output may
        # differ, so audio/transcode results are always presented as estimates.
        opts.pop("postprocessors",None)
        opts.update({"skip_download":True,"simulate":True,"ignoreerrors":True,"writethumbnail":False,"writeinfojson":False,"writesubtitles":False,"writeautomaticsub":False,"addmetadata":False})
        with yt_dlp.YoutubeDL(opts) as ydl:info=ydl.extract_info(request.url,download=False)
        result=self.estimate_info_size(info or {})
        if request.download_type=="Audio Only" and result["bytes"] is not None:result["confidence"]="approximate"
        if request.output_container!="auto" and result["bytes"] is not None:result["confidence"]="approximate"
        if (request.custom_video_filter or request.custom_audio_filter) and result["bytes"] is not None:result["confidence"]="approximate"
        if request.sponsorblock_enabled and request.sponsorblock_remove and result["bytes"] is not None:result["confidence"]="approximate"
        return result
    def verify_download(self,info: dict[str,Any],request: DownloadRequest,cancel: Event) -> dict[str,Any]:return self.integrity.verify(info,request,cancel).to_dict()
    def quarantine_corrupt(self,paths: list[str],folder: str) -> list[str]:return self.integrity.quarantine(paths,folder)
    @staticmethod
    def version() -> str: return yt_dlp.version.__version__
    @staticmethod
    def get_extractors() -> list[dict[str,str]]:
        from yt_dlp.extractor import list_extractor_classes
        result=[]
        for cls in list_extractor_classes():
            if getattr(cls,"IE_NAME",None): result.append({"name":cls.IE_NAME,"description":getattr(cls,"IE_DESC","") or "","type":"Generic" if cls.IE_NAME=="generic" else "Extractor"})
        return sorted(result,key=lambda x:x["name"].lower())
