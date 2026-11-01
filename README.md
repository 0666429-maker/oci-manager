# oci-manager

仅管理 Oracle Cloud（OCI）的开源平替项目，对齐 R-Bot（semicons/java_oci_manage）
的 OCI 相关操作，**去掉 AWS / GCP / Azure / DigitalOcean / SolusVM / VirtFusion /
Cloudflare**，只做 OCI。

## 功能对照（R-Bot OCI 部分 → 本项目）

| R-Bot 的 OCI 操作 | 本项目实现 |
|---|---|
| 实例开机 / 关机 / 重启 / 终止 | `POST /api/instances/{id}/action`，Bot `/start_vm /stop_vm /reboot_vm /terminate_vm` |
| 创建实例、快捷开机 | `POST /api/instances`，`preset=amd_micro`（E2.1.Micro）或 `arm_a1`（A1 Flex 4核24G） |
| 升降配 | `POST /api/instances/{id}/shape`（需先关机） |
| A1 配置体检 | `GET /api/a1-check`：汇总运行中 A1 的 OCPU/内存，对比 4核/24G 免费额度，只提示不自动删机 |
| 换 IP、保留 IP、IPv4/IPv6 | `POST /api/public-ips/change`（删临时 IP 再建新临时 IP）、保留 IP 创建/指派/解绑/删除 |
| 磁盘扩容、提 IO、分离/挂回、删除 | `/api/volumes` 系列；启动卷扩容 `/api/boot-volumes/{id}/resize` |
| 用户管理、API 密钥 | `/api/users`、`/api/users/{id}/api-keys`（含密钥轮换：先建新再删旧） |
| 统计概览、配额查询 | `/api/limits/services`、`/api/metrics/cpu`、`/api/alarms` |
| 对象存储 Bucket / 文件 | `/api/buckets` 系列（创建、上传、下载、删除） |
| 串行控制台 | `POST /api/instances/{id}/serial-console`（需 SSH 公钥） |
| 云主机同步到 SSH 列表 | `GET /api/hosts/sync`（取运行中实例 + 公网 IP） |
| Web SSH 智能终端 | WebSocket `/ws/ssh` + 面板“Web SSH”页（多主机、密码/私钥两种认证） |
| Telegram 机器人 | `python run.py --bot`（命令见 `app/bot.py`） |
| 停机自动拉起、CPU 告警 | `python run.py --monitor` + `monitor_rules.json`（见下） |
| 流量超额自动关停 | **刻意不做**：关停属于高危动作，本项目只告警，关停请人工确认 |

## 快速开始

```bash
cd oci-manager
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env   # 填 OCI 密钥、面板账号，务必改掉默认值
.venv/bin/python run.py
# 打开 http://你的IP:9527
```

同时启动 Bot / 监控：

```bash
.venv/bin/python run.py --bot --monitor
```

`monitor_rules.json` 示例（可选，不存在则监控不做事）：

```json
[
  {"instance_id": "ocid1.instance.oc1..xxxx", "auto_restart": true},
  {"instance_id": "ocid1.instance.oc1..xxxx", "cpu_threshold": 90}
]
```

## 配置说明

- **推荐：网页上传、多密钥管理**：面板顶部点“密钥管理”，填名字、用户
  OCID、租户 OCID、指纹、区域（可选默认 compartment），选 `.pem` 私钥
  文件上传保存。能存多条，点“切换到这条”立即生效，不用重启服务；
  每条的私钥单独存在 VPS 的 `data/keys/` 里（仅自己可读），列表里
  只显示 OCID 打码后的头尾，不能从网页下载或查看私钥原文。
- 兼容旧方式：没有激活任何一条网页密钥时，仍按 `.env` 里的
  `OCI_USER_OCID / OCI_TENANCY_OCID / OCI_FINGERPRINT /
  OCI_PRIVATE_KEY_PATH / OCI_REGION`，或标准 `~/.oci/config` 文件工作。
- `OCI_COMPARTMENT_OCID` 是默认 compartment；调用 API 时也可每次传
  `compartment_id` 覆盖。
- 创建实例前，需先在 OCI 控制台拿到：可用区（availability_domain）、
  镜像 OCID、子网 OCID。面板“创建实例”页会提示这三项必填。
- 改 Shape、删卷、终止实例、删 Bucket 等危险操作都要求 `confirm=true`
  或 Bot 端发两次命令，防止误触。

## 安全说明（请认真读）

1. **密钥只存在本机**：OCI API 私钥只在部署本程序的机器上（`.env` 或
   `~/.oci/config`），本程序不会把密钥发给任何第三方，也不要把 `.env`
   提交到 Git（`.gitignore` 已排除）。
2. **最小权限**：建议给本程序单独建一个 OCI 用户/API 密钥，只给它需要
   的 compartment 权限，不要用租户管理员密钥长期跑面板。
3. **不要裸奔上公网**：面板默认端口 9527，务必设强面板密码，最好只放
   内网 / VPN / 防火墙白名单后访问；Web SSH 等于目标主机 shell 入口，
   同样不要直接暴露。
4. **闭源原项目 vs 本项目**：原 R-Bot 仓库只提供文档和预编译包，核心
   程序不可审计；本项目是源码实现，你可以自己审每一行调用，但相应地，
   **它尚未在真实租户上做端到端实测**，上线前请先在测试 compartment
   里跑通创建/开关机/换 IP/删卷等流程。

## 托管到 GitHub（像原项目一样用 Release 一键安装）

本仓库已经按原项目的方式准备好了：根目录有 `install.sh`，
`.github/workflows/release.yml` 会在打 tag 时自动把 `oci-manager.zip`
挂到 Release 上。

1. 在 GitHub 上新建一个空仓库，名字建议就叫 `oci-manager`，不要勾选
   “Add a README”（避免和本地仓库冲突）。
2. 把本地仓库推上去（把 `<你的GitHub用户名>` 换成你自己的）：
```bash
cd oci-manager
git remote add origin https://github.com/<你的GitHub用户名>/oci-manager.git
git push -u origin main
git tag v0.1.0
git push origin v0.1.0
```
3. 等 Actions 跑完，Release 里出现 `oci-manager.zip` 后，VPS 上就只剩
   两行命令（原项目式的一键安装）：
```bash
wget -O install.sh https://raw.githubusercontent.com/<你的GitHub用户名>/oci-manager/main/install.sh
bash install.sh <你的GitHub用户名> --systemd
```
4. 之后不用再改 `.env` 也能配密钥：打开面板点“密钥管理”，网页上传
   `.pem` 并填好 OCID、指纹、区域就能用（密钥不能进 GitHub，这是
   安全底线；多条密钥也都在这里统一管理和切换）。

## Ubuntu VPS 部署（从零开始）

```bash
# 1) 把 oci-manager.zip 传到 VPS 并解压（本地电脑上执行）
scp oci-manager.zip 你的用户名@你的VPS_IP:~/
# 2) SSH 登录 VPS 后
ssh 你的用户名@你的VPS_IP
unzip oci-manager.zip && cd oci-manager
# 3) 一键装依赖（不设自启，先手动试跑）
bash scripts/install-ubuntu.sh
# 4) 填密钥（见下文“配置说明”），把 OCI 私钥放到 ~/.oci/oci_api_key.pem 并 chmod 600
nano .env
# 5) 手动试跑，另开终端 curl http://127.0.0.1:9527/api/health 能返回 {"ok":true} 再设自启
.venv/bin/python run.py
# 6) 设 systemd 开机自启（可选，--bot/--monitor 按需加）
bash scripts/install-ubuntu.sh --systemd --bot
sudo journalctl -u oci-manager -f   # 看日志
```

## 项目结构

```
run.py                  启动入口（--bot / --monitor）
app/
  config.py             .env / OCI config 翻译（优先用激活的网页密钥）
  credentials.py        网页上传的多密钥管理（data/profiles.json + data/keys/*.pem）
  oci_factory.py        OCI 各客户端懒加载（compute / network / blockstorage /
                        identity / object_storage / monitoring / limits）
  api.py                FastAPI Web 面板接口
  ssh_terminal.py       WebSocket + paramiko 交互终端
  bot.py                Telegram Bot 命令
  monitor_worker.py     停机拉起 / CPU 告警轮询
  services/
    instances.py        实例、快捷预设、A1 体检、串行控制台
    network.py          公网 IP / 保留 IP / VCN / 子网
    volumes.py          数据卷 / 启动卷
    identity.py         compartment / 可用区 / 用户 / API 密钥
    storage.py          对象存储
    monitoring.py       CPU 指标 / 告警 / 服务限额
web/                    面板前端（index.html / app.js / style.css）
```

## 已知限制（诚实说明）

- OCI 控制台密码、2FA 没有公开 SDK 调用可直接重置，本项目只实现
  SDK 支持的用户/API 密钥管理，密码/2FA 请走 OCI 控制台官方流程。
- 内存指标需要实例装 Management Agent 才会上报，无 Agent 时 CPU
  接口可能返回空数据，这是 OCI 本身的限制。
- 流量统计、账单成本需走 OCI Usage / Cost API，本版未接入，面板
  只做实例状态、CPU、配额这三类可直接拿到的监控。
