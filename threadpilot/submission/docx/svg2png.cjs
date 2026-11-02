const { chromium } = require('playwright'); const fs = require('fs'); const path = require('path');
(async () => {
  const html = fs.readFileSync('Documentation.html', 'utf8');
  const style = html.match(/<style>([\s\S]*?)<\/style>/)[1]; const svg = html.match(/<svg class="arch"[\s\S]*?<\/svg>/)[0];
  const b = await chromium.launch(); const p = await b.newPage({ viewport: { width: 1520, height: 820 }, deviceScaleFactor: 2 });
  await p.setContent(`<html><head><link rel="stylesheet" href="file://${path.resolve('style.css')}"><style>${style} body{margin:0;background:#fff} figure{margin:0;width:1520px}</style></head><body><figure>${svg}</figure></body></html>`, { waitUntil: 'load' });
  await p.locator('svg').screenshot({ path: 'docx/arch.png' }); await b.close(); console.log('arch.png');
})();
