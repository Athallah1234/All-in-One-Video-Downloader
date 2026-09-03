from dataclasses import asdict, dataclass
from datetime import datetime
from hashlib import new as new_hash
import json
from pathlib import Path
import shutil
import subprocess
from threading import Event
from typing import Any


MEDIA_EXTENSIONS={".mp4",".mkv",".webm",".mov",".avi",".m4v",".mp3",".m4a",".aac",".flac",".wav",".opus",".ogg"}


@dataclass
class IntegrityResult:
    valid: bool
    conclusive: bool
    confidence: str
    files: list[str]
    errors: list[str]
    hashes: dict[str,str]
    invalid_files: list[str]

    def to_dict(self):return asdict(self)


class IntegrityService:
    def __init__(self,logger):self.logger=logger

    @staticmethod
    def collect_paths(info: dict[str,Any]) -> list[Path]:
        paths=[]
        def visit(value):
            if isinstance(value,dict):
                for key,item in value.items():
                    if key in {"filepath","_filename"} and isinstance(item,str):paths.append(Path(item))
                    elif key=="_observed_output_paths" and isinstance(item,list):paths.extend(Path(path) for path in item if isinstance(path,str))
                    elif key in {"entries","requested_downloads"}:visit(item)
            elif isinstance(value,list):
                for item in value:visit(item)
        visit(info); result=[]; seen=set()
        for path in paths:
            key=str(path.absolute())
            if key not in seen:seen.add(key);result.append(path)
        return result

    @staticmethod
    def expected_hash(info: dict[str,Any],request) -> tuple[str,str] | None:
        if request.download_type!="Video Only":return None
        for algorithm in ("sha256","sha1","md5"):
            value=info.get(algorithm)
            if isinstance(value,str) and value:return algorithm,value.lower()
        checksum=info.get("checksum")
        if isinstance(checksum,dict):
            for algorithm in ("sha256","sha1","md5"):
                if checksum.get(algorithm):return algorithm,str(checksum[algorithm]).lower()
        return None

    @staticmethod
    def calculate_hash(path: Path,algorithm: str,cancel: Event) -> str:
        digest=new_hash(algorithm)
        with path.open("rb") as stream:
            while chunk:=stream.read(1024*1024):
                if cancel.is_set():raise InterruptedError("Integrity verification cancelled")
                digest.update(chunk)
        return digest.hexdigest()

    @staticmethod
    def probe(path: Path,ffprobe: str) -> str | None:
        try:
            result=subprocess.run([ffprobe,"-v","error","-show_entries","format=duration,size","-of","json",str(path)],capture_output=True,text=True,timeout=30,check=False)
            if result.returncode!=0:return (result.stderr or "FFprobe rejected the media container").strip()[:500]
            payload=json.loads(result.stdout or "{}"); size=(payload.get("format") or {}).get("size")
            if size is not None and int(size)<=0:return "FFprobe reported an empty media file"
            return None
        except (OSError,ValueError,json.JSONDecodeError,subprocess.SubprocessError) as exc:return f"FFprobe validation failed: {exc}"

    def verify(self,info: dict[str,Any],request,cancel: Event) -> IntegrityResult:
        folder=Path(request.folder).resolve(); candidates=self.collect_paths(info); files=[]; errors=[]; hashes={}; invalid=[]; ffprobe=shutil.which("ffprobe"); probed=False
        for candidate in candidates:
            try:
                path=candidate.resolve()
                if not path.is_relative_to(folder):errors.append(f"Unsafe output path ignored: {path}");continue
                if not path.exists():continue
                files.append(str(path))
                if not path.is_file() or path.stat().st_size<=0:errors.append(f"Empty or invalid output file: {path.name}");invalid.append(str(path));continue
                if ffprobe and path.suffix.lower() in MEDIA_EXTENSIONS:
                    probed=True; probe_error=self.probe(path,ffprobe)
                    if probe_error:errors.append(f"{path.name}: {probe_error}");invalid.append(str(path))
            except OSError as exc:errors.append(f"Cannot inspect output: {exc}")
        if not files:return IntegrityResult(True,False,"unavailable",[],["No final output path was exposed by yt-dlp"],{},[])
        if request.download_type=="Video Only" and len(files)==1 and not errors:
            expected_size=info.get("filesize")
            if not expected_size:
                downloads=info.get("requested_downloads") or []
                if len(downloads)==1:expected_size=(downloads[0] or {}).get("filesize")
            if isinstance(expected_size,(int,float)) and expected_size>0:
                actual_size=Path(files[0]).stat().st_size
                if actual_size!=int(expected_size):errors.append(f"File size mismatch (expected {int(expected_size)} bytes, got {actual_size})");invalid.append(files[0])
        expected=self.expected_hash(info,request)
        if expected and len(files)==1 and not errors:
            algorithm,value=expected
            try:
                actual=self.calculate_hash(Path(files[0]),algorithm,cancel);hashes[algorithm]=actual
                if actual.lower()!=value:errors.append(f"{algorithm.upper()} mismatch (expected {value}, got {actual})");invalid.append(files[0])
            except (OSError,ValueError,InterruptedError) as exc:errors.append(f"Hash verification failed: {exc}");invalid.append(files[0])
        confidence="hash" if hashes else ("ffprobe" if probed else "structural")
        return IntegrityResult(not errors,True,confidence,files,errors,hashes,sorted(set(invalid)))

    @staticmethod
    def quarantine(paths: list[str],folder: str) -> list[str]:
        root=Path(folder).resolve(); moved=[]; stamp=datetime.now().strftime("%Y%m%d-%H%M%S")
        for value in paths:
            path=Path(value).resolve()
            if not path.is_relative_to(root) or not path.exists() or not path.is_file():continue
            target=path.with_name(f"{path.name}.corrupt-{stamp}"); counter=1
            while target.exists():target=path.with_name(f"{path.name}.corrupt-{stamp}-{counter}");counter+=1
            path.replace(target);moved.append(str(target))
        return moved
