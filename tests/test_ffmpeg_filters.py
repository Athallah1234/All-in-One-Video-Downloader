from pathlib import Path
import pytest
from utils.ffmpeg_filters import resolve_audio_encoder,resolve_video_encoder,validate_encoder_container,validate_filtergraph
from services.custom_ffmpeg_filter import CustomFFmpegFilterPP

def test_filtergraph_structural_validation():
    assert validate_filtergraph("scale=-2:1080,unsharp=5:5:0.7").valid
    assert validate_filtergraph("drawtext=text='hello: world'").valid
    assert not validate_filtergraph("scale=(1080").valid
    assert not validate_filtergraph("volume=1\n-af anull").valid
    assert not validate_filtergraph("x"*4097).valid

def test_encoder_defaults_and_container_validation():
    assert resolve_video_encoder("auto","webm")=="libvpx-vp9"
    assert resolve_audio_encoder("auto","mp4")=="aac"
    assert resolve_audio_encoder("auto","ogg")=="libvorbis"
    assert resolve_audio_encoder("auto","wav")=="pcm_s16le"
    assert validate_encoder_container("libvpx-vp9","auto","webm",True,False).valid
    assert not validate_encoder_container("libx265","auto","webm",True,False).valid
    assert not validate_encoder_container("auto","libopus","mp4",False,True).valid

def test_postprocessor_uses_argv_and_atomic_replacement(tmp_path,monkeypatch):
    source=tmp_path/"clip.mp4";source.write_bytes(b"original")
    pp=CustomFFmpegFilterPP(None,video_filter="scale=-2:720",video_encoder="libx264")
    captured={}
    def fake_run(inputs,outputs):
        captured["inputs"]=inputs;captured["outputs"]=outputs
        Path(outputs[0][0]).write_bytes(b"filtered")
    monkeypatch.setattr(pp,"real_run_ffmpeg",fake_run);monkeypatch.setattr(pp,"to_screen",lambda *_:None)
    deleted,info=pp.run({"filepath":str(source)})
    assert deleted==[] and info["filepath"]==str(source) and source.read_bytes()==b"filtered"
    args=captured["outputs"][0][1]
    assert args[args.index("-filter:v:0")+1]=="scale=-2:720"
    assert "libx264" in args

def test_postprocessor_preserves_original_on_failure(tmp_path,monkeypatch):
    source=tmp_path/"clip.mkv";source.write_bytes(b"original")
    pp=CustomFFmpegFilterPP(None,audio_filter="loudnorm")
    monkeypatch.setattr(pp,"real_run_ffmpeg",lambda *_:(_ for _ in ()).throw(RuntimeError("boom")));monkeypatch.setattr(pp,"to_screen",lambda *_:None)
    with pytest.raises(Exception):pp.run({"filepath":str(source)})
    assert source.read_bytes()==b"original"
    assert not list(tmp_path.glob("*.custom-filter-*"))
