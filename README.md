# Nuclei Poc 全网收集
NucleiPocGather，每日更新

这个项目是一个 Python 脚本，用于批量克隆 GitHub 项目，获取 Nuclei POC，并将 POC 按类别分类存放到文件夹中。同时，使用 GitHub Action 每日自动运行脚本。
<!-- BEGIN_POC_STATS -->

## 📊 POC 详情统计

| 指标 | 数值 |
|:-----|:----:|
| **更新时间** | `2026-07-14 16:43` |
| **POC 总数** | 151,780 |
| **分类数量** | 85 |

### 🏷️ 标签 Top 10

| 排名 | 标签 | 数量 |
|:---:|:-----|:----:|
| 1 | `cve` | 100,457 |
| 2 | `wordpress` | 94,128 |
| 3 | `wp-plugin` | 86,169 |
| 4 | `candidate` | 33,459 |
| 5 | `low` | 33,027 |
| 6 | `medium` | 32,683 |
| 7 | `tech` | 18,223 |
| 8 | `detect` | 17,369 |
| 9 | `high` | 16,248 |
| 10 | `service` | 13,835 |

### 📂 分类 Top 10

| 排名 | 分类 | 数量 |
|:---:|:-----|:----:|
| 1 | `other` | 56,118 |
| 2 | `cve` | 53,722 |
| 3 | `sql` | 10,273 |
| 4 | `wordpress` | 7,241 |
| 5 | `auth` | 4,319 |
| 6 | `detect` | 1,854 |
| 7 | `remote_code_execution` | 1,592 |
| 8 | `microsoft` | 1,402 |
| 9 | `web` | 1,356 |
| 10 | `api` | 1,097 |

### ⚠️ 严重性分布

| 严重性 | 数量 |
|:------|:----:|
| Critical | 15,855 |
| High | 27,232 |
| Medium | 41,576 |
| Low | 35,240 |
| Info | 27,342 |
| Unknown | 133 |
| Hight | 15 |
| Ciritical | 1 |
| Informative | 19 |
| Highx | 1 |
| Cretical | 4 |
| Meduim | 18 |
| Criticall | 1 |
| __cve_severity__ | 1 |
| Severe | 1 |
| None | 1 |

<!-- END_POC_STATS -->

## 如何使用

### 克隆项目

克隆这个项目到本地：

```bash
git clone https://github.com/lianqingsec/NucleiPocGather.git
```

进入项目目录：

```bash
cd NucleiPocGather
```

### 配置

在 `repo.txt` 文件中配置监控 GitHub 项目信息。

### 运行脚本

运行 Python 脚本：

```bash
python NucleiPocGather.py
```

### GitHub Action

在 GitHub 仓库中设置 Action，以便每日自动运行脚本。

> 需要配置`Workflow permissions`为`Read and write`权限

## 文件结构

- `NucleiPocGather.py`: 收集全网 Nuclei POC 的脚本文件。
- `DeWeight.py`: 对现有的 Nuclei POC 进行进一步去重的脚本文件。
- `WirteREADME.py`: 统计 POC 并更新 README.md 文件。
- `repo.txt`: Nuclei POC 仓库列表。
- `poc.txt`: 已存档 POC 列表。
- `poc/`: 存放分类后的 Nuclei POC 文件夹。
