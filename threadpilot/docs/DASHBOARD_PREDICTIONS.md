# Dashboard 与预测数据核对（2026-10-10）

## 数据口径

本次提供的 `DSS5105_predict` 是订单延期风险与工坊产能情景估算，不是销量预测。原始文件保留不改；运行时读取 MySQL 中的导入批次和预测表。

- 120 个订单、360 条工序产量记录、8 个工坊，与现有数据匹配。
- 预测覆盖 34 个在制订单。由每条预测的 due_date − days_to_due 反推，参考日期均为 **2026-04-01**。
- JSON 导出时间在 2026-09-11，是文件生成时间；不能把它当作预测业务日期。
- 延期模型 HIGH ≥0.6，MEDIUM ≥0.35 且 <0.6，LOW <0.35：16 高、4 中、14 低。
- Order health 先分出实际逾期，再按模型划分未逾期订单：**8 逾期、9 风险、17 未达高风险阈值**，合计 34。与原有 Priority ≥60 规则分数不混用。
- 最近 30 个日历日按业务日期 `[2026-03-02, 2026-04-01)`、completed_date 统计：35 个完结订单，20 个按时或提前，57.1%。此前 30 日 27/44=61.4%。截图里的示例数值不用于业务计算。

## 预测适用范围

训练报告记录 86 个历史完结订单，随机分层拆分 64 训练、22 测试，测试 AUC 0.923、准确率 0.864。该结果来自提供的报告，未在此次改版重新训练或做时间外验证。

训练特征在订单到期日计算，推断特征在统一业务日期计算；工坊参数是当前快照。模型未使用订单实际剩余件数，也没有订单级生产记录。因此概率用于排序和复核，不能保证交期；后续适合增加按时间切分验证及概率校准。

产能估算公式：`整单件数 / (日产能 × (1−缺陷率)) + 排队天数 + 提货天数`。当前导出假定整单尚未完成、独占工坊产能，并将小数天转成日期；不包含联合排程和逐工序剩余工作。预测页面保留原始导出日期，不把它悄悄替换成重新计算的承诺日期。

诊断中的外协候选另按当前数据筛选 ACTIVE、品类匹配、满足批量限制的工坊，并比较完整的排队、生产与提货耗时；仍需人工确认实际剩余工作和可预留产能。

## 可生成的建议

固定最多三条：交期复核、薄弱工序产能检查、外协候选比较。它们是模型风险与透明规则形成的建议，不额外声称由大模型实时生成。每条提供数据来源入口；缺少销量数据时不生成销量或备货预测。

## 数据库与更新

- `prediction_batches`：业务日期、导入时间、模型报告、完整输入快照。
- `order_predictions`：每批次每订单一行；概率、风险等级、完工情景、建议工坊、原始特征与计算证据。
- 内容哈希标识批次，相同资产重复导入不增加行；导入在单个事务中完成。
- `/api/predictions` 与 `/api/predictions/{order_id}` 直接读取数据库。新页面在 Orders 后。
- Dashboard 只使用与当前业务日期和三份输入数据完全一致的批次；不匹配时停止使用旧模型结果，回退到原优先级规则。预测列表仍保留旧结果并显示“Archived forecast”。
- `backend/app/assets/order_forecasts.json` 是本次审查后的导入资产，来源是提供的 CSV 和完整 JSON；不加载 `.pkl` 执行代码。后续模型更新应重新生成该资产并重新导入，不能只替换页面数值。
- 已应用迁移 0003、0004，云数据库已导入 34 条预测。本次未修改现有业务订单。

从 backend 执行迁移和导入（先在进程环境中配置数据库连接，不把密码放在命令中）：

```powershell
python -m alembic upgrade head
python -m scripts.import_predictions
```

## 卡片图表

保留 In progress、Overdue、Due today、Idle ≥5 days、Priority ≥60 五项、现有字体和配色。

前三项在历史快照不足时按订单下单日、已记录交期和完结日重建近 7 天数量，图表说明为 recorded dates。若订单曾改期但未保留版本，无法还原当时的原交期。

后两项没有逐日活动与风险历史，先展示当前活动间隔、优先级分布折线，明确标注 distribution。积累至少两个业务日期的数据库快照后，改为真实记录的趋势。未填充虚构的每日数据。

## 待办与晨报

待办存储在 `dashboard_tasks`，按业务日期自动生成，跨设备共享。实际逾期、7 日内到期、预测高风险或 Priority≥60、5 日无活动合并为同一订单的一条待办。勾选只完成待办，不修改订单；仍满足规则的订单在下一个业务日期重新提示。手动输入支持幂等重试，更新使用版本检查。

Add chase-up 进入现有 AI 催办草稿与确认流程。实际发送仍取决于已配置的发送连接器，不会通过勾选待办发送消息。

晨报以 UTC+8 真实日期归档，内容按业务日期计算，每天 07:00 后只保存一份，重复触发不产生重复记录。宕机后恢复可以补存当天报告，保存实际生成时间；不会伪造漏掉日期的 07:00 报告。首次归档前显示 Live preview，预览本身不写入归档。

### CloudBase 发布时的操作

本机预览已启用晨报检查；本次未上传新版云后端或创建 CloudBase 触发器。本机关闭后本机检查不再运行。

1. 更新 HTTP 后端代码包 `dist/threadpilot-backend-python311.zip`。
2. 新建普通云函数 `threadpilot-morning-timer`，Python 3.11，上传 `dist/threadpilot-morning-timer.zip`；执行方法 `index.main_handler` 或 `index.main`。
3. 使用原提醒函数的 `BACKEND_ORIGIN`、`SCHEDULER_TOKEN` 配置；不要放到前端。开启公网访问，超时 120 秒。
4. 设置每日 UTC+8 07:00 定时触发。在控制台确认触发器使用的时区：UTC+8 的七段 Cron 为 `0 0 7 * * * *`；如果界面明确使用 UTC，则为 `0 0 23 * * * *`。函数内部再次用 UTC+8 校验，07:00 前不会生成。
5. 更新前端。验证 `/api/dashboard` 和 `/api/predictions`，手动测试晨报函数（07:00 后），确认归档后再检查下一次计划执行。

触发器配置和执行记录以控制台为准；单独上传 ZIP 不会创建定时触发器。参考：[CloudBase 定时触发器](https://docs.cloudbase.net/cloud-function/timer-trigger)、[腾讯云七段 Cron 说明](https://cloud.tencent.com/document/product/583/9708)。

## Morning summary email drafts

- Morning summary → Generate email builds an English draft from the selected latest saved briefing, including production, priority issues, decisions, up to three recommendations and handled items.
- One shared draft per archived report date; opening again preserves edits. Save, copy and EML download persist subject/body. No mail is sent by this feature.
- `briefing_email_drafts` stores subject, body, original report snapshot, version and UTC+8 timestamps. Migration `0005` is additive and has been applied to the configured CloudBase database.
- `POST /api/dashboard/briefings/{day}/email` creates or retrieves the draft. `PUT` saves with optimistic version checking; a conflict preserves browser edits. Existing workspace authentication applies.
- Generation uses the archived report, not a fresh model call or changing live data. Missing saved briefings return 404. Draft source snapshots remain unchanged after manual edits.
- Local preview loads these routes. Cloud function code and static frontend must be redeployed together for remote use; database migration alone does not deploy application code.
- Validation: backend coverage for authorization, archive grounding, idempotence, edits, stale versions and input validation; browser coverage for desktop/mobile, reopen, download encoding and preservation of unsaved edits on conflict.
