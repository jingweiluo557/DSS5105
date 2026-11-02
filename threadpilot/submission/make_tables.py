"""Turn the repo's markdown tables (tool specification, evaluation set) into HTML fragments for the submission PDFs,
so the numbers and wording in the PDFs are the repo's, not retyped."""
import html, json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = Path(__file__).resolve().parent / 'fragments'
OUT.mkdir(exist_ok=True)


def md_table(path, header_startswith):
    rows = []
    for line in Path(path).read_text(encoding='utf-8').splitlines():
        if line.startswith('|') and not re.match(r'^\|\s*-', line):
            cells = [c.strip() for c in line.strip().strip('|').split('|')]
            rows.append(cells)
    head = next(i for i, r in enumerate(rows) if r[0].startswith(header_startswith))
    return rows[head], rows[head + 1:]


def inline(md):
    s = html.escape(md)
    s = re.sub(r'`([^`]+)`', r'<code>\1</code>', s)
    s = re.sub(r'\*\*([^*]+)\*\*', r'<b>\1</b>', s)
    s = s.replace('✅ pass', '<span class="ok">pass</span>').replace('❌ fail', '<span class="bad">fail</span>')
    s = s.replace('— not in that run', '<span class="muted">not in that run</span>')
    return s


# ---------------------------------------------------------------- tool specification (32 tools)
head, rows = md_table(ROOT / 'docs/TOOL_SPECIFICATION.md', '#')
rows = [r for r in rows if len(r) >= 8 and r[0].strip().isdigit()]
rows.sort(key=lambda r: int(r[0]))
h = ['<table class="tools"><thead><tr><th>#</th><th>Tool</th><th>Kind</th><th>Input</th><th>Output</th><th>Exists to answer (purpose)</th><th>Deliberately does not (non-goals)</th><th>Failure mode</th></tr></thead><tbody>']
for r in rows:
    h.append('<tr>' + ''.join(f'<td>{inline(c)}</td>' for c in r[:8]) + '</tr>')
h.append('</tbody></table>')
(OUT / 'tools.html').write_text('\n'.join(h), encoding='utf-8')
print('tools:', len(rows))

# ---------------------------------------------------------------- evaluation set (88 questions)
head, rows = md_table(ROOT / 'evaluation/EVALUATION.md', '#')
rows = [r for r in rows if len(r) >= 5 and re.match(r'^[A-Za-z]+\d', r[0])]
h = ['<table class="evalset"><thead><tr><th>#</th><th>Category</th><th>Question (turns)</th><th>Verified answer / expected behaviour</th><th>24 Oct live first pass</th></tr></thead><tbody>']
for r in rows:
    h.append('<tr>' + ''.join(f'<td>{inline(c)}</td>' for c in r[:5]) + '</tr>')
h.append('</tbody></table>')
(OUT / 'evalset.html').write_text('\n'.join(h), encoding='utf-8')
print('questions:', len(rows))

# ---------------------------------------------------------------- held-out and bait question lists
def qlist(path, title):
    q = json.loads((ROOT / path).read_text(encoding='utf-8'))['questions']
    h = [f'<table><thead><tr><th>#</th><th>Category</th><th>Question</th><th>Check</th></tr></thead><tbody>']
    for x in q:
        exp = x.get('expect_any') or x.get('forbid') or x.get('expect') or ''
        if isinstance(exp, list): exp = ' | '.join(map(str, exp[:4])) + (' …' if len(exp) > 4 else '')
        h.append(f"<tr><td>{x['id']}</td><td>{html.escape(x['category'])}</td><td>{html.escape(' → '.join(x['turns']))}</td><td class=\"small\">{html.escape(x['check'])}: <code>{html.escape(str(exp))[:90]}</code></td></tr>")
    h.append('</tbody></table>')
    return '\n'.join(h), len(q)

frag, n = qlist('evaluation/heldout_questions.json', 'held-out'); (OUT / 'heldout.html').write_text(frag, encoding='utf-8'); print('heldout:', n)
frag, n = qlist('evaluation/bait_questions.json', 'bait'); (OUT / 'bait.html').write_text(frag, encoding='utf-8'); print('bait:', n)
