"""Create a clean skill distribution without benchmark answers or local history."""
import argparse
from pathlib import Path
import zipfile

ROOT=Path(__file__).resolve().parents[1]
FILES=['SKILL.md','README.md','README.en.md','requirements.txt','install.ps1','LICENSE','THIRD_PARTY_NOTICES.md']
DIRECTORIES=['scripts','references','schema','standards','examples']


def package(out):
    out=Path(out)
    if out.exists(): raise ValueError('Choose a new archive filename')
    files=[ROOT/name for name in FILES]
    for directory in DIRECTORIES:
        files.extend(p for p in (ROOT/directory).rglob('*') if p.is_file()
                     and '__pycache__' not in p.parts and p.suffix in ('.py','.md','.json','.txt','.pdf','.png'))
    out.parent.mkdir(parents=True,exist_ok=True)
    with zipfile.ZipFile(out,'x',compression=zipfile.ZIP_DEFLATED) as archive:
        for file in sorted(files): archive.write(file,'drawing2sw/'+file.relative_to(ROOT).as_posix())
    return len(files)


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('-o','--out',required=True)
    args=ap.parse_args()
    print(f'Packaged {package(args.out)} files')
