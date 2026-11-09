"""Ideal planner readings for the held-out set (heldout.json, written by a separate agent from the CSVs only).
Each reading is what a correct planner returns under the planner's documented contract: the intent, and the IDs, customer,
product, stage, dates and criteria the message states. Written once, before running, and not changed after seeing results.
A list = one reading per turn."""
L = lambda *ids, **k: dict(intent='order.lookup', order_ids=list(ids), reference='explicit', **k)
S = lambda **k: dict(intent='order.summary', **k)
RK = lambda **k: dict(intent='order.rank', **k)
CP = lambda *ids, **k: dict(intent='order.compare', order_ids=list(ids), reference='explicit', **k)
N = lambda **k: dict(intent='operations.normality', **k)
O = lambda **k: dict(intent='operations.output', **k)

A = {
 'L01': L('ORD-045'), 'L02': L('ORD-062'), 'L03': L('ORD-107'), 'L04': L('ORD-036'), 'L05': L('ORD-081'),
 'L06': L('ORD-057'), 'L07': L('ORD-099'), 'L08': L('ORD-008'), 'L09': L('ORD-120'), 'L10': L('ORD-002'),
 'A01': S(), 'A02': S(stage='WASHING'), 'A03': S(customer='Harbor Knits'), 'A04': S(customer='Loom & Leaf'),
 'A05': S(), 'A06': S(stage='KNITTING'), 'A07': S(), 'A08': S(),
 'A09': S(customer='Northwind Apparel'), 'A10': S(stage='ASSEMBLY'),
 'R01': RK(criterion='idle_days'), 'R02': RK(criterion='due_date'), 'R03': dict(intent='order.prioritize', window_days=0),
 'R04': dict(intent='order.compare'), 'R05': dict(intent='order.compare'), 'R06': RK(criterion='due_date'),
 'R07': dict(intent='order.prioritize', stage='WASHING', window_days=7), 'R08': RK(criterion='idle_days', stage='KNITTING'),
 'C01': CP('ORD-053', 'ORD-015', comparison_fields=['due_date']), 'C02': CP('ORD-062', 'ORD-103', comparison_fields=['current_stage']),
 'C03': CP('ORD-081', 'ORD-066', comparison_fields=['pieces']), 'C04': CP('ORD-083', 'ORD-002', comparison_fields=['due_date']),
 'C05': dict(intent='order.compare'), 'C06': CP('ORD-099', 'ORD-103', comparison_fields=['due_date']),
 'C07': CP('ORD-114', 'ORD-109', comparison_fields=['current_stage']), 'C08': dict(intent='order.compare'),
 'P01': O(stage='PACKING', target_date='2026-03-28'), 'P02': O(stage='WASHING', target_date='2026-03-29'),
 'P03': N(stage='ASSEMBLY', target_date='yesterday'), 'P04': N(stage='KNITTING', target_date='2026-03-13'),
 'P05': N(stage='WASHING', target_date='2026-03-09'), 'P06': N(stage='PACKING', target_date='2026-03-27'),
 'P07': N(stage='KNITTING', target_date='yesterday'), 'P08': N(stage='WASHING', target_date='2026-03-20'),
 'P09': N(stage='WASHING', target_date='2026-03-26'), 'P10': N(stage='KNITTING', observed_output=1000),
 'X01': dict(intent='execution.chase', action='draft', order_ids=['ORD-120'], reference='explicit', department='ASSEMBLY'),
 'X02': dict(intent='execution.chase', action='draft', order_ids=['ORD-053'], reference='explicit', recipient='QuickStitch'),
 'X03': dict(intent='execution.chase', action='send', order_ids=['ORD-083'], reference='explicit', department='WASHING'),
 'X04': dict(intent='execution.chase', action='send', order_ids=['ORD-045'], reference='explicit', recipient='SteadyHands'),
 'X05': dict(intent='general.unanswerable', reason='external', order_ids=['ORD-107'], customer='Northwind Apparel'),
 'X06': dict(intent='general.unanswerable', reason='external', customer='Cotton Club'),
 'X07': dict(intent='execution.reminder', action='create', order_ids=['ORD-002'], reference='explicit', condition='no_activity'),
 'X08': dict(intent='execution.reminder', action='create', order_ids=['ORD-061'], reference='explicit', condition='no_activity', deadline='2026-04-03T09:00'),
 'N01': L('ORD-150'), 'N02': L('ORD-121'), 'N03': S(customer='Bluewater Textiles'), 'N04': dict(intent='order.lookup', product='sock'),
 'N05': O(target_date='yesterday'), 'N06': O(stage='PACKING', target_date='today'),
 'N07': dict(intent='execution.chase', action='draft', order_ids=['ORD-045'], reference='explicit', recipient='SilkRoute'),
 'N08': dict(intent='order.lookup', customer='Patagonia'),
 'M01': [dict(intent='order.prioritize', window_days=0), dict(intent='order.lookup', reference='active')],
 'M02': [CP('ORD-053', 'ORD-036', comparison_fields=['due_date']), dict(intent='order.lookup', reference='active')],
 'M03': [dict(intent='order.prioritize', customer='Cotton Club', window_days=0), S(customer='Cotton Club')],
 'M04': [RK(criterion='idle_days'), RK(criterion='idle_days')],
 'M05': [L('ORD-061'), dict(intent='execution.chase', action='draft', reference='active', department='WASHING')],
 'M06': [S(customer='TrendCart'), dict(intent='order.lookup', customer='TrendCart', criterion='due_date')],
 'M07': [O(stage='ASSEMBLY', target_date='2026-03-25'), N(stage='ASSEMBLY', target_date='2026-03-25')],
 'M08': [L('ORD-029'), dict(intent='order.risk', reference='active')],
}
