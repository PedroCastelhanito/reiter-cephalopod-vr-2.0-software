"""Explicit opt-in mechanical migration; inspect dry-run and source diff before acceptance."""
import ast
import json
from pathlib import Path
import argparse
p=argparse.ArgumentParser();p.add_argument('--apply',action='store_true');p.add_argument('--only',nargs='*');p.add_argument('--exclude',nargs='*',default=[]);args=p.parse_args()
entries=json.loads(Path('/tmp/cephvr-nongui-deadline-seconds-candidates.json').read_text()); replacements={}
for item in entries:
    path=item['path']
    if args.only and not any(path.startswith(x) for x in args.only):continue
    if any(path.startswith(x) for x in args.exclude):continue
    replacements.setdefault(path,{})[ast.dump(ast.parse(item['before'],mode='eval').body)]=item['candidate']
result=[]
for name,mapping in replacements.items():
    path=Path(name);source=path.read_text();tree=ast.parse(source);lines=source.splitlines(keepends=True);offsets=[0]
    for line in lines:offsets.append(offsets[-1]+len(line))
    edits=[]
    for node in ast.walk(tree):
        if not isinstance(node,(ast.Call,ast.BinOp)):continue
        replacement=mapping.get(ast.dump(node))
        if replacement is None:continue
        # These project source expressions are ASCII; retain byte-offset correctness explicitly.
        assert lines[node.lineno-1][:node.col_offset].isascii()
        start=offsets[node.lineno-1]+node.col_offset;end=offsets[node.end_lineno-1]+node.end_col_offset
        edits.append((start,end,replacement))
    if not edits:continue
    edits.sort(reverse=True)
    assert all(later[0]>=earlier[1] for later,earlier in zip(edits,edits[1:]))
    for start,end,replacement in edits:source=source[:start]+replacement+source[end:]
    # Reuse current compatible import; otherwise one focused import (Ruff sorts it).
    names=[alias.asname or alias.name for node in tree.body if isinstance(node,ast.ImportFrom) and node.module in ('cephvr.shared.deadlines','cephvr.shared.transport_deadlines') for alias in node.names]
    if 'remaining_seconds' not in names:
        tree=ast.parse(source);position=0
        for node in tree.body:
            if isinstance(node,ast.Expr) and isinstance(node.value,ast.Constant) and isinstance(node.value.value,str) or isinstance(node,ast.ImportFrom) and node.module=='__future__':position=node.end_lineno
            else:break
        lines=source.splitlines(keepends=True);lines.insert(position,'\nfrom cephvr.shared.deadlines import remaining_seconds\n');source=''.join(lines)
    ast.parse(source)
    if args.apply:path.write_text(source)
    result.append({'path':name,'replacements':len(edits)})
print(json.dumps({'applied':args.apply,'files':result,'total':sum(x['replacements'] for x in result)},indent=2))
