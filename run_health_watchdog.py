#!/usr/bin/env python3
"""微软积分「每日运行」看门狗：每日 21:00 判定当天有没有成功签到，没成功就立即告警。

背景（2026-11-16 起发信改为「仅失败才发」后的盲区）：
  失败邮件的前提是「程序跑起来了但失败」。若进程根本没启动——cron 条目被剥离、
  容器起不来、登录态在 import 阶段就崩——既没有失败输出，也没有任何邮件，
  故障完全静默（2026-08-19 crontab 丢失就是这样静默了 5 天）。

判定规则（2026-11-16 用户口径，两个签到项目统一）：
  签到触发窗 = 08:00–20:00；每日 21:00 判定一次：
    - 当天有 ok=True 的心跳        -> 静默（不产生邮件）
    - 当天没有成功心跳 / 心跳缺失   -> 立即发一封告警邮件（同一天后续 tick 会去重）
  21:00 之前本脚本不判定（窗还没走完，早判必然误报），由调用方与脚本内部双重把关。

心跳来源：rewards_earn.py 每次运行收尾写 data/run_heartbeat.json：
  {"ts","date","ok","failed","unfinished","error","points_*","last_ok_date"}

调度：nas_cron.sh 每 15 分钟 tick，21:00 后调用本脚本（脚本内部再自闸门一次，
      一天只处理一次）；img.ink 的 watchdog.py 另有跨项目兜底调用（覆盖「微软 cron
      条目被单独删掉」）。判定时刻可用 REWARDS_HEALTH_CHECK_HOUR 覆盖，默认 21。
"""

import datetime
import json
import os
import sys
import time

BASE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(BASE, "data")
HEARTBEAT = os.path.join(DATA, "run_heartbeat.json")
CHECKED = os.path.join(DATA, "run_health_checked.json")
SCHEDULE = os.path.join(DATA, "schedule.txt")
AUTH_BLOCK = os.path.join(DATA, "auth_required.json")
RUN_LOCK = os.path.join(DATA, ".run.lock")
NAS_LOG = os.path.join(BASE, "nas.log")
DISABLED = os.path.join(BASE, "disabled.flag")
CONFIG = os.path.join(BASE, "config.json")

CHECK_HOUR = int(os.environ.get("REWARDS_HEALTH_CHECK_HOUR", "21"))
# 判定时若容器仍在跑（持锁），最多再等这么久；超过即视为陈旧锁，按未成功处理。
LOCK_FRESH_SECONDS = int(os.environ.get("REWARDS_HEALTH_LOCK_WAIT_SECONDS", "2700"))


def _load_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else default
    except Exception:
        return default


def _tail(path, n=15):
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()
        return "".join(lines[-n:]).strip()
    except Exception as e:
        return "（读取失败：%s）" % e


def _run_in_progress():
    """21:00 判定时容器可能还在跑（20:00 槽位 + 最多 30 分钟随机延迟 + 运行耗时）。

    此时当天还没写心跳，但不是失败，只是没跑完——直接告警会误报。
    返回 True 表示「有新鲜锁，判定推迟到下一个 tick」。
    """
    try:
        if not os.path.isdir(RUN_LOCK):
            return False
        age = time.time() - os.path.getmtime(RUN_LOCK)
        return 0 <= age < LOCK_FRESH_SECONDS
    except Exception:
        return False


def _load_mail_config():
    cfg = {}
    try:
        with open(CONFIG, encoding="utf-8") as f:
            cfg = json.load(f).get("email_notify") or {}
    except Exception:
        cfg = {}
    return {
        "enabled": str(
            os.environ.get("REWARDS_MAIL_ENABLED", cfg.get("enabled", False))
        ).lower()
        in ("1", "true", "yes"),
        "smtp_server": os.environ.get(
            "REWARDS_MAIL_SERVER", cfg.get("smtp_server", "")
        ),
        "smtp_port": int(
            os.environ.get("REWARDS_MAIL_PORT", cfg.get("smtp_port", 465))
        ),
        "sender": os.environ.get("REWARDS_MAIL_SENDER", cfg.get("sender", "")),
        "auth_code": os.environ.get("REWARDS_MAIL_AUTH", cfg.get("auth_code", "")),
        "recipient": os.environ.get("REWARDS_MAIL_RECIPIENT", cfg.get("recipient", "")),
    }


def _send(subject, body):
    """发告警邮件；返回 True 才允许标记「今日已判定」，否则留待下次 tick 重试。"""
    m = _load_mail_config()
    if not m["enabled"] or not (m["sender"] and m["recipient"] and m["auth_code"]):
        print("[health] 邮件未配置，仅打印：%s" % subject)
        print(body)
        return False
    try:
        import smtplib
        import ssl
        from email.mime.text import MIMEText
        from email.header import Header

        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = Header(subject, "utf-8")
        msg["From"] = m["sender"]
        msg["To"] = m["recipient"]
        if m["smtp_port"] == 465:
            with smtplib.SMTP_SSL(m["smtp_server"], m["smtp_port"], timeout=20) as s:
                s.login(m["sender"], m["auth_code"])
                s.sendmail(m["sender"], [m["recipient"]], msg.as_string())
        else:
            with smtplib.SMTP(m["smtp_server"], m["smtp_port"], timeout=20) as s:
                s.starttls(context=ssl.create_default_context())
                s.login(m["sender"], m["auth_code"])
                s.sendmail(m["sender"], [m["recipient"]], msg.as_string())
        print("[health] 已发送告警邮件至 %s" % m["recipient"])
        return True
    except Exception as e:
        print("[health] 邮件发送失败（下次 tick 重试）: %s" % e)
        return False


def _mark_checked(today_iso, alerted):
    try:
        os.makedirs(DATA, exist_ok=True)
        with open(CHECKED, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "date": today_iso,
                    "alerted": bool(alerted),
                    "checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
            f.write("\n")
    except Exception as e:
        print("[health] 写入检查状态失败: %s" % e)


def main():
    today = datetime.date.today()
    today_iso = today.isoformat()
    hour = int(time.strftime("%H"))

    if hour < CHECK_HOUR:
        print(
            "[health] 未到判定时刻（%02d:00 后才判定，当前 %02d 点），跳过。"
            % (CHECK_HOUR, hour)
        )
        return 0

    if os.path.exists(DISABLED):
        print("[health] 微软积分任务已暂停（disabled.flag），本轮不判定。")
        return 0

    checked = _load_json(CHECKED, {})
    if checked.get("date") == today_iso:
        print("[health] 今日已判定过（%s），跳过。" % today_iso)
        return 0

    hb = _load_json(HEARTBEAT, {})
    ok_today = (
        bool(hb) and str(hb.get("date") or "") == today_iso and hb.get("ok") is True
    )

    if ok_today:
        print(
            "[health] OK：今日（%s）已有成功运行记录（ts=%s 积分 %s->%s）。"
            % (today_iso, hb.get("ts"), hb.get("points_before"), hb.get("points_after"))
        )
        _mark_checked(today_iso, False)
        return 0

    # 当天没有成功记录，但可能只是「还在跑」——推迟到下一个 tick，不误报。
    if _run_in_progress():
        print(
            "[health] 当天暂无成功记录，但检测到运行锁（.run.lock 新鲜），判定推迟到下一 tick。"
        )
        return 0

    # ---- 组装告警 ----
    subject = "【微软积分看门狗】%s 21:00 仍未成功签到" % today_iso
    if not hb:
        reason = "运行心跳文件不存在（data/run_heartbeat.json）：主流程从未跑完过一次"
    elif str(hb.get("date") or "") != today_iso:
        reason = "今天（%s）没有任何运行记录：心跳还停留在 %s（最近成功 %s）" % (
            today_iso,
            hb.get("date") or "未知",
            hb.get("last_ok_date") or "无",
        )
    else:
        reason = "今天（%s）跑过但没成功：ok=%s failed=%s unfinished=%s" % (
            today_iso,
            hb.get("ok"),
            hb.get("failed"),
            hb.get("unfinished"),
        )

    lines = [
        "微软积分自动签到判定为「今日未成功」，请人工排查。",
        "",
        "[判定依据] %s（每日 %02d:00 判定，签到窗 08:00–20:00）" % (reason, CHECK_HOUR),
        "",
        "[今日调度计划] data/schedule.txt",
    ]
    try:
        with open(SCHEDULE, encoding="utf-8") as f:
            lines.append("  " + f.read().strip().replace("\n", " | "))
    except Exception as e:
        lines.append("  读取失败：%s" % e)

    lines += ["", "[最近一次运行心跳]"]
    if hb:
        for k in (
            "ts",
            "date",
            "ok",
            "failed",
            "unfinished",
            "last_ok_date",
            "points_before",
            "points_after",
            "error",
        ):
            if k in hb:
                lines.append("  %-14s = %s" % (k, hb.get(k)))
    else:
        lines.append("  （无）")

    if os.path.exists(AUTH_BLOCK):
        lines += [
            "",
            "[认证熔断] data/auth_required.json 存在 —— 需人工重新登录/确认条款",
            "  " + json.dumps(_load_json(AUTH_BLOCK, {}), ensure_ascii=False),
        ]
    else:
        lines += ["", "[认证熔断] 无 auth_required.json 标记"]

    lines += [
        "",
        "[nas.log 末尾 15 行]",
        "  " + _tail(NAS_LOG).replace("\n", "\n  "),
        "",
        "[建议排查顺序]",
        "  1) crontab 是否还在：grep nas_cron.sh /etc/config/crontab（及 /tmp/cron/crontabs/admin）",
        "  2) 容器/镜像是否正常：/share/CACHEDEV1_DATA/.qpkg/container-station/bin/docker images | grep ms-rewards",
        "  3) 手动跑一次看真实原因：/bin/sh %s/nas_cron.sh --now" % BASE,
        "  4) 登录态是否失效：data/auth_required.json、data/storage_state.json 的 mtime",
        "  5) 修好并当天成功运行后，本看门狗自动恢复静默（次日不再发信）",
    ]

    ok = _send(subject, "\n".join(lines))
    if ok:
        _mark_checked(today_iso, True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
