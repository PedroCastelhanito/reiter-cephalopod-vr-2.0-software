import hashlib,json,time,threading,sys
from pathlib import Path
import _hashlib
payload=bytearray(41_297_200)
results=[]
for name, factory in [("managed_default",hashlib.sha256),("explicit_openssl",_hashlib.openssl_sha256)]:
    spans=[]; pauses=[]; digests=[]
    def work():
        for _ in range(12):
            time.sleep(.01)
            start=time.perf_counter_ns();digests.append(factory(payload).hexdigest());spans.append((time.perf_counter_ns()-start)/1e6)
    thread=threading.Thread(target=work);thread.start();previous=time.perf_counter_ns()
    while thread.is_alive():
        time.sleep(.001);now=time.perf_counter_ns();pauses.append((now-previous)/1e6);previous=now
    thread.join()
    results.append({"name":name,"provider":factory.__module__,"hash_ms":spans,"max_observer_pause_ms":max(pauses),"digest":digests[0]})
assert results[0]["digest"]==results[1]["digest"]
record={"executable":sys.executable,"results":results}
Path(__file__).with_name("hash-probe-after.json").write_text(json.dumps(record,indent=2),encoding="utf-8")
print(json.dumps(record))
