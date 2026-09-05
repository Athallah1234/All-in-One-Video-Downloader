from services.aria2_service import Aria2Service
from services.ytdlp_service import YTDLPService

def test_aria2_options_use_argv_and_native_fragment_fallback(monkeypatch):
    monkeypatch.setattr(Aria2Service,"executable",classmethod(lambda cls,_=None:"C:/Tools/aria2c.exe"))
    monkeypatch.setattr(Aria2Service,"version",classmethod(lambda cls,_=None:"aria2 version 1.37.0"))
    monkeypatch.setattr(Aria2Service,"safe_ytdlp",classmethod(lambda cls:True))
    options=Aria2Service.build_options("",8,8,4,7,2,30,"none",False)
    assert options["external_downloader"]=={"default":"C:/Tools/aria2c.exe","dash":"native","m3u8":"native"}
    args=options["external_downloader_args"]["aria2c"]
    assert "--max-connection-per-server=8" in args and "--split=8" in args
    assert "--min-split-size=4M" in args and "--continue=true" in args

def test_aria2_can_explicitly_handle_fragments(monkeypatch):
    monkeypatch.setattr(Aria2Service,"executable",classmethod(lambda cls,_=None:"aria2c"));monkeypatch.setattr(Aria2Service,"version",classmethod(lambda cls,_=None:"aria2 version 1.37.0"));monkeypatch.setattr(Aria2Service,"safe_ytdlp",classmethod(lambda cls:True))
    assert Aria2Service.build_options("",16,16,1,5,1,20,"prealloc",True)["external_downloader"]=={"default":"aria2c"}

def test_aria2_rejects_invalid_configuration(monkeypatch):
    monkeypatch.setattr(Aria2Service,"executable",classmethod(lambda cls,_=None:"aria2c"));monkeypatch.setattr(Aria2Service,"version",classmethod(lambda cls,_=None:"aria2 version 1.37.0"));monkeypatch.setattr(Aria2Service,"safe_ytdlp",classmethod(lambda cls:True))
    import pytest
    with pytest.raises(ValueError):Aria2Service.build_options("",17,16,1,5,1,20,"none",False)
    with pytest.raises(ValueError):Aria2Service.build_options("",16,16,1,5,1,20,"falloc",False)

class Settings:
    values={"downloads/backend":"aria2c","downloads/aria2_connections":8,"downloads/aria2_split":4}
    def value(self,key,default=None):return self.values.get(key,default)

class Logger:
    def debug(self,*_):pass
    def info(self,*_):pass
    def warning(self,*_):pass
    def error(self,*_):pass

def test_service_configuration_applies_backend(monkeypatch):
    monkeypatch.setattr(Aria2Service,"executable",classmethod(lambda cls,_=None:"aria2c"));monkeypatch.setattr(Aria2Service,"version",classmethod(lambda cls,_=None:"aria2 version 1.37.0"));monkeypatch.setattr(Aria2Service,"safe_ytdlp",classmethod(lambda cls:True))
    service=YTDLPService(Logger());service.configure(Settings())
    assert service.runtime_options["external_downloader"]["default"]=="aria2c"
    assert "--split=4" in service.runtime_options["external_downloader_args"]["aria2c"]
