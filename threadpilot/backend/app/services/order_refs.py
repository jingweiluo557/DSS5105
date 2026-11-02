"""Order references the way people write or say them, turned into the form the system uses.

"ORD 080", "ord080", "order ID 080", "order number 7", "O R D zero zero five" -> ORD-080, ORD-080, ORD-080, ORD-007, ORD-005.
A bare "order 500" is left alone: it is as likely to be a quantity ("can we take order 500 hoodies"). Used on typed messages
before the explicit-ID rule in the workflow engine, and on voice transcripts (api/voice_api.py)."""
import re

DIGITS = {'zero': '0', 'oh': '0', 'o': '0', 'one': '1', 'two': '2', 'to': '2', 'too': '2', 'three': '3', 'four': '4', 'for': '4',
          'five': '5', 'six': '6', 'seven': '7', 'eight': '8', 'nine': '9'}
ORDER_RE = re.compile(r"\b(?:o\.?\s*r\.?\s*d\.?|ord|or\s+d|order\s+(?:number|no\.?|id))[\s\-#:]*((?:\d|zero|oh|one|two|three|four|five|six|seven|eight|nine)(?:[\s\-]*(?:\d|zero|oh|one|two|three|four|five|six|seven|eight|nine)){0,2})\b", re.I)


def normalize_order_refs(text: str) -> str:
    def repl(m: re.Match) -> str:
        digits = ''.join(DIGITS.get(t.lower(), t) for t in re.findall(r'\d+|[a-z]+', m.group(1), re.I))
        return f'ORD-{int(digits):03d}' if digits.isdigit() and 0 < int(digits) < 1000 else m.group(0)
    return ORDER_RE.sub(repl, text or '')
