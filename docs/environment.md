# 环境检查（2026-10-14，Asia/Taipei）

WSL 2 Debian13、用户 dev；Debian GNU/Linux 13.7 (trixie)，内核 6.18.54.1-microsoft-standard-WSL2 x86_64。

初检 tmux / Python 3 未安装；apt-get install tmux python3 后复检：

| 工具 | 路径 | 实际结果 |
|---|---|---|
| tmux | /usr/bin/tmux | tmux -V → tmux 3.5a（包 3.5a-3） |
| Python | /usr/bin/python3 | python3 --version → Python 3.13.5 |
| Bash | /usr/bin/bash | GNU bash 5.2.37 |
| Codex | /home/dev/.local/bin/codex | 登录 Bash --version → codex-cli 0.162.1 |
| OpenCode | /home/dev/.opencode/bin/opencode | 登录 Bash --version → opencode v2.0.28 |
| Antigravity | 未找到 | 登录 Bash command -v antigravity 无结果 |

直接 wsl --exec 的 PATH 未含 ~/.local/bin / ~/.opencode/bin，不能因此说 CLI 未安装。启动用实际解析的绝对路径及环境；这里只检查版本，不是 TUI 验收。

仓库初始无提交/无 Git author 配置。自动化提交命令级 author 为 Codex <codex@localhost>，不改全局身份。
