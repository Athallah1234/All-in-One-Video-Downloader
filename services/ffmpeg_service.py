import shutil, subprocess
from pathlib import Path

class FFmpegService:
    _location: str | None = None
    @classmethod
    def set_location(cls,location: str | None) -> None:cls._location=str(location).strip() if location else None
    @staticmethod
    def _candidate(location: str,name: str) -> str | None:
        path=Path(location)
        candidate=path/name if path.is_dir() else path
        if candidate.is_file() and (candidate.stem.lower()==name.lower() or path.is_dir()):return str(candidate)
        return None
    @classmethod
    def executable(cls,name: str) -> str | None:
        if cls._location:
            location_path=Path(cls._location)
            if location_path.is_file():
                sibling=location_path.with_name(name+(location_path.suffix if location_path.suffix else ""))
                if sibling.is_file():return str(sibling)
            direct=cls._candidate(cls._location,name+(".exe" if not name.lower().endswith(".exe") else "")) or cls._candidate(cls._location,name)
            if direct:return direct
        return shutil.which(name)
    @classmethod
    def version(cls, name: str="ffmpeg") -> str | None:
        path=cls.executable(name)
        if not path: return None
        try:
            result=subprocess.run([path,"-version"], capture_output=True, text=True, timeout=5, check=False)
            return result.stdout.splitlines()[0] if result.stdout else None
        except (OSError, subprocess.SubprocessError): return None
    @classmethod
    def available(cls) -> bool: return bool(cls.executable("ffmpeg") and cls.executable("ffprobe"))
