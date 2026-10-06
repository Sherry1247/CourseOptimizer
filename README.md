# BadgerPlan / CourseOptimizer

面向 UW–Madison 学生的个人定制版 DARS + 四年选课规划器：覆盖全部本科专业，支持双专业重合课程优化、新生 / 转学生、自选毕业学期、拖拽换学期实时校验，并整合 Madgrades 成绩分布和 Rate My Professors 教授评分。

> BadgerPlan 不是 UW–Madison 官方产品，不能替代 DARS 或 academic advisor。正式选课前请以 DARS、Course Search & Enroll 和你的 advisor 为准。

## 功能

| 功能 | 说明 |
|---|---|
| 全部专业 | 262 个项目（204 个本科专业 + 58 个 named option），要求从 UW Guide 2026–27 解析 |
| 结构化要求 | 每个专业解析成要求块：全部必修 / 任选 N 门 / N 学分 / 学科编号规则（如“15 credits of A A E 200+”）/ 选一个 emphasis |
| 学院 & 通识要求 | L&S BA/BS/BM、工程、CALS、商学院 BBA、教育、SoHE、护理、药学；新版 Core GenEd（Summer 2026 起）与旧版 Gen Ed 自动按入学时间切换 |
| 先修关系 | 7,830 门课的 AND/OR 先修树：placement、年级（junior standing）、同学期 co-requisite、“Not open to students with credit for …” 互斥课 |
| 双专业 | 优先选择两个专业都能算的课；显示共享课程和节省学分；“Double major” 页按重合度给第一专业排序推荐第二专业 |
| 新生 / 转学生 | 起始学期、毕业学期、AP/IB/转学分（映射到 UW 课程或仅学分）、入学前第一个大学学期（决定 Gen Ed 版本） |
| Transcript 导入 | 上传 PDF/TXT/CSV/TSV/JSON 或粘贴课程记录；先匹配本地 UW 目录并人工复核，再转入 prior credit；原文件不持久化、不发送到第三方 |
| 拖拽规划 | 课程卡片可跨学期拖动或用 ⋯ 菜单移动/固定/删除；每次移动后端重新校验先修、开课季节、学分上限、互斥课，并刷新 audit |
| DARS 式审计 | 每个要求显示 已完成 / 已计划 / 部分 / 缺失；缺失块直接列出可选课程一键加入；解析置信度低的块标记 “verify” 并链接 Guide |
| Madgrades | 8,536 门课的历史成绩分布（累计 + 最近 10 学期 GPA 走势），课程卡片显示平均 GPA，可选 “GPA-friendly” 规划偏好 |
| RMP | 2,195 位授课教师的评分 / 难度 / would-take-again / 评价数（只存汇总，不存评论），附 RMP 链接 |
| 开课季节 | 由 5 年开课记录推断 Fall / Spring / Summer 和频率 |
| 保存 | 本地 SQLite 保存方案、浏览器自动保存草稿、导出/导入 JSON、打印 |

## 快速开始

```bash
python -m venv .venv
.venv\Scripts\activate            # macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python scripts/init_db.py         # 从 data/snapshot/*.json.gz 生成 data/badgerplan.db（约 2 秒，无需联网）
python -m uvicorn web_app:app --app-dir src --host 127.0.0.1 --port 8501
```

打开 <http://127.0.0.1:8501>。

测试：

```bash
python -m unittest discover -s tests -v
node --check web/static/app.js
```

## 架构

```text
data/
  snapshot/badgerplan-2026-27.json.gz   # 已提交的规范化目录快照（4 MB，可 diff）
  badgerplan.db                         # 本地生成的 SQLite（git 忽略）
  raw/                                  # 原始抓取数据（git 忽略，可由脚本重建）
scripts/
  scrape_uw_guide.py     # 抓 UW Guide：全部课程 + 全部本科专业要求 + named options
  fetch_uwcourses.py     # 下载 uw-coursemap-data（Madgrades 历史 + RMP 汇总）
  build_snapshot.py      # 原始数据 → 规范化快照（解析要求、先修、开课季节、成绩、教师）
  init_db.py             # 快照 → SQLite
src/
  ingest/
    codes.py             # 课程代码规范化；交叉列名（COMP SCI/MATH 240）别名
    guide_parser.py      # Guide 要求表 → 要求块（all / choose / credits / pattern / variants）
    designations.py      # Course Designation → 标签（comm_a, ethnic, hum, ge_ha …）
    uwcm.py              # Madgrades 分布、开课历史、RMP 汇总
  requisites.py          # 先修文本解析器 + 三值求值 + 最短先修链
  degree_rules.py        # 大学 / 学院层级学位要求（手工编码，附 Guide 链接）
  audit.py               # DARS 式审计（专业内一课一块；双专业间允许共享）
  planner.py             # 选课 + 先修展开 + gen-ed 填充 + 排学期 + 校验
  analysis.py            # 第二专业重合度排名
  catalog_db.py          # SQLite schema 与查询
  transcript.py          # Transcript 文本 → 本地课程目录的保守匹配（导入前复核）
  web_app.py             # Starlette API + 可扩展的分组 discovery search
web/static/              # 无构建步骤的前端（index.html / app.css / app.js）
tests/                   # 50 个当前单元 / 集成测试（另保留 1 个旧 Streamlit 测试）
legacy/                  # hackathon 原型（Java optimizer、Streamlit、旧静态页）
```

### 数据库表

`courses` · `course_aliases` · `course_tags` · `course_prereqs` · `grade_distributions` · `instructors` · `course_instructors` · `programs` · `requirement_blocks` · `requirement_slots` · `requirement_options` · `saved_plans` · `sources` · `meta`

例：哪些专业要求 COMP SCI 400？

```sql
SELECT DISTINCT p.name FROM requirement_options o
JOIN requirement_slots s ON s.id = o.slot_id
JOIN requirement_blocks b ON b.id = s.block_id
JOIN programs p ON p.id = b.program_id
WHERE o.course_code = 'COMP SCI 400' AND b.section = 'major';
```

### API

| Method | Path | 用途 |
|---|---|---|
| GET | `/api/meta` | 目录年份、统计、数据来源、标签名称 |
| GET | `/api/search?q=` | 首页统一搜索；返回带 `type/label/results` 的实体分组，未来可追加 labs/events 而不改首页结构 |
| GET | `/api/programs` · `/api/programs/{id}` | 专业列表 / 要求树 |
| GET | `/api/programs/{id}/second-majors` | 双专业重合排名 |
| GET | `/api/courses?q=&tag=` · `/api/courses/{code}` | 搜索 / 课程详情（成绩、教师、先修树、解锁课程、计入哪些专业） |
| POST | `/api/plan/generate` | 生成方案 |
| POST | `/api/plan/validate` | 校验用户编辑后的方案并返回完整 audit |
| POST | `/api/transcript/parse` | 解析 transcript 文本/PDF，只返回待复核的本地课程匹配，不直接写入计划 |
| GET/POST/DELETE | `/api/plans` · `/api/plans/{id}` | 保存的方案 |

## 更新数据（每学年一次）

```bash
python scripts/scrape_uw_guide.py      # → data/raw/guide/
python scripts/fetch_uwcourses.py      # → data/raw/uwcm/（约 215 MB，可断点续传）
python scripts/build_snapshot.py       # → data/snapshot/badgerplan-2026-27.json.gz
python scripts/init_db.py --force
```

## 数据来源与可信度

| 数据 | 来源 | 用法 |
|---|---|---|
| 专业要求、课程、学分、designation、先修文本 | [UW–Madison Guide](https://guide.wisc.edu/) 2026–27（官方） | 硬约束 |
| 成绩分布、学期历史、授课教师 | [Madgrades](https://madgrades.com/)，经 [uw-coursemap-data](https://github.com/twangodev/uw-coursemap-data)（MIT，uwcourses.com 的数据） | 软参考 / 排序偏好 |
| 教师评分 | Rate My Professors 汇总（同上来源） | 只显示汇总 + 链接，不存评论 |
| 开课季节 | 由最近 5 年成绩记录推断 | 排课约束（无记录时允许 Fall/Spring 并提示） |

**Madgrades API**：不需要单独申请 token —— 上述开源仓库已包含全部 Madgrades 历史分布。`src/integrations/madgrades.py` 保留为可选的官方 API 客户端。

### 已知限制

- 要求解析是启发式的：137 个专业高置信、92 个中等、24 个低（结构复杂，如音乐表演、亚洲语言各语种路线），9 个没有固定要求（Individual Major 等）或内容在 named option 页面。低置信的块在界面上标 “verify”。
- 回归测试：对 253 个可解析专业逐一自动生成四年方案，169 个专业要求满足 ≥ 90%，147 个 100%。
- 语言单元（高中外语）、GPA / residence、honors、“最多 N 学分可重复计算”这类规则需要在 audit 里手动勾选或以 DARS 为准。
- 双专业共享学分上限因学院而异，目前只显示共享量，不自动封顶。
- Transcript PDF 必须包含可选择的文字；扫描件需要先 OCR。课程匹配与学分值只是规划辅助，最终转入结果仍以 DARS / 官方 credit evaluation 为准。

### Labs / Events 扩展方向

首页搜索现在消费统一的 `groups[]` 结果，而不是把界面写死成三个并列卡片。未来接入实验室、研究机会和校园活动时，可新增 `lab` / `event` discovery provider 与独立详情页，并继续复用同一个搜索入口、实体链接和“加入计划/保存机会”的上下文动作。当前版本不会展示没有真实数据的空入口。

更详细的审计与路线见 [docs/ANALYSIS.md](docs/ANALYSIS.md)。
