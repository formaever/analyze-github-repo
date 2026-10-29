# analyze-github-repo

**中文** | [English](README_EN.md)

一个只读的 Agent Skill：分析公开 GitHub 仓库或本地源码，解释主要功能、架构、执行流程与实现边界。

目标不是写一篇项目介绍，而是让结论**可追溯、可区分、可验证**：

- 区分作者声明、源码证据、运行证据和分析推断；
- 重要实现判断附文件与行号；
- 用脚本排除失效引用，再由 AI 复核语义；
- 明确标注未覆盖范围与未知内容。

> README 仅用于仓库说明。Skill 运行时只加载 `SKILL.md`，不会读取本文件。

## 能做什么

- 判断项目属于应用、库、CLI、Skill 还是资料集合；
- 沿“输入 → 处理 → 外部依赖 → 输出”追踪代表性流程；
- 核对 README 宣称的能力是否真有实现证据；
- 分析 Skill 时，区分提示词要求、辅助脚本和宿主能力；
- 输出带证据的功能说明、限制与适用场景。

## 不做什么

- 不安装依赖，不执行被分析仓库的脚本，不修改其文件；
- 不把引用位置检查通过称为事实核验或语义验证；
- 不把示例、截图或模型评分当作业务效果证明；
- 不替代真实运行测试，未运行时不报告“运行正常”。

## 目录结构

```text
analyze-github-repo/
├── SKILL.md                          # 主指令与执行流程
├── README.md                         # 中文仓库说明（本文件）
├── README_EN.md                      # 英文仓库说明
├── references/
│   └── domain-rules.md               # 能力声明分类、证据与验收规则
├── scripts/
│   └── check_evidence.py             # 只读引用位置检查器
├── examples/
│   ├── sample-repo/review_rules.py   # 供引用的合成源码
│   ├── evidence-valid.json           # 正确引用示例
│   └── evidence-invalid.json         # 缺失文件、越界、路径逃逸示例
└── tests/
    └── test_check_evidence.py        # 标准库自动化测试
```

## 安装

把整个目录复制到目标 runtime 的 skills 目录：

| 范围 | 路径 |
|---|---|
| Qoder 项目级 | `.qoder/skills/analyze-github-repo/` |
| Qoder 用户级 | `~/.qoder/skills/analyze-github-repo/` |
| Claude Code 等兼容 runtime | 对应 runtime 的 `skills/` 目录 |

安装后重启会话或重新加载 Skill，确认 `analyze-github-repo` 出现在可用列表中。

## 使用

直接提出分析需求即可触发：

```text
分析 https://github.com/owner/repo 的主要功能和实现原理。
这个项目的 README 说支持多 Agent，代码里真的有调度实现吗？
对比这两个仓库的错误处理方式，并给出源码证据。
```

需要固定输出时，也可显式调用：

```text
/analyze-github-repo 分析 E:\WorkSpace\Qoder\btsou-mvp
```

默认只读。分析远程仓库时，遵循宿主提供的仓库访问与搜索工具规则。

## 引用检查器

需要 Python 3.9+，仅使用标准库，不联网、不执行目标代码、不写入源码目录。

```bash
python scripts/check_evidence.py <本地源码根目录> <引用JSON文件> --max-errors 20
```

引用格式：

```json
{
  "claims": [
    {
      "id": "C1",
      "claim": "待复核的实现结论",
      "file": "src/app.py",
      "start_line": 10,
      "end_line": 24
    }
  ]
}
```

检查内容：

- 字段类型与 `id` 唯一性；
- 相对路径、驱动器、UNC、`..`、特殊字符和符号链接逃逸；
- 文件存在且为普通文件；
- 行号有效且不超过文件长度；
- UTF-8（可带 BOM）读取。

退出码：

| 退出码 | 含义 |
|---|---|
| 0 | 所有引用位置有效 |
| 1 | 引用位置无效（缺失文件、越界、路径逃逸等） |
| 2 | 参数、JSON、编码或读取错误 |

`ok: true` 只表示位置有效，**不代表结论真实或代码支持该结论**。

本地演示（在 Skill 目录内执行）：

```bash
python scripts/check_evidence.py examples/sample-repo examples/evidence-valid.json
python scripts/check_evidence.py examples/sample-repo examples/evidence-invalid.json
```

## 测试

```bash
python -m unittest discover -s tests -v
```

当前结果：**31 项测试，30 项通过，1 项跳过**。

跳过项是“仓库外符号链接”用例，原因是当前 Windows 环境缺少创建符号链接的特权；仓库外目录联接（junction）用例已实际通过，另有模拟解析用例覆盖同一拒绝分支。

## 设计说明

- **规则与脚本分离**：判断标准放在 `references/`，机械检查放在 `scripts/`。
- **脚本只做确定性工作**：验证路径和行号，不猜测语义，不用关键词统计冒充理解。
- **证据分级**：有实现证据、有运行证据、仅有声明、依赖外部能力、未知。
- **失败不伪装**：无法访问或无法运行时说明缺口，不用推测补全实现。

## 已知限制

- 只检查引用位置，不验证引用内容是否支持结论；
- 无法读取编码异常或网络路径中的源码；
- 静态分析不能证明生产环境行为；
- 测试覆盖当前实现，不代表所有平台与权限组合。
