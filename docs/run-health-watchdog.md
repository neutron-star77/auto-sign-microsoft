# 每日运行看门狗（run_health_watchdog.py）

> 一句话：**每天 21:00 问一次「今天签到成功了吗」，没成功立刻发邮件，成功就闭嘴。**

---

## 一、为什么需要它

2026-11-16 起发信规则改成「仅失败才发」，噪音没了，但留下一个盲区：

> 「失败邮件」的前提是**程序跑起来了**。若进程根本没启动——cron 条目被剥离、容器起不来、登录态在 import 阶段就崩——既没有失败输出，也没有任何邮件，故障完全静默。

这不是假想：2026-08-19 crontab 里的自定义任务被固件更新清掉，两个签到项目一起静默了 5 天，直到人工发现。

---

## 二、依赖的心跳

主流程 `rewards_earn.py` 每次运行收尾写 `data/run_heartbeat.json`：

| 字段 | 含义 |
|---|---|
| `ts` / `date` | 本次运行时间与日期 |
| `ok` | **本轮既没失败、也没有遗留未完成任务** 才为 `true` |
| `failed` / `unfinished` / `error` | 失败标记、遗留任务数、错误摘要 |
| `points_before` / `points_after` | 运行前后可用积分（便于判断是真跑还是空转） |
| `last_ok_date` | **跨运行累积**：只由成功运行推进；失败运行不会抹掉它 |

> 关键设计：`ok` 只认「干净成功」。每天跑了但每天都失败，仍然算「不健康」——这正是需要你介入的状态。
> `last_ok_date` 必须跨运行累积，否则「连续失败」会被误读成「从未成功」。

---

## 三、判定矩阵

判定时刻 **21:00**（`REWARDS_HEALTH_CHECK_HOUR`，默认 21；21:00 之前一律不判，因为签到窗 08:00–20:00 还没走完）。

| 观察到的状态 | 结论 | 是否发信 |
|---|---|---|
| 心跳 `date == 今天` 且 `ok == true` | 今天成功了 | 不发，写一行 `[health] OK` |
| 心跳 `date == 今天` 但 `ok == false` | 跑了但没成功 | **立即发**，正文写「跑过但没成功」 |
| 心跳 `date` 不是今天 | 今天压根没跑 | **立即发**，正文写「今天没有任何运行记录」 |
| 心跳文件不存在 | 从未跑完过一次 | **立即发** |
| `disabled.flag` 存在 | 你主动暂停了 | 不发 |
| 今天已判定过（`run_health_checked.json`） | 一天只判一次 | 不再重复 |
| 21:00 时容器还在跑（`data/.run.lock` 新鲜） | 只是没跑完 | 推迟到下一个 15 分钟 tick |
| 邮件发送失败 | 通道问题 | 不标记已判定，下一个 tick 重试 |

---

## 四、调度接入（三条路，互为兜底）

| 触发源 | 频率 | 作用 |
|---|---|---|
| `nas_cron.sh` 内部钩子 | 每 15 分钟 tick，只在 21:00 之后真正执行 | 主路径；钩子放在 `disabled` / 认证墙等所有早退分支**之前**，否则那两类最需要告警的情况会被漏掉 |
| `auto_sign/watchdog.py` 跨项目调用 | 每晚 23:30 | 兜底：微软那条 cron 被单独删掉时，只要 img.ink 的 cron 还活着就仍会被判 |
| `nas_cron.sh` 同时调用 img.ink 的 watchdog | 21:00 之后 | 反向兜底：img.ink 的条目被删掉时由微软侧判它 |

三条路都读同一个 `run_health_checked.json`，所以一天最多一封，不会因为多个触发源而刷屏。

---

## 五、手动验证

```bash
cd /share/CACHEDEV1_DATA/Web/gadget/microsoft

# 正常调用（01 点跑会打印「未到判定时刻」并退出）
/opt/python3/bin/python3 run_health_watchdog.py

# 临时改判定时刻，验证逻辑（会按真实心跳判定并可能发信）
REWARDS_HEALTH_CHECK_HOUR=1 /opt/python3/bin/python3 run_health_watchdog.py

# 只看判定不发信：把邮件临时关掉
REWARDS_MAIL_ENABLED=false /opt/python3/bin/python3 run_health_watchdog.py
```

测试时可把 `BASE` 目录整体复制到 `/tmp/xxx` 下，放入夹具心跳与 `config.json`（`enabled=false`），改的是夹具、不污染生产状态。

---

## 六、状态文件

| 文件 | 说明 |
|---|---|
| `data/run_heartbeat.json` | 输入：主流程写的心跳 |
| `data/run_health_checked.json` | 输出：`{date, alerted, checked_at}`，当天是否已判定 |
| `data/watchdog.log` | 判定过程日志（`nas_cron.sh` 与 img.ink 兜底都追加到这里） |

---

## 七、排障

| 现象 | 原因 / 处理 |
|---|---|
| 21:00 收到告警但实际签到成功 | 心跳没写成功——查 `data/run_*.log` 结尾有没有 `[心跳] 已记录`；容器被 kill 会没有心跳 |
| 21:00 收到告警说「今天没有任何运行记录」 | 看 `schedule.txt` 槽位与 DONE；看 `nas.log` 有没有到点、`docker images` 镜像还在不在 |
| 一直不告警、以为一切正常 | 确认 `cat data/run_health_checked.json` 的 `date` 是否被误写成今天；确认 `disabled.flag` 不存在 |
| 一天收到两封 | 检查 `mail_notify_state.json`（失败邮件去重）与 `run_health_checked.json` 是否被外部删掉 |
| 想临时改判定时刻 | `REWARDS_HEALTH_CHECK_HOUR=20`，只影响判定，不改签到窗 |

---

## 八、局限（明确写清）

- **整张 crontab 被清空时，三条路一起失效**，看门狗不会说话。这种只能靠 cron 之外的机制（QNAP 任务计划、外部探活、面板定时自检）。
- 判定只回答「今天有没有一次干净的成功」，不判断积分涨了多少——积分差额请查 `data/run_*.log` 里的 `[积分自审]` 行。
- 心跳与判定都依赖 NAS 系统时间正确；RTC 归零时由 `nas_cron.sh` 的时钟自愈段先做 NTP 校准。