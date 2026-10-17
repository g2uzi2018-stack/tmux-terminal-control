# agy 在 WSL 中的 Gemini 地区错误：已修复

日期：2026-10-17，Asia/Taipei。已修复本机 Linux 原生 agy CLI 1.4.0 的 Gemini 3.8 Flash High 调用。显式代理、仅 proxy_on 的透明代理，以及不传 --model 的原默认模型均已成功响应；真实技能工作包也已验收。配置在本机代理生成器中持久生效，不依赖临时转发进程。

## 原因与修复

本机路径为 WSL → sing-box 1.14.3 → Windows FlClash 127.0.0.1:7890。原配置把 mixed 入口的代理域名提前解析为 IPv4；透明流量也直接按 IP 转发。这使请求的域名解析/上游路由路径与 Windows 按域名访问不同。公共出口检测相同，并不足以证明具体 API 的请求路径相同。

对照中，Windows 官方 CLI、Linux CLI 经保留域名的转发路径均成功；同一 Linux CLI 切回原 mixed 入口即再次报错。去掉提前解析后，原端口立即成功。由此确认可修复的本地配置差异；未测量 Windows 内部最终选择的节点或 Google 地区判定，不把更深的具体机制当作已证实事实。

修改 `/usr/local/lib/wsl-proxy/wsl_proxy_common.py` 的 `make_config()`：

1. 删除 mixed-in / Global 的 `action: resolve, strategy: ipv4_only` 规则，保留 HTTP CONNECT/SOCKS 请求的原域名交给 Windows 上游。
2. Global 模式下对 TUN 的 TCP 443 读取 TLS 握手中的公开域名；仅匹配 `daily-cloudcode-pa.googleapis.com` 时，把目的地址恢复成这个同名域名，经原 windows-proxy 转发。TLS 保持端到端加密，没有解密、证书替换或认证信息记录。

[源文件补丁](patches/wsl-proxy-preserve-domains.patch) 只含上述配置生成代码，不含 API 密钥。sing-box check 通过后，使用现有 wsl-proxy stop/on 重载监督进程，使其导入新生成器。运行时配置与生成器都已更新，再次 proxy_on 不会写回旧规则；最终状态为 on / Global、服务运行、Windows 上游可达。没有改动代理开关的 off / Direct 分支。

此次没有更换账号、Gemini 模型、默认后端或 Windows 节点，没有重新登录或跨系统复制凭据。没有采用 Claude 替代 Gemini，也没有持久设置 CLOUD_CODE_URL。

## 关键对照

所有模型测试均使用已有登录；每次真实 CLI 启动前先 proxy_on。仅请求一个固定测试答案，不调用工具或修改项目文件。Windows CLI 来自官方更新 manifest，版本 1.4.0，执行前验证 SHA-512；下载到用户临时目录，没有安装到 Windows PATH。

| 配置 | 实测结果 | 耗时 |
|---|---|---|
| 修复前 Linux / 原 17890 / Gemini High | ERROR，地区错误 400 | 9.60 秒 |
| 相同 Linux / 账号 / 代理 / Claude Sonnet 4.6 | SUCCESS | 8.69 秒 |
| Linux / Gemini / 临时生产后端 | ERROR，配额错误 429，未持久化 | 8.54 秒 |
| Windows 原生 CLI / 7890 / Gemini High | SUCCESS，AGY_WINDOWS_GEMINI_OK | 13.82 秒 |
| Linux 原生 CLI / 到 Windows 的纯 TCP 转发 / Gemini High | SUCCESS，AGY_NATIVE_GEMINI_OK | 11.32 秒 |
| Linux 再切回未修复的原 17890 | ERROR，地区错误 400 | 9.65 秒 |
| Linux / 保留域名的临时 sing-box / Gemini High | SUCCESS | 13.05 秒 |
| 删除提前解析规则，重载后使用原 17890 | SUCCESS | 11.60 秒 |
| 仅完成 mixed 修复，清除代理变量只走 TUN | ERROR，地区错误 400 | 9.79 秒 |
| 补齐透明流量域名转发，清除代理变量 | SUCCESS | 12.08 秒 |
| 最终配置，再 proxy_on，不传代理变量和 --model | SUCCESS；执行元数据确认为 gemini-3.8-flash-high | 13.21 秒 |

Windows 桌面版 2.24.0 的本地登录名称与 Linux CLI 一致；只检查配置和模型执行元数据，未读取用户对话正文。桌面会话模型为 gemini-3.8-flash-high，与用户确认一致。两边 loadCodeAssist / fetchAvailableModels 均使用 daily-cloudcode-pa.googleapis.com。Windows 和 WSL 的公共出口检测 IP 相同，地区为 US；未在仓库保存公网 IP。

早期 [#1016](https://github.com/google-antigravity/antigravity-cli/issues/1016)、[#875](https://github.com/google-antigravity/antigravity-cli/issues/875) 提供相似症状，但都是报告，不能代替本机因果对照。此次修复依据本机真实请求结果。sing-box 官方说明 [resolve 会把目的域名解析成 IP](https://sing-box.sagernet.org/configuration/route/rule_action/#resolve)，并说明 [sniff 与目的地址覆盖](https://sing-box.sagernet.org/configuration/route/rule_action/) 的配置语义。

可供检查的结构化摘要见 [agy-wsl-test-results.json](agy-wsl-test-results.json)。原始诊断日志位于私有临时目录 `/tmp/agy-network-diagnosis-20261017/`，不复制认证日志到仓库；临时目录可能被系统清理。

## 技能任务验收

工作包 `task-6589ff584d1c4fce82afb04d66f5dbe1`，模型显式绑定 `gemini-3.8-flash-high`，通过已安装的 peer-coworkers 启动独立 tmux server，启动前 proxy_on，指定 --proxy-url http://127.0.0.1:17890。

主代理读屏确认 Gemini 3.8 Flash High，核对实际 pane 的六个代理变量，确认短指令完整接收后只提交一次。工作进程读取 prompt.txt、写入 result.json 并结束生成；结果包含 AGY_GEMINI_WORKER_OK 与 23×29=667。collect 校验本任务/本轮标识及六字段合同通过，changed_paths、scope_violations 为空，git_state_changed=false。主代理另行检查结果并验算后 accept，再 close 和 prune 该精确 socket。

较早的 Claude 工作包 `task-f1cc85bc0ccc4929b83a11784cd48f5e` 也已通过；它保留为另一模型的验收事实，不是这次 Gemini 修复的替代方案。诊断用临时 relay / sing-box 进程均已停止，没有留下常驻转发服务或本次 tmux 会话。

## 使用与恢复

日常终端：

```bash
proxy_on
agy
# 需要本次显式指定时：
agy --model gemini-3.8-flash-high
```

技能任务仍推荐显式代理，以便任务记录能够复现：

```bash
# RUN 替换成 init 返回的绝对目录。
bash -ic 'proxy_on && python3 /home/kuang/.codex/skills/peer-coworkers/scripts/cowork.py start --run RUN --proxy-url http://127.0.0.1:17890'
```

本机初始配置与源文件备份位于 `/etc/wsl-proxy/backups/agy-domain-forwarding-20261017T103153Z/`；仅 mixed 修复完成时的中间备份位于 `/etc/wsl-proxy/backups/agy-transparent-domain-20261017T103524Z/`。目录仅 root 可访问；其中 config.json 含本机 API secret，不放入仓库或对外分享。

若确需回滚，恢复所选备份的 wsl_proxy_common.py，再执行 wsl-proxy stop 和 proxy_on，让监督进程重新导入生成器。恢复初始版本会同时恢复本次已复现的调用故障。技能安装器不会自动应用系统代理补丁；它只安装技能包。
