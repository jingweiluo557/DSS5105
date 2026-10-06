"""Package only probe source and preinstalled Linux dependencies, never .env."""
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

source = Path(__file__).resolve().parent
root = source.parents[1]
vendor = root / '.build/cloud-function-probe'
if not (vendor / 'pymysql/__init__.py').exists():
    raise SystemExit('Install Linux/Python 3.11 requirements into .build/cloud-function-probe first.')
output = root / 'dist/threadpilot-api-test.zip'
output.parent.mkdir(exist_ok=True)
with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
    for name in ('app.py', 'scf_bootstrap', 'requirements.txt'):
        entry = ZipInfo(name)
        entry.create_system = 3
        entry.external_attr = (0o100755 if name == 'scf_bootstrap' else 0o100644) << 16
        entry.compress_type = ZIP_DEFLATED
        archive.writestr(entry, (source / name).read_text(encoding='utf-8').replace('\r\n', '\n').encode())
    for path in sorted(vendor.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix != '.pyc':
            archive.write(path, path.relative_to(vendor).as_posix())
with ZipFile(output) as archive:
    assert archive.testzip() is None
    assert archive.getinfo('scf_bootstrap').external_attr >> 16 & 0o111
    assert not any('.env' in Path(name).name for name in archive.namelist())
    assert b'\r' not in archive.read('scf_bootstrap')
print(f'Created {output} ({output.stat().st_size:,} bytes); ZIP integrity and bootstrap permissions verified.')
