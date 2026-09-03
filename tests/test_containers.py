from utils.containers import CONTAINER_PRESETS,check_container_compatibility


def test_requested_container_presets_exist():
    assert [value for _label,value in CONTAINER_PRESETS]==[None,"mp4","mkv","webm","avi","mov"]


def test_container_compatibility_matrix():
    assert check_container_compatibility("mp4","h264","aac","SDR").compatible
    assert not check_container_compatibility("mp4","h264","opus","SDR").compatible
    assert check_container_compatibility("mkv","av1","opus","DV").compatible
    assert check_container_compatibility("webm","vp9","opus","HDR10").compatible
    assert not check_container_compatibility("webm","h264","opus","SDR").compatible
    assert not check_container_compatibility("webm","vp9","opus","DV").compatible
    assert check_container_compatibility("avi","h264","mp3","SDR").compatible
    assert not check_container_compatibility("avi","h264","mp3","HDR10").compatible
    assert not check_container_compatibility("avi","av1","mp3","SDR").compatible
    assert check_container_compatibility("mov","h265","aac","DV").compatible
    assert not check_container_compatibility("mov","vp9","aac","SDR").compatible


def test_video_only_does_not_apply_audio_restrictions():
    assert check_container_compatibility("webm","vp9","aac","SDR",video_only=True).compatible
