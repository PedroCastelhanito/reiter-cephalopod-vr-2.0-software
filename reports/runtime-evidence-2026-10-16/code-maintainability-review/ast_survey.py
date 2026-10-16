import ast, collections, pathlib, json
roots=[pathlib.Path(p) for p in ('src','tests','tools')]
files=[p for r in roots for p in r.rglob('*.py') if '/v1/' not in str(p) and not p.name.endswith(('_pb2.py','_pb2_grpc.py'))]
counts=collections.Counter(); parsed={}; imports=collections.defaultdict(list)
for p in files:
 try: tree=ast.parse(p.read_text())
 except (SyntaxError,UnicodeError): continue
 parsed[p]=tree
 for n in ast.walk(tree):
  if isinstance(n,ast.Name):counts[n.id]+=1
  elif isinstance(n,ast.Attribute):counts[n.attr]+=1
  elif isinstance(n,ast.ImportFrom):
   for a in n.names: counts[a.name]+=1
   if n.module:imports[n.module].append(str(p))
  elif isinstance(n,ast.Constant) and isinstance(n.value,str):
   counts[n.value]+=1
unused=[]; same=collections.defaultdict(list); sizes=[]
for p,tree in parsed.items():
 if not str(p).startswith('src/'):continue
 sizes.append((len(p.read_text().splitlines()),str(p)))
 for n in tree.body:
  if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef,ast.ClassDef)) and counts[n.name]==0 and not n.name.startswith('__'):
   unused.append((str(p),n.lineno,n.name,n.end_lineno-n.lineno+1))
 for n in ast.walk(tree):
  if isinstance(n,(ast.FunctionDef,ast.AsyncFunctionDef)):
   body=n.body
   if body and isinstance(body[0],ast.Expr) and isinstance(body[0].value,ast.Constant) and isinstance(body[0].value.value,str):body=body[1:]
   if n.end_lineno-n.lineno>=8:
    key=ast.dump(ast.Module(body=body,type_ignores=[]),include_attributes=False)
    same[key].append((str(p),n.lineno,n.name,n.end_lineno-n.lineno+1))
print('LARGEST',json.dumps(sorted(sizes,reverse=True)[:35],indent=2))
print('UNREFERENCED TOP LEVEL',json.dumps(unused,indent=2))
print('EXACT BODY DUPLICATES',json.dumps([v for v in same.values() if len({p for p,_,_,_ in v})>1],indent=2))
