"""Verify local references/anchors in this increment's four current report sections."""
import re
from pathlib import Path

sections={
 'reports/runtime.md':('Oct13 combined recording/reset repair','Oct13 owner-authorized throughput implementation'),
 'reports/acquisition.md':('Oct13 owner-selected125ms','\n\n##'),
 'reports/visual_stimulus.md':('Oct13 owner-authorized combined','Oct13 `stimulus-throughput-repair`'),
 'reports/rig-verification.md':('Oct13 final combined repair','Oct13 later throughput repair'),
}
failures=[]
count=0
for name,(start,end) in sections.items():
    path=Path(name)
    body=path.read_text(encoding='utf-8')
    offset=body.index(start)
    finish=body.find(end,offset)
    section=body[offset:finish if finish>=0 else len(body)]
    for reference in re.findall(r'\]\(([^)]+)\)',section):
        if '://' in reference or reference.startswith('#'):continue
        filename,_,anchor=reference.partition('#')
        target=path.parent/filename
        if not target.exists():failures.append((name,reference))
        elif anchor and target.suffix=='.md':
            text=target.read_text(encoding='utf-8')
            anchors=set(re.findall(r'id=["\x27]([^"\x27]+)',text))
            anchors.update(re.sub(r'[^\w\s-]','',heading.lower()).strip().replace(' ','-') for heading in re.findall(r'^#+ (.+)$',text,re.M))
            if anchor not in anchors:failures.append((name,reference))
        count+=1
print('current report links checked',count,'failures',failures)
raise SystemExit(bool(failures))
