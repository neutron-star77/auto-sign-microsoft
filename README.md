# 微软积分自动签到（auto-sign/microsoft）

> 适用环境：QNAP NAS（QTS）+ Container Station（Docker），或本地 Windows（Playwright + Edge 持久化登录态）。
> 配套文件：`rewards_earn.py`（主流程）、`nas_cron.sh`（NAS 调度入口）、`run_health_watchdog.py`（每日运行看门狗）、`monthly_watchdog.py`（月度进度看门狗）、`config.json`（账号与邮件配置）。

---

## 一、这套东西在做什么

每天在 **08:00–20:00** 之间随机挑两个时刻，用 Playwright 驱动浏览器把微软 Rewards 的每日任务（每日活动 Daily Set、搜索、日常任务）跑一遍，并把结果写进日志与状态文件。

两条硬规则：

1. **只在需要你介入时才发邮件**（失败 / 有遗留任务 / 结构性异常），成功不发。
2. **每天 21:00 判定一次**：当天没有成功签到，立刻发一封告警邮件——用来覆盖「程序压根没跑起来」这类静默失败。

---

## 二、时间窗与判定时刻

| 项目 | 值 | 落地位置 |
|---|---|---|
| 签到触发窗 | 每日 **08:00–20:00**，随机两个槽位 | `nas_cron.sh`（`RANDOM % 721 + 480` 分钟偏移，最晚槽位正好 20:00） |
| 槽位随机延迟 | 0–30 分钟（`REWARDS_SCHEDULED_DELAY_MAX_SECONDS`，默认 1800） | `nas_cron.sh` |
| 每日判定时刻 | **21:00**（`REWARDS_HEALTH_CHECK_HOUR`，默认 21） | `run_health_watchdog.py` + `nas_cron.sh` 钩子 |
| 跨项目兜底判定 | img.ink 的 `watchdog.py` 每晚 23:30 会顺带调一次本项目的判定 | `auto_sign/watchdog.py` |

> 为什么槽位最晚卡在 20:00 而不是 20:59：槽位后面还要叠加最多 30 分钟随机延迟，若槽位能到 20:59，实际启动会滑过 21:00，当天判定就会误报「未成功」。

---

## 三、部署（NAS）

```bash
# 1) 目录
/share/CACHEDEV1_DATA/Web/gadget/microsoft

# 2) 构建镜像（一次即可）
/share/CACHEDEV1_DATA/.qpkg/container-station/bin/docker build -t ms-rewards /share/CACHEDEV1_DATA/Web/gadget/microsoft

# 3) crontab（生产环境由 nas_selfheal.sh 统一写入，勿手改）
*/15 * * * * /bin/sh /share/CACHEDEV1_DATA/Web/gadget/microsoft/nas_cron.sh >> /share/CACHEDEV1_DATA/Web/gadget/microsoft/nas.log 2>&1
```

`nas_cron.sh` 每 15 分钟被唤醒一次，内部自己做三件事：生成当天两个随机槽位 → 到点拉起一次性容器跑签到 → 21:00 之后跑每日判定。

---

## 四、配置（config.json）

```json
{
  "email_notify": {
    "enabled": true,
    "smtp_server": "smtp.qq.com",
    "smtp_port": 465,
    "sender": "你的QQ邮箱@qq.com",
    "auth_code": "QQ邮箱SMTP授权码",
    "recipient": "接收告警的邮箱@qq.com"
  }
}
```

- `auth_code` 是 **QQ 邮箱设置 → 账户 → POP3/IMAP/SMTP 服务** 里生成的授权码，不是登录密码；改密码或重新生成后旧码立即失效（2026-10-31 至 11-16 的邮件静默就是这个原因）。
- 可用环境变量覆盖：`REWARDS_MAIL_ENABLED / SERVER / PORT / SENDER / AUTH / RECIPIENT`。
- 本项目配置不入库（`.gitignore` 只跟踪 `config.example.json`）。

---

## 五、邮件规则（2026-11-16 起）

主流程 `_notify_mail()` 在入口处统一过滤：**全部成功且无遗留任务 → 直接跳过**。会发信的情形只有三类：

| 情形 | 触发条件 | 同日去重 |
|---|---|---|
| 硬失败 | 抛异常（`TOU_REQUIRED`、`AUTH_EXPIRED`、导航失败等） | 是，`data/mail_notify_state.json` |
| 有遗留任务 | `run_state.unfinished` 非空（标题带「部分未完成(N)」） | 是 |
| 结构性异常 | 本月攻略整月零匹配等（正文追加「结构异常」段） | 是 |

另外两路独立告警：

- `run_health_watchdog.py`：**21:00 当天未成功 → 立即告警**（见 `docs/run-health-watchdog.md`）。
- `monthly_watchdog.py`：每月 5/15/25 检查本月攻略进度，落后即告警。

---

## 六、状态文件一览（都在 `data/`）

| 文件 | 谁写 | 用途 |
|---|---|---|
| `schedule.txt` | `nas_cron.sh` | 当天两个随机槽位与 DONE 标记 |
| `run_heartbeat.json` | `rewards_earn.py` | 最近一次运行心跳 + `last_ok_date`（看门狗据此判定） |
| `run_health_checked.json` | `run_health_watchdog.py` | 当天是否已判定过（一天只判一次） |
| `mail_notify_state.json` | `rewards_earn.py` | 失败/未完成邮件同日去重 |
| `monthly_state.json` | `rewards_earn.py` | 本月攻略进度（月度看门狗消费） |
| `auth_required.json` | `rewards_earn.py` | 认证熔断标记，存在即暂停调度直到人工重登 |
| `run_*.log` | 主流程 | 每次运行的完整日志 |

---

## 七、日常操作

```bash
# 立刻跑一次（排障用，随机延迟 ≤1 分钟）
/bin/sh /share/CACHEDEV1_DATA/Web/gadget/microsoft/nas_cron.sh --now

# 手动跑每日判定（不看时间门限的临时改法）
REWARDS_HEALTH_CHECK_HOUR=1 /opt/python3/bin/python3 run_health_watchdog.py

# 只读复检（不做任务、不发邮件）
/opt/python3/bin/python3 rewards_earn.py verify
```

暂停计划任务：在项目根放一个 `disabled.flag`（面板「暂停」按钮即写它）；判定器看到该文件会跳过，不会误告警。

---

## 八、排障顺序

1. `tail -n 50 data/nas.log` —— 调度层日志：有没有生成槽位、有没有到点、容器 rc 多少。
2. `tail -n 30 data/watchdog.log` —— 两只看门狗的输出（每日判定 + 月度进度）。
3. `cat data/run_heartbeat.json` —— 最近一次运行的 ok / failed / unfinished / `last_ok_date`。
4. `cat data/schedule.txt` —— 今天的两个槽位与 DONE 标记（DONE=0 且已过槽位说明没跑成）。
5. `ls data/auth_required.json` —— 存在即登录态失效，需在 Windows 重新导出 `storage_state.json`。
6. `docker images | grep ms-rewards` —— 镜像是否还在。

---

## 九、文档索引

- `CONTEXT.md` —— 项目统一语言（术语单一真相源）
- `docs/run-health-watchdog.md` —— 每日运行看门狗说明
- `docs/adr/` —— 架构决策记录（调度单一信源、月度打卡、认证熔断等）
- `docs/NAS_DEPLOY.md` —— NAS 部署细节
- `CLAUDE.md` —— 本仓库对 AI 助手的施工纪律