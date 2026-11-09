"""HTML submission sources -> Word-friendly HTML -> .docx (pandoc + the team's reference.docx).
CSS-only layout (KPI tiles, score bars, case cards, the SVG figure, signature boxes) becomes real tables and paragraphs."""
import sys, re, subprocess
from pathlib import Path
from bs4 import BeautifulSoup
SUB = Path(__file__).resolve().parents[1]

def prep(html):
    soup = BeautifulSoup(html, 'html.parser')
    for t in soup(['style', 'script', 'link']): t.decompose()
    # architecture figure -> the PNG rendered from the same SVG
    for svg in soup.find_all('svg'):
        img = soup.new_tag('img', src=str(SUB / 'docx/arch.png'), alt='Figure 1. ThreadPilot architecture', style='width:16cm')
        svg.replace_with(img)
    # relative image paths -> absolute, so pandoc finds them from any working directory
    for img in soup.find_all('img'):
        src = img.get('src') or ''
        if src and not src.startswith(('/', 'http', 'data:')): img['src'] = str(SUB / src)
        img['style'] = 'width:16cm'
    # KPI tiles -> a two-column table
    for box in soup.select('div.kpis'):
        tbl = soup.new_tag('table'); tr = soup.new_tag('tr'); tbl.append(tr)
        for h in ('Figure', 'What it measures'):
            th = soup.new_tag('th'); th.string = h; tr.append(th)
        for k in box.select('div.kpi'):
            tr = soup.new_tag('tr'); a = soup.new_tag('td'); b = soup.new_tag('td')
            bb = soup.new_tag('b'); bb.string = k.b.get_text(); a.append(bb); b.string = k.span.get_text()
            tr.append(a); tr.append(b); tbl.append(tr)
        box.replace_with(tbl)
    # score bars -> one table per run of bars
    for first in soup.select('div.bar'):
        if first.decomposed: continue
        if first.find_previous_sibling() is not None and 'bar' in (first.find_previous_sibling().get('class') or []): continue
        run = [first]; nxt = first.find_next_sibling()
        while nxt is not None and 'bar' in (nxt.get('class') or []): run.append(nxt); nxt = nxt.find_next_sibling()
        tbl = soup.new_tag('table'); tr = soup.new_tag('tr'); tbl.append(tr)
        for h in ('Question type', 'Fully correct'):
            th = soup.new_tag('th'); th.string = h; tr.append(th)
        for b in run:
            label = b.b.get_text(); score = b.get_text().replace(label, '', 1).strip()
            tr = soup.new_tag('tr'); c1 = soup.new_tag('td'); c1.string = label; c2 = soup.new_tag('td'); c2.string = score
            tr.append(c1); tr.append(c2); tbl.append(tr)
        first.insert_before(tbl)
        for b in run: b.decompose()
    # case cards: dt/dd -> "Got. …" paragraphs
    for dl in soup.find_all('dl'):
        div = soup.new_tag('div')
        for dt in dl.find_all('dt'):
            dd = dt.find_next_sibling('dd'); p = soup.new_tag('p'); b = soup.new_tag('b'); b.string = dt.get_text().strip() + '. '
            p.append(b)
            for c in list(dd.contents): p.append(c)
            div.append(p)
        dl.replace_with(div)
    # signature boxes (Teams) -> a one-row table of names with a signature line
    for sig in soup.select('.sig'):
        names = [x.get_text(' ', strip=True) for x in sig.find_all(recursive=False)] or [sig.get_text(' ', strip=True)]
        tbl = soup.new_tag('table'); tr = soup.new_tag('tr'); tbl.append(tr)
        for n in names:
            td = soup.new_tag('td'); td.string = ' \n\n' + n; tr.append(td)
        sig.replace_with(tbl)
    return str(soup)

src, out = Path(sys.argv[1]), Path(sys.argv[2])
tmp = out.with_suffix('.prep.html'); tmp.write_text(prep(src.read_text(encoding='utf-8')), encoding='utf-8')
subprocess.run(['pandoc', str(tmp), '-f', 'html', '-t', 'docx', '--reference-doc', str(SUB / 'docx/reference.docx'), '-o', str(out)], check=True)
tmp.unlink(); print(out)
