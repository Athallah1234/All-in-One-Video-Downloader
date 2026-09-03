from utils.queue_eta import estimate_queue_eta

def item(status,size=None,progress=0,speed=None,confidence="exact",**extra):
    value={"request":object(),"status":status,"progress":progress,"speed_bytes":speed}
    if size is not None:value["estimate"]={"bytes":size,"confidence":confidence}
    value.update(extra);return value

def test_serial_and_concurrent_makespan():
    queue=[item("Waiting",1000),item("Waiting",1000),item("Waiting",1000)]
    assert estimate_queue_eta(queue,1,100).seconds==30
    assert estimate_queue_eta(queue,2,100).seconds==20

def test_active_progress_and_future_queue():
    queue=[item("Downloading",1000,progress=50,speed=100),item("Waiting",1000)]
    result=estimate_queue_eta(queue,1,100)
    assert result.seconds==15

def test_pause_makes_finish_time_undefined():
    result=estimate_queue_eta([item("Paused",1000,progress=50,speed=100)],2,100)
    assert result.seconds is None and result.paused_items==1

def test_unknown_size_is_lower_bound():
    result=estimate_queue_eta([item("Waiting",1000),item("Waiting")],1,100)
    assert result.seconds==10 and result.confidence=="lower_bound" and result.unknown_items==1

def test_all_unknown_sizes_have_no_fake_zero_eta():
    result=estimate_queue_eta([item("Estimating size…"),item("Waiting")],2,100)
    assert result.seconds is None and result.unknown_items==2

def test_speed_is_required_for_known_transfer():
    result=estimate_queue_eta([item("Waiting",1000)],1,None)
    assert result.seconds is None and result.waiting_for_speed

def test_postprocessing_uses_learned_duration():
    result=estimate_queue_eta([item("Post-processing: ffmpeg",1000,postprocess_started=95)],1,100,postprocess_seconds=20,now=100)
    assert result.seconds==15 and result.postprocessing_items==1
