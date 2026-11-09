// node build_pdf.cjs <in.html> <out.pdf> ["Footer title"]  — renders an HTML file to A4 PDF with page numbers.
const { chromium } = require('playwright'); const path = require('path'); const fs = require('fs');
(async () => {
  const [inp, out, title = ''] = process.argv.slice(2);
  const b = await chromium.launch(); const p = await b.newPage();
  await p.goto('file://' + path.resolve(inp), { waitUntil: 'networkidle' });
  await p.emulateMedia({ media: 'print' });
  await p.pdf({ path: out, format: 'A4', printBackground: true, preferCSSPageSize: true, displayHeaderFooter: true,
    headerTemplate: '<div></div>',
    footerTemplate: `<div style="width:100%;font:7.5pt 'Inter',Arial,sans-serif;color:#5b6670;padding:0 17mm;display:flex;justify-content:space-between"><span>${title.replace(/</g,'&lt;')}</span><span>Group 19 · Track 1 · ThreadPilot · page <span class="pageNumber"></span> of <span class="totalPages"></span></span></div>` });
  await b.close();
  const { execSync } = require('child_process');
  try { console.log(out, execSync(`python3 -c "import pypdf,sys;print(len(pypdf.PdfReader(sys.argv[1]).pages),'pages')" "${out}"`).toString().trim()); } catch { console.log(out, 'written'); }
})();
