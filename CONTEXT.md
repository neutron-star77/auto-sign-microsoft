# CONTEXT.md — 微软积分自动签到（auto-sign/microsoft）统一语言

> 本文件是**项目词汇的单一真相源**。凡参与本仓库改动（新会话/模型/human）先读这里，
> 术语含义以此为准，避免一话多义、一个词干多职。文档链：本文件 → `docs/adr/` →
> 代码注释。任何拟新增/改写术语，先在本表定稿再落盘。

最后更新：2026-09-16（W2 审计 + 周门控落地后）

---

## 1. 一句话目标
以最像真人、最低风控的方式，稳定地把微软 Rewards 的**每日/每周/每月可白嫖积分**自动拿到手：真实鼠标操作、随机时刻调度、绿勾即完成即跳过、每周一次、翻车可回滚。

## 2. 术语表（按字母序）

| 术语 | 领域含义（本仓库口径） | 别把它误当成 | 落地位置/信号 |
|---|---|---|---|
| **earn 页** | 积分任务主页面 `rewards.bing.com/earn`，任务卡片集中地 | dashboard 页 | 打开后逐卡处理 |
| **dashboard 页** | `rewards.bing.com/rewards/dashboard`，积分余额/目标/搜索额度 | earn 页 | 积分自审读点 |
| **每日活动 / Daily Set** | 每日线性任务组，`task_dashboard_daily_set` 处理，Diary 底部卡片(旧)/每日一组 | 日常任务 | earn 页 |
| **日常任务** | 「点击若干拼图/搜索卡片」这一类散卡 | 每日活动 | `process_offers` / `run_offer` |
| **今日积分卡 / search card** | earn 顶部的搜索卡片，`task_search_card` | 购物卡 | 搜索额度 |
| **本月攻略 / 月度打卡 punchcard** | 卡上「本月攻略」，点开进入 4 周 punchcard 详情；`task_monthly_strategy` 处理 | 每日活动 | `a[href*="BingMonthlyPC"]` |
| **周任务 / 周任务行** | punchcard 详情里每个自然周一行；行 = 状态徽章 + 标题 +（可选的）前往链接 | 单次打卡键 | 行容器 DOM |
| **绿勾** | 某周已完成的正向信号 = 徽章类 **`bg-statusSuccessRewardsBg`** | 空圈/锁定 | 唯一完成信号 |
| **锁定周** | 未到开放时间的周 = 锁图标 或文案 `4周后|⑤周后|到期日期|未解锁…`；**一律不点击、不判未完成** | 已/未完成 | 行内锁 + 文案 |
| **前往链接** | 开放周里的跳转链接，真人点击后弹搜索页即可计分 | 任意链接 | 行内首个非导航 `<a>` |
| **拟真化阅读** | 弹页 = 随机滚动 + 停留 8~18s（`humanize_read`），模拟真人阅读计分 | 纯 `sleep` | `humanize_read()` |
| **每周门控** | 同一自然周内"已点过且未翻绿→不重复点"；翻绿→整周不再碰；跨周自动重置 | 每日限流 | `weekly_click_state.json` |
| **积分自审 / 涨分校验** | 点击后 reload 重扫确认绿勾翻转；对比计分，区分"没点到"与"点了不计分" | 只看日志 | 事后复检 |
| **拼图 / 拼图验证** | Bing 弹出的滑块拼图，`skip_puzzle` 尝试自动跳过 | quiz | 弹页 |
| **问答 quiz** | 选择题任务，回答拿积分 | 拼图 | 弹页 |
| **flyout / 活动侧边栏** | 点击卡片弹出的右侧活动栏，内含若干跳转链接 | earn 页本体 | `find_flyout` |
| **`storage_state.json`** | **登录态 cookie 缓存，属敏感文件，禁止进版本库** | 普通配置 | `data/`（已 gitignore） |
| **调度唯一事实源** | 触发本项目的**唯一**正式入口 = `nas_cron.sh`（含 `--now/--force/disabled.flag` 语义）；任何"怎么触发"的改动只改它 | 手动 ssh 起容器 | `nas_cron.sh` |
| **profile / data 卷** | 持久化的浏览器 profile 与日志、状态文件，挂载 `<scriptdir>:/app` | 仓库代码 | `/app/data` |
| **周门控状态文件** | `weekly_click_state.json`：记录 `{week, clicked, done}`，实现"每周一次" | 页面绿勾 | `weekly_click_state.json` |
| **W2 / w2 副本** | 2026-09-16 审计重构产物 `rewards_earn.py.w2`（已提升为主版本，原版留 `.bak.W2pre_*`） | 主源 | 主源=w2 |

## 3. 本仓库"变化最快、最怕拍脑袋"的三处（改前必读对应 ADR）
1. **调度与立即模式限流** → `docs/adr/0001-*.md`
2. **earn/月任务 DOM 判完成信号与涨分自审** → `docs/adr/0002-*.md`
3. **周任务门控、拟真阅读、绿勾即跳过** → `docs/adr/0003-*.md`

## 4. 版本与回滚
- 本仓库**非 Git**，回滚靠 `.bak.<原因>_<YYYYMMDD>` 双端（本地+NAS）备份；详见 `非git回滚改进建议_2026-09-16.md`。
- 上生产分支＝通过 `nas_push.ps1`（NAS 上，`rewards_earn.py` 与本地源保持 md5 一致）。