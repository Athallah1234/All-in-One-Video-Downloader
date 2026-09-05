import re,shutil,subprocess
from pathlib import Path
import yt_dlp

class Aria2Service:
    MIN_SAFE_YTDLP=(2026,6,9)
    @staticmethod
    def executable(location:str|None=None) -> str|None:
        value=str(location or "").strip()
        if value:
            path=Path(value)
            if path.is_dir():path=path/("aria2c.exe" if __import__("os").name=="nt" else "aria2c")
            return str(path.resolve()) if path.is_file() else None
        return shutil.which("aria2c")
    @classmethod
    def version(cls,location:str|None=None) -> str|None:
        executable=cls.executable(location)
        if not executable:return None
        try:
            result=subprocess.run([executable,"--version"],capture_output=True,text=True,timeout=5,check=False)
            return result.stdout.splitlines()[0].strip() if result.returncode==0 and result.stdout else None
        except (OSError,subprocess.SubprocessError):return None
    @staticmethod
    def ytdlp_version_tuple() -> tuple[int,int,int]:
        values=[int(value) for value in re.findall(r"\d+",yt_dlp.version.__version__)[:3]]
        return tuple((values+[0,0,0])[:3])
    @classmethod
    def safe_ytdlp(cls) -> bool:return cls.ytdlp_version_tuple()>=cls.MIN_SAFE_YTDLP
    @classmethod
    def build_options(cls,location:str|None,connections:int,split:int,min_split_mib:int,max_tries:int,retry_wait:int,timeout:int,file_allocation:str,use_fragments:bool) -> dict:
        executable=cls.executable(location)
        if not executable:raise ValueError("aria2c executable was not found")
        if not cls.version(location):raise ValueError("aria2c executable could not be started or did not report a version")
        if not cls.safe_ytdlp():raise ValueError("aria2c is disabled because yt-dlp must be version 2026.06.09 or newer")
        if not 1<=connections<=16 or not 1<=split<=16:raise ValueError("aria2c connections and splits must be between 1 and 16")
        if not 1<=min_split_mib<=1024 or not 0<=max_tries<=100 or not 0<=retry_wait<=120 or not 1<=timeout<=600:raise ValueError("aria2c numeric options are outside their supported ranges")
        if file_allocation not in {"none","prealloc","trunc"}:raise ValueError("Unsupported aria2c file-allocation mode")
        args=[f"--max-connection-per-server={connections}",f"--split={split}",f"--min-split-size={min_split_mib}M",f"--max-tries={max_tries}",f"--retry-wait={retry_wait}",f"--connect-timeout={timeout}",f"--timeout={timeout}",f"--file-allocation={file_allocation}","--continue=true"]
        downloader={"default":executable}
        if not use_fragments:downloader.update({"dash":"native","m3u8":"native"})
        return {"external_downloader":downloader,"external_downloader_args":{"aria2c":args}}
