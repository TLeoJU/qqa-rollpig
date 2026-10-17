# Windows 原生部署（手动）

> 文档性质：**部署说明**（面向安装者）。
>
> 状态：**未实测**。本仓库的一键脚本只支持 Linux + systemd；Windows 需要手动装 Python 侧车。
> 插件已经去掉 `/app/data` 写死，媒体前缀和帮助图路径可配置；但 Windows 上
> 的 QQA/Snowluma 组合方式较多，请先按本文确认“媒体目录能被 QQA 进程读到”。

## 0. 先确认部署形态

Windows 上常见三种情况：

| 情况 | 能否用本地图片 | 做法 |
| --- | --- | --- |
| QQA 和 Snowluma 都原生跑在 Windows | ✅ | 本文的 native 模式 |
| QQA 原生 Windows，Snowluma 在 WSL/Docker | ⚠️ | Windows 路径对 WSL/容器不可见；需要把媒体目录挂进 WSL/容器，或改用 Docker 部署 |
| QQA 在 Docker Desktop 的 Linux 容器 | ✅ | 按 Linux/Docker 文档，媒体目录挂载为 `/media` |

本文只覆盖第一种。若 Snowluma 在 WSL/容器里，优先用 Docker 方案，不要硬套本文。

## 1. 安装 Python

安装 Python **3.10 或更高版本**（python.org 安装包即可），勾选 “Add python.exe to PATH”。

```powershell
py -3.10 --version
```

## 2. 准备目录

假设：

- QQA 根目录：`C:\qq-agent`
- 侧车目录：`C:\qq-agent-rollpig`
- 媒体目录：`C:\qq-agent\media`

按实际安装路径替换。QQA 原生版不一定是 `C:\qq-agent`，以你机器上的实际目录为准。

```powershell
New-Item -ItemType Directory -Force C:\qq-agent-rollpig
cd C:\qq-agent-rollpig
git clone https://github.com/TLeoJU/qqa-rollpig.git repo
```

## 3. 创建 venv 并安装依赖

```powershell
cd C:\qq-agent-rollpig
py -3.10 -m venv venv
.\venv\Scripts\python -m pip install --upgrade pip
.\venv\Scripts\pip install -r .\repo\sidecar\requirements.txt
```

如果下载慢，可加国内镜像：

```powershell
.\venv\Scripts\pip install -i https://mirrors.aliyun.com/pypi/simple/ `
  --trusted-host mirrors.aliyun.com -r .\repo\sidecar\requirements.txt
```

## 4. 配置侧车

复制配置模板：

```powershell
Copy-Item .\repo\sidecar\rollpig_config.example.json .\repo\sidecar\rollpig_config.json
```

设置环境变量（当前 PowerShell 窗口）：

```powershell
$env:QQA_HOME = "C:\qq-agent"
$env:QQA_MEDIA_DIR = "C:\qq-agent\media"
# 关键：原生模式必须用绝对路径，不能是 /media
$env:QQA_MEDIA_URL_PREFIX = "C:\qq-agent\media"
$env:QQA_DEPLOY_MODE = "native"
$env:ROLLPIG_CONFIG_FILE = "C:\qq-agent-rollpig\repo\sidecar\rollpig_config.json"
$env:ROLLPIG_PORT = "18765"
$env:TZ = "Asia/Shanghai"
```

先生成帮助图：

```powershell
cd C:\qq-agent-rollpig\repo
.\..\venv\Scripts\python .\sidecar\make_help_image.py
```

如果生成失败，直接把 `plugin\assets\rollpig-help.png` 复制到
`C:\qq-agent\media\rollpig\help\rollpig-help.png`。

## 5. 启动侧车

前台试跑：

```powershell
cd C:\qq-agent-rollpig\repo
.\..\venv\Scripts\python .\sidecar\server.py
```

另开一个 PowerShell 验证：

```powershell
curl.exe -s http://127.0.0.1:18765/health
```

期望返回 `{"ok": true, ...}`。

## 6. 让侧车常驻

简单做法是用“任务计划程序”，登录时启动：

```powershell
schtasks /Create /TN "RollPig Sidecar" /SC ONLOGON /RL HIGHEST /F `
  /TR "cmd /c cd /d C:\qq-agent-rollpig\repo && C:\qq-agent-rollpig\venv\Scripts\python.exe sidecar\server.py"
```

然后手动启动一次：

```powershell
schtasks /Run /TN "RollPig Sidecar"
```

注意：任务计划程序不会自动带上第 4 步的临时环境变量。更稳妥的做法是写一个
`start-rollpig.cmd`，在文件里 `set` 好 `QQA_HOME`、`QQA_MEDIA_DIR`、
`QQA_MEDIA_URL_PREFIX`、`ROLLPIG_CONFIG_FILE`，再让任务计划程序运行这个 `.cmd`。

示例 `start-rollpig.cmd`：

```bat
@echo off
set QQA_HOME=C:\qq-agent
set QQA_MEDIA_DIR=C:\qq-agent\media
set QQA_MEDIA_URL_PREFIX=C:\qq-agent\media
set QQA_DEPLOY_MODE=native
set ROLLPIG_CONFIG_FILE=C:\qq-agent-rollpig\repo\sidecar\rollpig_config.json
set ROLLPIG_PORT=18765
cd /d C:\qq-agent-rollpig\repo
C:\qq-agent-rollpig\venv\Scripts\python.exe sidecar\server.py
```

## 7. 安装 QQA 插件

```powershell
$qqa = "C:\qq-agent"
New-Item -ItemType Directory -Force "$qqa\app\plugins\rollpig\assets" | Out-Null
Copy-Item .\plugin\plugin.json "$qqa\app\plugins\rollpig\plugin.json" -Force
Copy-Item .\plugin\index.js "$qqa\app\plugins\rollpig\index.js" -Force
Copy-Item .\plugin\assets\rollpig-help.png "$qqa\app\plugins\rollpig\assets\rollpig-help.png" -Force
```

QQA 开着热重载时会自动加载；没有热重载就重启 QQA。

然后在 QQA「插件 → 今日小猪（RollPig）」里把 **小猪帮助图路径** 改成
`C:/qq-agent/media/rollpig/help/rollpig-help.png`（按实际路径替换）。不改也能用，
只是 `小猪帮助` 会走插件内置图兜底，而不是安装脚本生成的那张。

## 8. 验证

1. QQA 控制台「插件」页应出现「今日小猪（RollPig）」，状态为已加载/已启用。
2. 群里发 `小猪帮助`：应收到帮助图（优先 `/media` 图，失败用插件内置图）。
3. 群里发 `今日小猪`：应收到卡片，且没有 AI 文字回复。
4. 若卡片裂图，检查：
   - `QQA_MEDIA_URL_PREFIX` 是否真的是 QQA 进程能读到的绝对路径；
   - 侧车日志里生成的图片路径；
   - Snowluma 是否和 QQA 在同一台 Windows 机器上。

## 9. 卸载

1. 停止并删除计划任务：
   ```powershell
   schtasks /End /TN "RollPig Sidecar"
   schtasks /Delete /TN "RollPig Sidecar" /F
   ```
2. 删除 `C:\qq-agent\app\plugins\rollpig`（或移到备份目录）。
3. 需要彻底清理时再删 `C:\qq-agent-rollpig` 和 `C:\qq-agent\media\rollpig`。
4. 上游数据默认在 `%USERPROFILE%\.local\share\nonebot2\nonebot_plugin_rollpig_plus`，按需保留或删除。
