# NAS 部署与验证

本项目生产目录是：

```text
/share/CACHEDEV1_DATA/Web/gadget/microsoft
```

Windows 的 `Z:` 盘不是稳定前提。当前会话没有映射盘时，把 `Z:\...` 传给部署脚本可能无法定位真实目标。优先使用真实 Unix 路径。

## 推送登录态

```powershell
& 'F:\AI\skills\my-skills\nas-deploy\scripts\nas_push.ps1' `
  -Path 'F:\AI\projects\auto-sign\microsoft\storage_state.json' `
  -RemoteDir '/share/CACHEDEV1_DATA/Web/gadget/microsoft/data'
```

## 推送生产脚本

```powershell
& 'F:\AI\skills\my-skills\nas-deploy\scripts\nas_push.ps1' `
  -Path 'F:\AI\projects\auto-sign\microsoft\rewards_earn.py',
        'F:\AI\projects\auto-sign\microsoft\nas_cron.sh' `
  -RemoteDir '/share/CACHEDEV1_DATA/Web/gadget/microsoft'
```

## 必须做的远端核对

```powershell
& 'F:\AI\skills\my-skills\nas-deploy\scripts\nas_ssh.ps1' `
  -Cmd "sha256sum /share/CACHEDEV1_DATA/Web/gadget/microsoft/data/storage_state.json; wc -c /share/CACHEDEV1_DATA/Web/gadget/microsoft/data/storage_state.json; tr -cd '\r' < /share/CACHEDEV1_DATA/Web/gadget/microsoft/data/storage_state.json | wc -c"
```

本地与远端 SHA-256、字节数必须一致，CR 计数必须为 `0`。推送工具显示 PASS 不能替代这一步。
