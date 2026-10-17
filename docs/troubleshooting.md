# 故障排查

> 文档性质：**运维说明**（面向安装者/管理员），按现象查原因。

## 先做这三件事

```bash
# 1. 侧车是否活着
curl -s http://127.0.0.1:18765/health

# 2. 服务状态与最近日志
systemctl status rollpig-sidecar --no-pager
journalctl -u rollpig-sidecar -n 120 --no-pager

# 3. QQA 插件日志
docker logs --tail 120 qq-agent 2>&1 | grep -iE 'rollpig|plugin|skill'
```

正常 `health` 类似：

```json
{"ok":true,"self_id":"123456789","groups":3,"outbox":0,...}
```

## 插件页显示加载失败

QQA 的「插件」页会给出原文。常见原因：

| 页面错误关键词 | 原因 | 处理 |
| --- | --- | --- |
| `Unexpected token` / `JSON` | `plugin.json` 语法错 | `python3 -m json.tool plugin/plugin.json` |
| `BOM` / `invalid` | 文件带 UTF-8 BOM | 用无 BOM 保存 |
| `id` / `invalid id` | id 含非法字符或为空 | 只用 `[a-zA-Z0-9._-]`，且以字母数字开头 |
| `entry` / `not found` | `entry` 指向的文件不存在 | 确认 `index.js` 与 `plugin.json` 同目录 |
| `Cannot find module` | 相对 import 路径错 | 本项目用 `../../src/orchestrator.js`，必须放在 `plugins/rollpig/` |
| 加载成功但 `active=false` | `activate()` 抛错 | 看 QQA 日志里的 stack |

改完 `plugin.json`/`index.js` 后，QQA 热重载通常 500ms 内生效；不生效再
`touch plugins/rollpig/index.js`。

## 指令没反应 / 变成普通聊天

按顺序排查：

1. **侧车没起**：`systemctl is-active rollpig-sidecar` 不是 `active`。
2. **端口不通**：`curl -s http://127.0.0.1:18765/health` 失败。
3. **插件没命中**：在 QQA 日志搜 `[RollPig]`。命中时应有类似
   `[RollPig] 命中 ...` 或 `[发送 -> group:...] [RollPig]`。
4. **消息被别的插件先吞了**：本项目在 `onIncoming` 最外层包装，理论上先于其他插件；
   如果仍有插件在更外层包装，需要调整加载顺序。
5. **文本带前缀**：`@机器人 今日小猪` 会先去掉 `@名字`；`/今日小猪` 也能命中。
   但 `今日小猪呀`、`小猪帮助一下` 不会命中（保守匹配）。

## `fetch failed` / `sidecar unavailable`

插件在侧车不可用时会回退到普通聊天，避免吞消息。处理：

```bash
sudo systemctl restart rollpig-sidecar
curl -s http://127.0.0.1:18765/health
```

插件下一条消息会重新同步 `self_id`/群列表；不需要重启 QQA。

## 卡片裂图 / 图片 404

先确认部署形态和发送前缀：

```bash
# 侧车写到哪里、返回什么前缀
grep -E 'QQA_MEDIA_DIR|QQA_MEDIA_URL_PREFIX|QQA_DEPLOY_MODE' \
  /etc/systemd/system/rollpig-sidecar.service
```

Docker 双容器：`QQA_MEDIA_URL_PREFIX` 必须是 `/media`，并检查挂载：

```bash
docker inspect qq-agent --format '{{range .Mounts}}{{println .Source "->" .Destination}}{{end}}' | grep media
```

原生安装：`QQA_MEDIA_URL_PREFIX` 必须是**绝对路径**（如 `/opt/qq-agent/media`，
Windows 如 `C:/qq-agent/media`），不能是 `/media`。如果 QQA 用别的 `QQA_HOME`：

```bash
sudo QQA_HOME=/your/qq-agent ./scripts/install.sh
# 或强制原生：
sudo QQA_DEPLOY_MODE=native ./scripts/install.sh
```

## 帮助图不显示

```bash
QQA_HOME="${QQA_HOME:-/opt/qq-agent}"
ls -l "$QQA_HOME/media/rollpig/help/rollpig-help.png"
# Docker 形态再看容器内：
docker exec qq-agent ls -l /media/rollpig/help/rollpig-help.png
```

文件不在就重跑：

```bash
QQA_HOME="${QQA_HOME:-/opt/qq-agent}"
sudo "$QQA_HOME/rollpig-service/venv/bin/python" \
  "$QQA_HOME/rollpig-service/make_help_image.py"
```

原生/Windows 还要确认 QQA 插件设置里的 `helpImage` 是 QQA 能读到的绝对路径，
不是 `/media/...`。

仍失败时，`小猪帮助` 会回退为文字版指令列表。

## 日报不推

- 日报只在 **23:45–00:10** 窗口出刊；
- 侧车需要知道群列表：让机器人在目标群先收到一条消息，或重启后等插件同步；
- 群设置需开启：`小猪日报 开启`（群主/管理员）；
- 检查 `rollpig_config.json` 的 `rollpig_daily_summary_enabled` 是否为 `true`。

## 侧车启动失败

```bash
journalctl -u rollpig-sidecar -n 200 --no-pager
```

常见：

| 日志 | 原因 | 处理 |
| --- | --- | --- |
| `No module named 'nonebot'` | venv 未装依赖 | `sudo ./scripts/install.sh` |
| `No module named 'fastapi'` / `uvicorn` | 依赖不全 | 重跑安装脚本 |
| `Address already in use` | 18765 被占用 | `ss -tulnp | grep 18765`，改 `ROLLPIG_PORT` |
| `Permission denied` | 媒体目录不可写 | 确认服务以 root 运行，或修目录权限 |
| `resource sync failed` | 外网/PyPI/资源站不通 | 可忽略，用内置资源；查网络 |

## 升级

```bash
cd qqa-rollpig
git pull
sudo ./scripts/install.sh
```

安装脚本会保留 `rollpig_config.json`，旧插件移到
`/opt/qq-agent/app/data/rollpig-backups/`，不会留在 `plugins/` 下被误扫描。

## 卸载

```bash
sudo ./scripts/uninstall.sh          # 保留侧车目录与数据
sudo ./scripts/uninstall.sh --purge  # 删侧车目录与帮助图，仍保留用户数据
```

用户数据默认在 `/root/.local/share/nonebot2/nonebot_plugin_rollpig_plus/`。

## 收集反馈信息

```bash
{
  echo '--- health ---'; curl -s http://127.0.0.1:18765/health
  echo; echo '--- service ---'; systemctl status rollpig-sidecar --no-pager
  echo '--- journal ---'; journalctl -u rollpig-sidecar -n 100 --no-pager
  echo '--- plugin ---'; ls -l /opt/qq-agent/app/plugins/rollpig
} > /tmp/rollpig-report.txt
```

把 `/tmp/rollpig-report.txt` 与 QQA 插件页错误原文一起提交 issue。
