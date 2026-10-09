import re,subprocess
from pathlib import Path
from urllib.parse import unquote
files=[Path(x) for x in subprocess.check_output(['git','diff','--name-only'],text=True).splitlines() if x.endswith('.md') and Path(x).is_file()]
errors=[];n=0
for file in files:
 text=file.read_text()
 for match in re.finditer(r'(?<!!)\[[^\]\n]+\]\(([^)\n]+)\)',text):
  dest=match.group(1).strip('<>')
  if re.match(r'^[a-zA-Z]+:',dest):continue
  path,_,anchor=unquote(dest).partition('#')
  target=file.parent/path if path else file
  if not target.exists():errors.append(f'{file}: missing {dest}');continue
  n+=1
  if anchor and target.is_file() and target.suffix=='.md':
   content=target.read_text(); ids=set(re.findall(r'<a\s+id=[\"\x27]([^\"\x27]+)',content))
   for heading in re.findall(r'^#{1,6}\s+(.+)$',content,re.M):
    slug=re.sub(r'[^\w\- ]','',heading.lower()).replace(' ','-'); ids.add(slug)
   if anchor not in ids:errors.append(f'{file}: missing anchor {dest}')
print(f'Checked {n} local links/anchors in {len(files)} edited Markdown files')
print('\n'.join(errors))
raise SystemExit(bool(errors))
