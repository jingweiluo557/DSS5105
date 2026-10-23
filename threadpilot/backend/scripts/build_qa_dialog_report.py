"""Build a self-contained read-only QA report from retained first-run evidence."""
import csv,html,json,statistics,shutil
from pathlib import Path
from tests.test_workflow import SCENARIOS
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs/reports/intent-qa-20261023'
data=json.loads((OUT/'live-results.json').read_text(encoding='utf8'))
results=sorted(data['results'],key=lambda x:(x['case'],x['turn']))
source=list(csv.reader((OUT/'source.tsv').open(encoding='utf8'),delimiter='\t'))
H=lambda x:html.escape(str(x))
findings=[
('D01','P1','切换订单后，催办草稿仍绑定旧订单','本地新增测试失败','ORD-005 起草 → Open ORD-055 → Draft a chase-up for this order。active_order 已是 ORD-055，草稿却仍是 ORD-005。','chase_chat 优先使用旧 chase_context.order_ids，未依据当前选中订单重建任务。','切换订单时失效旧催办上下文；代词绑定需要显式一致性校验。','backend/app/services/chase_chat.py'),
('D02','P1','审核预览时改部门未更新收件人','本地新增测试失败','ORD-005 起草 → Preview draft 1 for Assembly instead。模型槽位已正确给出 ASSEMBLY，预览仍发送到 knitting@example.com。','send 分支只在 slots.recipient 存在时更新已选草稿，忽略新的 department。','部门变更必须重新计算收件人和预览，且旧确认立即失效。','backend/app/services/chase_chat.py'),
('D03','P1','多订单查询后的代词歧义未阻断','真实模型 E4 第2轮','先查询 ORD-005、ORD-055 的工序，再问 Is it late? 系统无澄清地回答 ORD-055。','多个独立任务顺序执行后 active_order 保留最后一单，缺少集合上下文。','多订单回答后保留候选集合，单数代词必须澄清。','backend/app/workflow_engine.py'),
('D04','P1','把窗口截止日期当作当前日期','真实模型 1.6 第1、2轮','业务时钟固定 2026-04-01，回答却说 As of Apr 8。','prioritize 返回 window_end=2026-04-08；narrate 输入没有单独的 business_now，模型误解释日期。','统一传入 business_now/window_start/window_end，关键日期由服务端渲染或校验。','backend/app/conversation.py'),
('D05','P2','澄清标志和最终回答不一致','真实模型 1.4 第3轮','Which one is more risky? 返回 needs_clarification=true，但自然语言直接宣布 ORD-005 更危险，未问比较标准。','澄清回答仍进入自由改写。','needs_clarification 时直接返回服务端问题，不交由模型改写。','backend/app/conversation.py'),
('D06','P2','取消语义缺少确定性状态处理','真实模型 E5 + 本地降级测试失败','正常模型把 Cancel, do not send. 生成一封正文为“我不会起草或发送”的新草稿；降级规则则重新打开发送预览。再次 send now 在真实模型测试中被阻止，未发送。','没有 cancel 动作；降级规则仅匹配 send，未处理否定。','新增明确取消处理，清空待确认动作并给出取消回执；不把取消语句写入邮件。','backend/app/conversation.py; backend/app/services/chase_chat.py'),
('D07','P2','联系人姓名可以进入不可发送的预览','真实模型 3.1 第2–5轮','Draft it to Maya → Send it → Send now。预览 To: Maya；最终才提示有效邮箱，而且误称 scheduling。','草稿预览未验证邮箱或解析联系人，校验推迟到真实发送层。','生成预览前解析姓名或追问邮箱；立即发送与定时发送错误文案区分。','backend/app/services/chase_chat.py; backend/app/workflow_engine.py'),
('D08','P2','邮件回复期限未按业务时钟固化','真实模型 3.1 第3轮、E7 第2–3轮','Ask for an answer by tomorrow noon. 草稿和预览仍保留 tomorrow noon，没有明确 2026-04-02 12:00 +08:00。','compose_chase 未接收 business_now；新 chase 路径未统一解析 deadline。','服务器将 deadline 解析为绝对业务日期，写入草稿/预览并保存。','backend/app/conversation.py; backend/app/services/chase_chat.py'),
('D09','P2','要求原始基准记录时只返回汇总','真实模型 2.1 第4轮','Show me the records behind it. 回答表示个别日期记录未包含，只给范围和均值。','narrate 的 results 包含工具结果，未包含 response.evidence；本次未单独验收前端证据面板是否足够补足。','将所选基准原始行提供给回答层，或明确导向可展开证据并进行 UI 验收。','backend/app/conversation.py'),
]
notes={('1.4',3):'D05：需要澄清的标志未落实到最终文字。',('1.6',1):'D04：当前日期误写为 Apr 8；另有需求差异：现产品默认查今天+七天，不先追问。',('1.6',2):'D04：再次将窗口截止日说成当前日期。',('2.1',4):'D09：回答未展示逐日基准行；前端证据面板待单独验收。',('3.1',2):'D07：Maya 未解析为邮箱。',('3.1',3):'D08：回复期限没有转为明确业务日期。',('3.1',4):'D07/D08：允许无效收件人进入预览、保留相对期限。',('3.1',5):'D07：实际安全阻止发送，但端到端任务未完成。',('E4-multi',2):'D03：应澄清指哪一单，实际默认最后一单。',('E5-cancel',3):'D06：未发送，但把取消指令变成新邮件正文。',('E5-cancel',4):'安全阻止确认。原脚本期望 unknown，但返回上次意图 execution.chase；这是测试标签预期差异，不记模型误识别。',('E7-reply-time',2):'D08：未固化相对回复时间。',('E7-reply-time',3):'D08：预览仍未固化日期。'}
scenario_notes=[
('1.1','模糊订单定位','基本完成','正确澄清客户、缩小范围、保存 active_order。种子数据仅一张 TrendCart scarf 订单，第二轮直接定位是正确行为，不能照抄示例要求继续追问。'),
('1.2','刷新活动订单','基本完成','工序/最后活动/今日更新均查询；没有虚构活动描述。'),
('1.3','风险与溯源','基本完成（数据限制）','预测与已逾期分离；承认没有逐事件历史，不能称已实现完整活动时间线。'),
('1.4','订单比较','部分完成','维度、对比和近交期排序可用；风险比较的澄清问题被改写丢失。'),
('1.5','新订单承诺','基本完成','交付地点、假设、packing loss 连续更新；未作无条件承诺。'),
('1.6','每日例外优先级','部分完成/规格差异','产品提示词明确默认两个窗口，和表格先追问的要求冲突；另有独立日期错误。'),
('2.1','产量正常性','部分完成','同星期基准、用户输入未核验的界限正确；原始行展示不足。'),
('2.2','偏差分析','基本完成','核实实际产量，不臆造停工、人员或因果关系；能给原始当天四工序记录。'),
('3.1','催办起草修改发送','部分完成','有效部门邮箱测试可走完模拟提交；表格中 Maya 姓名未解析，回复期限未固化；边界有错单/错部门风险。'),
('3.2','内部备注','基本完成','先确认订单，再预览原文，再保存；未自动增加“已联系供应商”等未经用户授权的内容。'),
('3.3','条件提醒','基本完成（接入边界）','明天12点→14点→确认→周五早晨追问时间有效；已有测试验证回复条件、更新不重复。回复依赖 /workflow/replies 事件，未验证 Outlook/Gmail 收信自动接入。'),
]
timings=[r['seconds'] for r in results if r.get('plan')]
body='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>ThreadPilot 意图与多轮对话测试报告</title><style>body{font:16px/1.65 system-ui,sans-serif;margin:0;color:#243640;background:#f5f7f7}main{max-width:1400px;margin:auto;padding:40px}h1,h2{color:#254d46}section{background:white;padding:24px;border-radius:14px;margin:24px 0}table{border-collapse:collapse;width:100%;font-size:14px}td,th{padding:12px;border:1px solid #d8e1df;vertical-align:top;text-align:left;overflow-wrap:anywhere}th{background:#e5eeea}pre{white-space:pre-wrap;font:14px/1.6 system-ui}small{color:#60706c}.bad{color:#9c3030}.ok{color:#35634b}details{margin:8px 0}input{padding:12px;width:90%;border:1px solid #b7cac1;border-radius:8px}.tag{background:#e6eeeb;padding:4px 8px;border-radius:6px}a{color:#256457}@media print{main{padding:0}section{break-inside:avoid}details>*{display:block}}</style><main>'''
body+='<h1>ThreadPilot 意图识别与多轮对话验收</h1><p>执行日期：2026-10-23 · 业务时间：2026-04-01 09:00 +08:00</p>'
body+='<section><h2>结论</h2><p><b>主要场景能正确进入对应业务流程，但尚不满足“多轮执行稳定完成”的验收条件。</b>主要风险在订单/部门上下文切换、澄清落实、取消和时间解释。建议先修复 P1 问题，再做真实外部发送演示。</p><ul><li>既有本地回归：77/77 通过，2 条依赖弃用警告。</li><li>新增边界：4 项，1 通过、3 失败；失败用例保留，未修改生产实现掩盖问题。</li><li>真实模型：18 组、66 轮完成；61 轮调用规划器，5 轮由确定性确认逻辑处理；无模型降级、无异常。</li><li>参考表格45轮返回意图标签均符合基准；这不等于45轮业务行为全部合格。扩展测试唯一标签差异是无待确认动作时沿用旧意图，不属于模型分类错误。</li><li>邮件通道全部替身：仅 E3 最后确认产生一次模拟 accepted；真实外发 0 封。</li></ul>'
body+=f'<p>模型：{H(data["model"])} / {H(data["api_style"])}。61轮模型驱动响应的端到端耗时中位数 {statistics.median(timings):.2f}s，最大 {max(timings):.2f}s；不是并发压测指标。</p></section>'
body+='<section><h2>范围、来源与限制</h2><p><a href="https://docs.google.com/spreadsheets/d/1B8XUomWD2RnH0SfSCVY7tEsLA02-afd9RB77SBZRpjQ/edit?gid=0">Multi-turn dialogues 原始表格</a>：11场景、45轮；本次已读取，45轮输入与仓库 dialogs.json 一致。示例答案明确不是事实，结果按实际种子数据判断。</p><p>真实模型路径为 ConversationAgent → WorkflowEngine；业务数据使用项目 CSV 回归种子，独立 SQLite 会话/邮件库、固定业务时钟。没有更改生产数据库、正式邮箱设置或实际邮件；生产 MySQL、浏览器完整链路和真实收件投递不在本次联调覆盖内。每场景仅运行一次，不构成稳定性统计；不将预设规划器测试视为真实意图准确率。</p><p>以下“基本完成”仅指本次样本。晨报、审核理由、插单分析属于额外能力，其本地测试已纳入部分回归，但本次没有完整真实模型覆盖。没有改写原 Google 表格。</p></section>'
body+='<section><h2>逐场景完成度</h2><table><tr><th>编号</th><th>场景</th><th>评估</th><th>依据与限制</th></tr>'
body+=''.join('<tr>'+''.join('<td>'+H(v)+'</td>' for v in row)+'</tr>' for row in scenario_notes)+'</table></section>'
body+='<section><h2>问题清单与修复顺序</h2><p>P1：可能选择错误对象或给出错误业务日期；P2：闭环/澄清/交互存在缺口。未发现本次未确认即真实发送；确认和幂等保护仍应保留。</p>'
for fid,priority,title,evidence,repro,cause,fix,path in findings:
 body+=f'<h3>{fid} · {priority} · {H(title)}</h3><p><b>证据：</b>{H(evidence)}<br><b>复现/实际：</b>{H(repro)}<br><b>代码定位/判断：</b>{H(cause)}<br><b>建议：</b>{H(fix)}<br><small>{H(path)}</small></p>'
body+='</section><section><h2>可复用用例与逐轮实际结果（66轮）</h2><p>先按组顺序执行，沿用该组 session；1.2/1.3/3.2/3.3 预置 active_order=ORD-005。其他组从空会话开始。测试邮箱为 example.com 且发送替身启用。展开查看完整输入输出；可搜索编号、关键词或问题编号。</p><input id="filter" placeholder="筛选，例如：3.1、D04、取消、ORD-055"><div id="cases">'
for r in results:
 key=(r['case'],r['turn']);note=notes.get(key,'本轮未发现偏差；以场景结论和测试范围为准。')
 if r['case'] in SCENARIOS:
  source_row=SCENARIOS[r['case']][r['turn']-1][0]
  expected=source[source_row-1][4]+'\n示例（非真实业务事实）：'+source[source_row-1][6]
 else:
  expected={'E1-switch-resume':'跨话题后恢复数量、产品、交期与交付地点。','E2-zh-entity':'中文输入正确澄清和绑定唯一订单。','E3-department':'生成/修改不发送，审核后才提交一次且记录精确正文。','E4-multi':'多个订单查询保留集合，后续 it 应澄清。','E5-cancel':'取消后没有待发送动作，不生成可发送的取消正文，后续裸确认无效。','E6-invalid':'无效订单需澄清，越权外发指令不执行。','E7-reply-time':'回复期限按业务时钟明确为2026-04-02 12:00 +08:00；与发送时间分开。'}[r['case']]
 body+=f'<details class="case"><summary><b>{H(r["case"])} / T{r["turn"]}</b> · {H(r["input"])} <span class="tag">{H(r.get("intent","error"))}</span></summary><p class="{ "bad" if key in notes else "ok"}">{H(note)}</p><table><tr><th>预期行为</th><td><pre>{H(expected)}</pre></td></tr><tr><th>实际回答</th><td><pre>{H(r.get("answer",r.get("error","")))}</pre></td></tr><tr><th>执行证据</th><td>澄清={H(r.get("clarification"))}；确认预览={H(r.get("confirmation"))}；活动订单={H(r.get("active_order"))}；本轮模拟提交={r.get("sends_this_turn",0)}；耗时={r["seconds"]}秒<br>工具：{H(r.get("tools"))}</td></tr></table></details>'
body+='</div></section><section><h2>复测准入与保留证据</h2><ol><li>先修复 D01–D04，要求新增边界用例通过；错单/错收件人不能仅靠提示词防护。</li><li>修复澄清、取消、姓名解析和日期归一化；覆盖中英文、否定、改口、明确指定部门、多订单与会话恢复。</li><li>真实模型关键场景至少各重复3次，再通过实际配置的 MySQL/API/SSE/UI 链路验收。</li><li>真实发送另行逐封授权，核对 provider accepted、Sent Items、收件箱；不能把202当成投递成功。</li></ol><p>原始证据：<a href="live-results.json">66轮模型结果</a> · <a href="regression.xml">77项回归JUnit</a> · <a href="boundaries.xml">新增边界JUnit</a> · <a href="source.tsv">参考表格快照</a>。测试脚本保留在 backend/scripts/qa_dialog_audit.py 和 backend/tests/test_qa_dialog_boundaries.py；后者3项当前失败是本次发现的待修复缺陷。</p></section></main><script>document.getElementById("filter").oninput=e=>document.querySelectorAll(".case").forEach(x=>x.hidden=!x.textContent.toLowerCase().includes(e.target.value.toLowerCase()))</script></html>'
(OUT/'report.html').write_text(body,encoding='utf8')
for sourcefile,dest in [('qa-intent-20261023.xml','regression.xml'),('qa-boundaries-20261023.xml','boundaries.xml')]:
 shutil.copyfile(ROOT/'backend/runtime'/sourcefile,OUT/dest)
print('Report written:',OUT/'report.html')
