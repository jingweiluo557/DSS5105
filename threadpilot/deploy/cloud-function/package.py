"""Allowlist backend artifacts; credentials and local runtime files never enter ZIP."""
from pathlib import Path
from zipfile import ZipFile, ZipInfo, ZIP_DEFLATED

source = Path(__file__).resolve().parent
root = source.parents[1]
vendor = root / '.build/cloud-function-full'
if not (vendor / 'fastapi/__init__.py').exists():
    raise SystemExit('Install Linux/Python 3.11 requirements into .build/cloud-function-full first.')
output = root / 'dist/threadpilot-backend-python311.zip'
output.parent.mkdir(exist_ok=True)


def add(archive, path, name, executable=False):
    if '__pycache__' in path.parts or path.suffix == '.pyc':
        return
    entry = ZipInfo(name)
    entry.create_system = 3
    entry.external_attr = (0o100755 if executable else 0o100644) << 16
    entry.compress_type = ZIP_DEFLATED
    payload = path.read_bytes()
    if executable:
        payload = payload.replace(b'\r\n', b'\n')
    archive.writestr(entry, payload)


with ZipFile(output, 'w', ZIP_DEFLATED) as archive:
    add(archive, source / 'scf_bootstrap', 'scf_bootstrap', True)
    for directory in ('backend/app', 'data/dictionary'):
        for path in sorted((root / directory).rglob('*')):
            if path.is_file() and path.suffix in ('.py', '.yaml', '.json'):
                add(archive, path, path.relative_to(root).as_posix())
    for name in ('__init__.py', 'cloud_serve.py'):
        add(archive, root / 'backend/scripts' / name, 'backend/scripts/' + name)
    for path in sorted(vendor.rglob('*')):
        if path.is_file():
            add(archive, path, path.relative_to(vendor).as_posix())
with ZipFile(output) as archive:
    assert archive.testzip() is None
    assert archive.getinfo('scf_bootstrap').external_attr >> 16 & 0o111
    assert not any(Path(name).name.startswith('.env') or name.startswith('backend/runtime/') or name.endswith('.sqlite3') for name in archive.namelist())
    assert output.stat().st_size < 500 * 1024 * 1024
print(f'Created {output} ({output.stat().st_size:,} bytes)')
timer_output = output.with_name('threadpilot-reminder-timer.zip')
with ZipFile(timer_output, 'w', ZIP_DEFLATED) as archive:
    add(archive, source / 'timer.py', 'timer.py')
    add(archive, source / 'index.py', 'index.py')
print(f'Created {timer_output}')
morning_output = output.with_name('threadpilot-morning-timer.zip')
with ZipFile(morning_output, 'w', ZIP_DEFLATED) as archive:
    add(archive, source / 'morning_timer.py', 'index.py')
print(f'Created {morning_output}')
