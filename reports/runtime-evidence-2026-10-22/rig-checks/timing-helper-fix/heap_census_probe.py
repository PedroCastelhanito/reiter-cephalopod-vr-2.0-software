"""Disposable off-frame heap census; no GC policy changes or new deadline."""
import collections,gc,json,time,itertools,traceback
from pathlib import Path

def type_name(value):
    return f"{type(value).__module__}.{type(value).__qualname__}"

def describe(value):
    kind=type_name(value)
    result={"type":kind}
    if isinstance(value,(dict,list,tuple,set)):
        result["length"]=len(value)
    if isinstance(value,dict):
        result["keys"]=[key[:64] if isinstance(key,str) else type(key).__name__ for key in itertools.islice(value,8)]
    return result

def census(stage,refs=False):
    started=time.perf_counter_ns(); objects=gc.get_objects()
    counts=collections.Counter(type_name(x) for x in objects)
    samples=[]
    if refs:
        for name,_ in counts.most_common(3):
            obj=next(x for x in objects if type_name(x)==name)
            parents=gc.get_referrers(obj)
            samples.append({"sample_type":name,"parents":[describe(x) for x in parents[:8] if x is not objects]})
            del parents,obj
    return {"stage":stage,"start_ns":started,"elapsed_ns":time.perf_counter_ns()-started,
            "freeze_count":gc.get_freeze_count(),"tracked_total":len(objects),
            "type_counts":dict(counts),"samples":samples}

def install(driver,port,recording):
    snapshots=[]; errors=[]
    heap=driver.preparation._prepared_heap
    prepare=heap.prepare; cleanup=driver.cleanup
    def prepared(*args,**kwargs):
        result=prepare(*args,**kwargs)
        try:snapshots.append(census("after_setup_freeze"))
        except BaseException as error:errors.append({"error":str(error)[:512],"traceback":traceback.format_exc(limit=5)[-2048:]})
        return result
    heap.prepare=prepared
    def finish(command):
        started=time.perf_counter_ns()
        try:
            session=recording._session
            quiescent=driver.engine._stopped and (session is None or not session._thread.is_alive())
            if quiescent and command.deadline_monotonic_ns-time.perf_counter_ns()>3_000_000_000:
                snapshots.append(census("before_cleanup_collect"))
                if command.deadline_monotonic_ns-time.perf_counter_ns()>2_000_000_000:
                    before=time.perf_counter_ns();collected=gc.collect(2)
                    snapshots.append({"stage":"cleanup_collect","elapsed_ns":time.perf_counter_ns()-before,"collected":collected})
                    snapshots.append(census("after_cleanup_collect",refs=True))
            else:errors.append("census skipped: active recording or original cleanup budget insufficient")
        except BaseException as error:errors.append({"error":str(error)[:512],"traceback":traceback.format_exc(limit=5)[-2048:]})
        diagnostic_elapsed=time.perf_counter_ns()-started
        try:
            return cleanup(command)
        finally:
            for obj,name in ((heap,"prepare"),(driver,"cleanup")):
                try:delattr(obj,name)
                except BaseException:pass
            try:
                Path(__file__).with_name("heap-census-results.json").write_text(json.dumps({"diagnostic_perturbed":True,"diagnostic_elapsed_ns":diagnostic_elapsed,"errors":errors,"snapshots":snapshots},indent=2),encoding="utf-8")
            except BaseException:
                pass
    driver.cleanup=finish
