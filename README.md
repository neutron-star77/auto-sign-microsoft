# Microsoft Rewards 自动任务

基于 Playwright 的 Microsoft Rewards 自动任务工具：Windows 用 Edge 导出登录态，NAS 用 Docker 无头运行。程序**只使用已有登录态**，不保存、不上传 Microsoft 密码。

> 本项目仅用于个人自动化研究，请遵守 Microsoft Rewards 服务条款并自行承担使用风险。

## 当前入口

| 文件 | 用途 |
| --- | --- |
| `rewards_earn.py` | 唯一主程序：每日任务、搜索、本月攻略、登录态校验、心跳与邮件 |
| `nas_cron.sh` | NAS 调度入口（随机槽位、拉容器、每日判定） |
| `run_health_watchdog.py` | 每日运行看门狗：21:00 判定当天是否成功，未成功立即告警 |
| `monthly_watchdog.py` | 月度进度看门狗：每月 5/15/25 检查本月攻略进度 |
| `nas_autorun.sh` / `nas_selfheal.sh` | NAS 启动初始化 / 运行环境自愈 |
| `Dockerfile` | NAS 容器镜像 |
| `config.example.json` | 配置模板（复制为 `config.json` 后填自己的值） |
| `tests/` | 认证、月度状态与错误处理测试 |

---

## 一、时间窗与判定口径（2026-11-16 起）

| 项 | 值 | 落地位置 |
| --- | --- | --- |
| 签到触发窗 | 每日 **08:00–20:00**，随机两个槽位 | `nas_cron.sh`（分钟偏移抽样，最晚槽位正好 20:00） |
| 槽位随机延迟 | 0–30 分钟 | `REWARDS_SCHEDULED_DELAY_MAX_SECONDS`（默认 1800） |
| 每日判定时刻 | **21:00** | `run_health_watchdog.py`（`REWARDS_HEALTH_CHECK_HOUR`，默认 21） |
| 判定结论 | 当天有 `ok=true` 心跳就静默；否则 21:00 立即发一封告警 | 同上 |

> 为什么槽位卡在 20:00 而不是 20:59：槽位后还要叠加最多 30 分钟随机延迟，若允许 20:59，实际启动会滑过 21:00，当天判定就会误报「未成功」。

配套的图床签到项目（img.ink）使用**同一套口径**；两边的看门狗会互相兜底（任一侧 cron 被单独删掉，另一侧仍会判定）。

---

## 二、Windows 首次登录与导出

```powershell
cd <项目目录>
python -m pip install -r requirements.txt
python rewards_earn.py export
```

1. 关闭所有 Microsoft Edge 窗口，避免浏览器配置目录被锁定。
2. 执行 `python rewards_earn.py export`。
3. 在弹出的 Edge 窗口完成 Microsoft 登录、条款确认或验证码。
4. 回到终端按 Enter，确认看到 `storage_state 已写入`。
5. 生成的 `storage_state.json` 只用于部署到自己的 NAS，**不能提交到 GitHub 或 Gitee**。

若导出提示 `EXPORT_EDGE_CLOSED`，关闭残留 Edge 进程后重新执行；若页面停留在 `account.live.com/tou`，先在窗口中完成条款确认再按 Enter。

---

## 三、Windows 手动运行

```powershell
python rewards_earn.py
```

首次运行建议使用可见浏览器确认登录态。程序按页面的绿色勾选状态跳过已完成任务，不会重复点击。

只读复检（不做任务、不发邮件）：

```powershell
python rewards_earn.py verify
```

---

## 四、NAS / Docker 部署

部署到 NAS 应用目录（示例 `/share/CACHEDEV1_DATA/Web/gadget/microsoft`）：

```text
rewards_earn.py
run_health_watchdog.py
nas_cron.sh
monthly_watchdog.py
nas_autorun.sh
nas_selfheal.sh
Dockerfile
requirements_nas.txt
config.json              # 私有配置，不提交仓库
data/storage_state.json  # Windows 导出的登录态，不提交仓库
```

```bash
# 构建镜像（一次即可）
/share/CACHEDEV1_DATA/.qpkg/container-station/bin/docker build -t ms-rewards /share/CACHEDEV1_DATA/Web/gadget/microsoft

# crontab（生产环境由 nas_selfheal.sh 统一写入，勿手改）
*/15 * * * * /bin/sh /share/CACHEDEV1_DATA/Web/gadget/microsoft/nas_cron.sh >> /share/CACHEDEV1_DATA/Web/gadget/microsoft/nas.log 2>&1
```

`nas_cron.sh` 每 15 分钟被唤醒：生成当天两个随机槽位 → 到点拉起一次性容器 → 21:00 之后跑每日判定。

部署脚本应使用项目维护者提供的 NAS 推送工具，并指定远端项目目录；推送完成后必须检查文件哈希、换行符、权限和 Python 语法，不要用 `scp` 或直接管道覆盖文件。

---

## 五、配置

复制 `config.example.json` 为 `config.json` 并填写：

```json
{
  "email": "",
  "password": "",
  "email_notify": {
    "enabled": true,
    "smtp_server": "smtp.qq.com",
    "smtp_port": 465,
    "sender": "your_qq_mail@example.com",
    "auth_code": "你的SMTP授权码",
    "recipient": "your_qq_mail@example.com"
  }
}
```

- `auth_code` 是邮箱 **SMTP 授权码**，不是邮箱登录密码；改密码或重新生成后旧码立即失效。
- 也可用环境变量覆盖，避免把授权码写进文件：`REWARDS_MAIL_ENABLED / SERVER / PORT / SENDER / AUTH / RECIPIENT`。

---

## 六、邮件规则：只在需要你介入时发

主流程 `_notify_mail()` 在入口统一过滤——**全部成功且无遗留任务 → 直接跳过**。会发信的情形：

| 情形 | 触发条件 | 同日去重 |
| --- | --- | --- |
| 硬失败 | 抛异常（`TOU_REQUIRED`、`AUTH_EXPIRED`、导航失败等） | 是 |
| 有遗留任务 | `run_state.unfinished` 非空（标题带「部分未完成(N)」） | 是 |
| 结构性异常 | 本月攻略整月零匹配等（正文追加「结构异常」段） | 是 |
| 当天未成功 | 21:00 判定当天无 `ok=true` 心跳 | 是（一天一封） |

邮件正文包含：错误码与中文含义、自动处理结果、下一步动作、日志位置。

---

## 七、每日运行看门狗

`run_health_watchdog.py` 解决的问题：**失败邮件的前提是程序跑起来了**。若进程根本没启动（cron 被剥离、容器起不来、登录态在 import 阶段就崩），既没有失败输出也没有邮件——故障完全静默（2026-08-19 crontab 被清掉曾静默 5 天）。

判定依据是 `data/run_heartbeat.json`（主流程每次运行收尾写入）：

| 字段 | 含义 |
| --- | --- |
| `ok` | 本轮既没失败、也无遗留任务才为 `true` |
| `last_ok_date` | 跨运行累积，只由成功运行推进 |
| `points_before/after` | 运行前后积分，用于判断是否真跑 |

细节（判定矩阵、三条调度兜底、局限）见 [`docs/run-health-watchdog.md`](docs/run-health-watchdog.md)。

---

## 八、认证失败与恢复

Microsoft 可能要求重新确认条款、重新认证或完成验证码。程序会识别认证墙、写入 `data/auth_required.json`，暂停定时任务，并在邮件中给出中文含义与恢复步骤。**不会绕过条款确认或验证码**，也不保证第三方页面规则永久不变。

恢复流程：

1. Windows 执行 `python rewards_earn.py export`。
2. 在 Edge 中完成登录、条款确认或重新认证。
3. 把新的 `storage_state.json` 部署到 NAS 的 `data/storage_state.json`。
4. 重新运行一次任务，确认日志出现认证成功与积分校验结果。

认证失败期间 NAS 会自动暂停重复调度；只有检测到新的登录态指纹才恢复。

---

## 九、状态文件（都在 `data/`）

| 文件 | 谁写 | 用途 |
| --- | --- | --- |
| `schedule.txt` | `nas_cron.sh` | 当天两个随机槽位与 DONE 标记 |
| `run_heartbeat.json` | `rewards_earn.py` | 最近一次运行心跳 + `last_ok_date` |
| `run_health_checked.json` | `run_health_watchdog.py` | 当天是否已判定过 |
| `mail_notify_state.json` | `rewards_earn.py` | 邮件同日去重 |
| `monthly_state.json` | `rewards_earn.py` | 本月攻略进度 |
| `auth_required.json` | `rewards_earn.py` | 认证熔断标记 |
| `run_*.log` | 主程序 | 每次运行完整日志 |

---

## 十、日常操作

```bash
# 立刻跑一次（排障用，随机延迟 ≤1 分钟）
/bin/sh nas_cron.sh --now

# 手动跑每日判定（临时绕过 21:00 门限）
REWARDS_HEALTH_CHECK_HOUR=1 /opt/python3/bin/python3 run_health_watchdog.py

# 只读复检
/opt/python3/bin/python3 rewards_earn.py verify
```

暂停计划任务：在项目根放 `disabled.flag`（面板「暂停」按钮即写它）；判定器看到它会跳过，不会误告警。

---

## 十一、排障顺序

1. `tail -n 50 data/nas.log` —— 调度层：有没有生成槽位、有没有到点、容器 rc。
2. `tail -n 30 data/watchdog.log` —— 两只看门狗的输出。
3. `cat data/run_heartbeat.json` —— 最近一次运行的 ok / unfinished / `last_ok_date`。
4. `cat data/schedule.txt` —— 今天的槽位与 DONE 标记（DONE=0 且已过槽位说明没跑成）。
5. `ls data/auth_required.json` —— 存在即登录态失效，需重新导出。
6. `docker images | grep ms-rewards` —— 镜像是否还在。

---

## 安全

以下内容**永不入库**（`.gitignore` 已隔离）：`storage_state.json`、`config.json`、`edge_profile/`、`data/`、`authorized_keys_seed.txt`、运行日志、页面截图（`*.png` / `*.jpg`）、本地回滚副本（`*.pre<日期>`）。

真实配置与登录态只保存在本机或 NAS 私有目录。仓库内的邮箱、内网地址一律使用占位符。

---

## 文档索引

- `CONTEXT.md` —— 项目统一语言（术语单一真相源）
- `docs/run-health-watchdog.md` —— 每日运行看门狗说明
- `docs/NAS_DEPLOY.md` —— NAS 部署细节
- `docs/adr/` —— 架构决策记录
- `CLAUDE.md` —— 本仓库对 AI 助手的施工纪律