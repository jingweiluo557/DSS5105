"""Order references the way people write or say them, turned into the form the system uses.

"ORD 080", "ord080", "order ID 080", "order number 7", "O R D zero zero five" -> ORD-080, ORD-080, ORD-080, ORD-007, ORD-005.
A bare "order 500" is left alone: it is as likely to be a quantity ("can we take order 500 hoodies"). Used on typed messages
before the explicit-ID rule in the workflow engine, and on voice transcripts (api/voice_api.py)."""
import re

DIGITS = {'zero': '0', 'oh': '0', 'o': '0', 'one': '1', 'two': '2', 'to': '2', 'too': '2', 'three': '3', 'four': '4', 'for': '4',
          'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9'}
ORDER_RE = re.compile(r"\b(?:o\.?\s*r\.?\s*d\.?|ord|or\s+d|order\s+(?:number|no\.?|id))[\s\-#:]*((?:\d|zero|oh|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)(?:[\s\-]*(?:\d|zero|oh|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)){0,5})\b", re.I)


TENS = {'ten': 10, 'eleven': 11, 'twelve': 12, 'thirteen': 13, 'fourteen': 14, 'fifteen': 15, 'sixteen': 16, 'seventeen': 17, 'eighteen': 18, 'nineteen': 19,
        'twenty': 20, 'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60, 'seventy': 70, 'eighty': 80, 'ninety': 90}
WORDNUM = r"(?:\d+|zero|oh|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety)"
SHORTHAND = {'wk': 'week', 'wks': 'weeks', 'tmrw': 'tomorrow', 'tmr': 'tomorrow', 'tdy': 'today', 'yday': 'yesterday', 'pls': 'please', 'cust': 'customer',
             'mon': 'Monday', 'tue': 'Tuesday', 'tues': 'Tuesday', 'wed': 'Wednesday', 'thu': 'Thursday', 'thur': 'Thursday', 'thurs': 'Thursday', 'fri': 'Friday', 'sat': 'Saturday',
             'hrs': 'hours', 'hr': 'hour', 'pcs': 'pieces', 'qty': 'quantity', 'r': 'are', 'u': 'you', 'wat': 'what', 'wich': 'which'}


def expand_shorthand(text: str) -> str:
    """Manager shorthand into words the parsers know: "last wk" -> "last week", "tmrw" -> "tomorrow", "fri" -> "Friday"."""
    return re.sub(r"\b([A-Za-z]+)\b", lambda m: SHORTHAND.get(m.group(1).lower(), m.group(1)) if m.group(1).lower() in SHORTHAND else m.group(1), text or '')


def words_to_digits(tok: str) -> str:
    """'zero zero five' -> '005'; 'twenty nine' -> '29'; '0000029' -> '0000029'."""
    out, pending = [], None
    for t in re.findall(r'\d+|[a-z]+', tok, re.I):
        tl = t.lower()
        if tl in TENS:
            if pending is not None: out.append(str(pending))
            pending = TENS[tl]
        elif tl in DIGITS or t.isdigit():
            d = DIGITS.get(tl, t)
            if pending is not None and pending >= 20 and len(d) == 1 and d != '0':
                out.append(str(pending + int(d))); pending = None
            else:
                if pending is not None: out.append(str(pending)); pending = None
                out.append(d)
        else:
            return tok
    if pending is not None: out.append(str(pending))
    return ''.join(out)
# "order 5", "order 0000029", "order005", "order zero zero five", "orders 29 and 108": an order number only when it is an
# existing order and is not followed by a product or unit word ("order 500 hoodies" is a quantity).
NUMBER_RE = re.compile(r"\borders?\s*#?\s*(" + WORDNUM + r"(?:[\s\-]*" + WORDNUM + r"){0,3}(?:\s*(?:,|and|&|or|vs\.?|versus)\s*\d+)*)\b", re.I)


def normalize_order_numbers(text: str, known: set[int], products: set[str] = frozenset()) -> str:
    """Typed order numbers without the ORD- prefix, when they can only be order numbers. `known` = existing order numbers."""
    units = {'pieces', 'piece', 'pcs', 'pc', 'units', 'unit', 'days', 'day', 'hours', 'orders', 'percent', '%'} | {p.lower() for p in products} | {p.lower() + 's' for p in products}
    def one(tok: str) -> str:
        digits = words_to_digits(tok)
        return f'ORD-{int(digits):03d}' if digits.isdigit() and int(digits) in known else tok
    def repl(m: re.Match) -> str:
        after = text[m.end():m.end() + 24].strip().split(' ')[0].strip('.,;:!?').lower()
        if after in units or after.rstrip('s') in units: return m.group(0)
        parts = re.split(r'(\s*(?:,|\band\b|&|\bor\b|\bvs\.?|\bversus\b)\s*)', m.group(1), flags=re.I)
        out = [one(p) if i % 2 == 0 else p for i, p in enumerate(parts)]
        if all(o == p for o, p in zip(out[::2], parts[::2])): return m.group(0)
        return ''.join(out)
    text = NUMBER_RE.sub(repl, text or '')
    # "29 versus 108", "29 vs 108", "2 or 55" with no other words: two bare order numbers compared
    def pair(m: re.Match) -> str:
        a, b = int(m.group(1)), int(m.group(3))
        return f'ORD-{a:03d}{m.group(2)}ORD-{b:03d}' if a in known and b in known else m.group(0)
    text = re.sub(r'(?<![\w-])(\d{1,3})(\s*(?:vs\.?|versus|v\.)\s*)(\d{1,3})(?![\w-])', pair, text)
    def unit_follows(end: int) -> bool:
        words = [w.strip('.,;:!?').lower() for w in text[end:end + 40].strip().split(' ')[:2]] + ['', '']
        after = words[1] if words[0] in ('more', 'less', 'extra', 'working', 'calendar') and (words[1] in units or words[1].rstrip('s') in units or words[1] in ('week', 'weeks')) else words[0]
        return (after in units or after.rstrip('s') in units
                or after in {'%', 'am', 'pm', 'weeks', 'week', 'x', 'priority', 'priorities', 'choice', 'rule', 'issue', 'reason', 'thing', 'problem', 'concern', 'job', 'task', 'customer', 'stage'})
    # "#81 what stage", "chase washing on #83": a hash number is an order number when that order exists
    def hashed(m: re.Match) -> str:
        n = int(m.group(1))
        return f'ORD-{n:03d}' if n in known and not unit_follows(m.end()) else m.group(0)
    text = re.sub(r'(?<![\w#&-])#\s?(\d{1,3})(?![\w.,:/-]*\d)', hashed, text)
    # "002", "053": three digits with a leading zero are written as an order number, never as a quantity
    def padded(m: re.Match) -> str:
        n = int(m.group(1))
        return f'ORD-{n:03d}' if n in known and not unit_follows(m.end()) else m.group(0)
    text = re.sub(r'(?<![\w#.,:/-])(0\d{2})(?![\w.,:/-]*\d)(?![\w%])', padded, text)
    # "81 or 66 - which one's bigger", "is 83 or 2 more overdue": two bare numbers joined by "or" in a question that
    # compares two things. Without a comparing word ("2 or 3 days", "5 or 6 hundred") nothing is changed.
    if re.search(r"\b(which|bigger|larger|smaller|more|less|first|sooner|later|closer|further|farther|ahead|behind|overdue|late|riskier|compare|urgent)\b", text, re.I):
        def either(m: re.Match) -> str:
            a, b = int(m.group(1)), int(m.group(3))
            if a in known and b in known and a != b and not unit_follows(m.end()):
                return f'ORD-{a:03d}{m.group(2)}ORD-{b:03d}'
            return m.group(0)
        text = re.sub(r'(?<![\w#.,:/-])(\d{1,3})(\s+or\s+)(\d{1,3})(?![\w.,:/-]*\d)(?![\w%])', either, text, flags=re.I)
    return text


def normalize_order_refs(text: str) -> str:
    def repl(m: re.Match) -> str:
        digits = words_to_digits(m.group(1))
        return f'ORD-{int(digits):03d}' if digits.isdigit() and 0 < int(digits) < 1000 else m.group(0)
    return ORDER_RE.sub(repl, text or '')
