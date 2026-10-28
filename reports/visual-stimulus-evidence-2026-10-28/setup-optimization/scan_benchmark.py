import re
import time
from pathlib import Path

source = Path(__file__).with_name("prepared.json").read_text()
tokens = re.compile(r'"[^"\\]*(?:\\.[^"\\]*)*"|[{}\[\]]')
start = time.perf_counter()
depth = maximum = 0
for match in tokens.finditer(source):
    token = source[match.start()]
    if token in "[{":
        depth += 1
        maximum = max(maximum, depth)
    elif token in "]}":
        depth -= 1
print(dict(seconds=time.perf_counter()-start,maximum=maximum,depth=depth))
