# astrbot_plugin_computer_use

通过 AstrBot 远程控制你的电脑。支持屏幕截图、鼠标点击、键盘输入等操作，通过 SSH 隧道安全连接本地电脑。

## 架构

```
┌─────────────────┐         SSH 隧道          ┌──────────────────┐
│   AstrBot 服务器  │ ──── 端口转发 (SSH) ────► │   被控电脑        │
│  (远程/云端)      │                          │  (Windows/Linux)  │
│                  │  localhost:xxxxx ───────► │  Agent (FastAPI)  │
│  本插件 (main.py) │                          │  pyautogui 执行    │
└─────────────────┘                           └──────────────────┘
```

**工作流程:**
1. 被控电脑上运行 Agent (`remote_agent.py`)，提供 HTTP API
2. AstrBot 服务器上的插件通过 SSH 端口转发连接到 Agent
3. 用户在聊天中发送指令，插件通过隧道转发给 Agent 执行
4. 执行结果（截图/文字）返回给用户

## 安装

### 1. 被控电脑上安装 Agent

```bash
# 进入 agent 目录
cd agent/

# 安装依赖
pip install -r requirements.txt

# Windows 需要额外安装 pygetwindow（pyautogui 依赖）
pip install pygetwindow

# 启动 Agent
python remote_agent.py --port 8765

# 启动 Agent（带认证 token）
python remote_agent.py --port 8765 --token your_secret_token
```

Agent 默认只监听 `127.0.0.1`（本机），通过 SSH 隧道访问，不直接暴露到网络。

### 2. 被控电脑开启 SSH 服务

**Windows:**
```powershell
# 以管理员身份运行 PowerShell
Add-WindowsCapability -Online -Name "OpenSSH.Server~~~~0.0.1.0"
Start-Service sshd
Set-Service -Name sshd -StartupType Automatic
```

**Linux:**
```bash
sudo apt install openssh-server
sudo systemctl start sshd
sudo systemctl enable sshd
```

**密钥认证（推荐）:**
```bash
# 在 AstrBot 服务器上生成密钥
ssh-keygen -t rsa -b 4096

# 将公钥复制到被控电脑
cat ~/.ssh/id_rsa.pub | ssh username@IP "mkdir -p ~/.ssh && cat >> ~/.ssh/authorized_keys"
```

### 3. 安装 AstrBot 插件

将 `astrbot_plugin_computer_use` 文件夹放入 AstrBot 的 `data/plugins/` 目录。

或在 AstrBot WebUI 的插件管理中直接安装。

### 4. 配置插件

在 AstrBot WebUI 的插件配置中填写:

| 配置项 | 说明 | 示例 |
|--------|------|------|
| ssh_host | 被控电脑 IP | 192.168.1.100 或 Tailscale IP |
| ssh_port | SSH 端口 | 22 |
| ssh_username | SSH 用户名 | administrator |
| ssh_password | SSH 密码（二选一） | your_password |
| ssh_key_path | SSH 密钥路径（二选一） | ~/.ssh/id_rsa |
| agent_port | Agent 端口 | 8765 |
| auto_connect | 自动连接 | false |
| screenshot_quality | 截图质量 (1-100) | 75 |
| command_timeout | 命令超时秒数 | 30 |
| allowed_users | 允许的用户ID（留空=所有人） | [] |

## 使用

### 连接管理

```
/cu 状态          查看连接状态
/cu 连接          连接被控电脑
/cu 断开          断开连接
```

### 屏幕操作

```
/cu 截图                   截取屏幕画面
/cu 点击 500 300           左键点击坐标 (500, 300)
/cu 双击 500 300           双击坐标
/cu 右键 500 300           右键点击坐标
/cu 移动 500 300           移动鼠标到坐标
/cu 拖拽 100 100 500 500   从 (100,100) 拖拽到 (500,500)
```

### 键盘操作

```
/cu 输入 Hello World       输入文字（支持中文）
/cu 按键 enter             按键（enter/esc/tab/space/up/down/left/right等）
/cu 组合键 ctrl c          组合键 Ctrl+C
/cu 组合键 ctrl shift esc  组合键 Ctrl+Shift+Esc
/cu 滚动 down 3            向下滚动 3 格
/cu 滚动 up 5              向上滚动 5 格
```

### 帮助

```
/cu 帮助                   显示完整帮助
/cu                        显示完整帮助
```

## 支持的按键名称

| 按键 | 名称 |
|------|------|
| 回车 | enter, 回车 |
| 退出 | esc, escape |
| 制表 | tab, 制表 |
| 空格 | space, 空格 |
| 退格 | backspace, 退格 |
| 删除 | delete, del, 删除 |
| 方向键 | up, down, left, right, 上, 下, 左, 右 |
| 功能键 | f1-f12 |
| 修饰键 | ctrl, alt, shift, win |

## 安全建议

1. **Agent 只监听 127.0.0.1** — 不要改为 0.0.0.0，通过 SSH 隧道访问更安全
2. **使用 SSH 密钥认证** — 比密码更安全，且支持自动化
3. **设置 Agent token** — 防止即使隧道建立后未授权访问
4. **配置 allowed_users** — 限制只有指定用户能使用控制命令
5. **使用 Tailscale/VPN** — 如果服务器和电脑不在同一局域网

## 文件结构

```
astrbot_plugin_computer_use/
├── main.py               # AstrBot 插件主入口
├── metadata.yaml          # 插件元数据
├── _conf_schema.json      # 配置项定义
├── requirements.txt       # 插件依赖
├── ssh_tunnel.py          # SSH 隧道管理
├── LICENSE                # MIT 许可证
├── README.md              # 本文档
└── agent/
    ├── remote_agent.py     # 本地 Agent（运行在被控电脑上）
    └── requirements.txt   # Agent 依赖
```

## 技术栈

- **AstrBot 插件端**: Python + asyncssh (SSH隧道) + aiohttp (HTTP请求)
- **本地 Agent**: FastAPI + pyautogui (UI自动化) + Pillow (图像处理)

## 跨平台支持

- **被控端**: Windows (完整支持)、Linux (需安装 python3-tk)
- **服务器端**: 任意支持 AstrBot 的平台

## 开源协议

MIT License — 自由使用、修改、分发。

## 贡献

欢迎提交 Issue 和 Pull Request！
