"""Insert the generated table fragments into a document before rendering."""
import sys
from pathlib import Path
src, out = Path(sys.argv[1]), Path(sys.argv[2])
s = src.read_text(encoding='utf-8')
for tag, frag in [('<!--TOOLS-->', 'tools.html'), ('<!--EVALSET-->', 'evalset.html'), ('<!--HELDOUT-->', 'heldout.html'), ('<!--BAIT-->', 'bait.html'), ('<!--HELDOUT70-->', 'heldout70.html')]:
    if tag in s: s = s.replace(tag, (Path('fragments') / frag).read_text(encoding='utf-8'))
out.write_text(s, encoding='utf-8')
