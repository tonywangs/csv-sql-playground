"""Check publishable project files, excluding local environments and Git internals."""
from pathlib import Path
import subprocess
root=Path(__file__).resolve().parents[1]
files=subprocess.check_output(['git','ls-files','--cached','--others','--exclude-standard','-z'],cwd=root).decode().split('\0')
files=sorted(set(p for p in files if p));total=0
for p in files:
    f=root/p
    assert f.is_file(),p
    size=f.stat().st_size;assert size<=10*1024*1024,(p,size);total+=size
    assert not p.endswith('.log') or p=='results/tests.log',p
assert len(files)<=1000 and total<=32*1024*1024,(len(files),total)
print(len(files),'files;',total,'bytes; publication size limits satisfied')
