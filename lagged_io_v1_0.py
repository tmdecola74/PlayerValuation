"""UTF-8, hashing and path-validation helpers for the standalone lagged build."""
import hashlib,json
from pathlib import Path
from decimal import Decimal

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def dump(p,v):p.write_text(json.dumps(v,indent=2,ensure_ascii=False,allow_nan=False),encoding='utf-8')
def load(p):return json.loads(Path(p).read_text(encoding='utf-8-sig'))
def tree(p):return {str(x.relative_to(p)):sha(x) for x in p.rglob('*') if x.is_file()}
def inside(root,name):
 p=(root/name).resolve()
 if p==root or root not in p.parents:raise ValueError('Manifest path outside register')
 return p
def integer(x,label):
 try:v=Decimal(str(x))
 except ArithmeticError:raise ValueError('Invalid '+label) from None
 if not v.is_finite() or v<0 or v!=int(v):raise ValueError('Invalid '+label)
 return int(v)
