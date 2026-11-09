"""Post-process pandoc output: full-width tables (columns scaled to the text width) and smaller code text."""
import re, sys, zipfile, shutil
from pathlib import Path
for f in sys.argv[1:]:
    p = Path(f); tmp = p.with_suffix('.tmp.docx')
    with zipfile.ZipFile(p) as z:
        items = {n: z.read(n) for n in z.namelist() if not n.endswith('/')}
    doc = items['word/document.xml'].decode('utf-8')
    # A4, 2 cm margins (pandoc writes an empty sectPr, which leaves the page size to the viewer)
    sect = '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1134" w:right="1134" w:bottom="1134" w:left="1134" w:header="567" w:footer="567" w:gutter="0"/></w:sectPr>'
    doc = re.sub(r'<w:sectPr\s*/>|<w:sectPr>.*?</w:sectPr>', sect, doc, flags=re.S)
    text_w = 11906 - 2 * 1134
    def fix_table(m):
        t = m.group(0)
        cols = [int(x) for x in re.findall(r'<w:gridCol w:w="(\d+)"\s*/>', t)]
        if cols:
            tot = sum(cols); new = [max(400, round(c * text_w / tot)) for c in cols]
            it = iter(new); t = re.sub(r'<w:gridCol w:w="\d+"\s*/>', lambda _: f'<w:gridCol w:w="{next(it)}"/>', t)
        t = re.sub(r'<w:tblW [^>]*/>', f'<w:tblW w:type="dxa" w:w="{text_w}"/>', t, count=1)
        return t
    doc = re.sub(r'<w:tbl>.*?</w:tbl>', fix_table, doc, flags=re.S)
    items['word/document.xml'] = doc.encode('utf-8')
    st = items['word/styles.xml'].decode('utf-8')
    st = re.sub(r'(<w:style [^>]*w:styleId="VerbatimChar".*?<w:sz w:val=")\d+(")', r'\g<1>17\2', st, flags=re.S)
    st = re.sub(r'(<w:style [^>]*w:styleId="SourceCode"[^>]*>)(.*?)(</w:style>)', lambda m: m.group(1) + (re.sub(r'<w:sz w:val="\d+"', '<w:sz w:val="16"', m.group(2)) if '<w:sz ' in m.group(2) else m.group(2).replace('</w:rPr>', '<w:sz w:val="16"/></w:rPr>') if '<w:rPr>' in m.group(2) else m.group(2) + '<w:rPr><w:sz w:val="16"/></w:rPr>') + m.group(3), st, flags=re.S)
    items['word/styles.xml'] = st.encode('utf-8')
    with zipfile.ZipFile(tmp, 'w', zipfile.ZIP_DEFLATED) as z:
        for n in (['[Content_Types].xml'] + [n for n in items if n != '[Content_Types].xml']):
            z.writestr(n, items[n])
    shutil.move(tmp, p); print(p.name, 'text width', text_w)
