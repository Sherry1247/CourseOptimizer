# BadgerPlan / CourseOptimizer

BadgerPlan 是一个面向 UW–Madison 学生的个性化 degree-planning workspace：支持新生与转学生、双专业、目标毕业年份、先修课校验，以及可拖拽的学期规划板。

> BadgerPlan 不是 UW–Madison 官方产品，也不能替代 DARS 或 academic advisor。专业要求以学生对应 catalog year 的 UW Guide 和 DARS 为准。

## 当前产品

- 浅色 UW 深红视觉系统，响应式桌面/移动布局
- First-year / Transfer 两种入口
- 自定义入学学期、入学年份和目标毕业年份
- 单专业或双专业要求合并、共享课程标记
- 已修、AP/IB、placement 和 transfer course 输入
- prerequisite-aware 自动排课
- 原生 HTML5 跨学期拖拽
- 拖动后即时检查先修顺序、开课季和学分上限
- 8,952 门 UW 课程的本地 SQLite 检索（通过公开 UW Courses snapshot 导入）
- 本地保存 plan、JSON 导出和课程库手动加课
- Madgrades server-side API client 接入位

## 技术结构

```text
web/static/
  index.html              # 产品页面
  app.css                 # UW 浅色/深红设计系统
  app.js                  # 拖拽、校验、搜索、保存
src/
  web_app.py              # Starlette API
  catalog_db.py           # SQLite schema、provenance、plan persistence
  planner.py              # 无 UI 依赖的 prerequisite planner
  integrations/
    madgrades.py          # Madgrades token client
scripts/
  init_db.py              # 初始化本地数据库
  sync_uwcourses.py       # 导入公开的 UW Courses Parquet snapshot
tests/                    # planner、database、legacy UI tests
```

## 运行新版网站

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
python scripts\init_db.py
python scripts\sync_uwcourses.py
python -m uvicorn web_app:app --app-dir src --host 127.0.0.1 --port 8501
```

打开 <http://127.0.0.1:8501>。

运行测试：

```bash
python -m unittest discover -s tests -v
node --check web/static/app.js
```

## 数据库设计

SQLite 数据库存储：

- `sources`：来源、权威级别、访问时间和 terms URL
- `catalog_versions`：catalog year 与导入状态
- `programs`：专业、degree、school/college 和 Guide URL
- `requirement_blocks`：`all_of`、`choose_n`、`min_credits`、`designation`
- `requirement_options`：requirement block 中的课程候选
- `courses`：课程代码、学分、课程描述、原始 requisite 文本和 provenance
- `prerequisites`：结构化先修关系和 evidence text
- `course_offerings`：常见开课季
- `external_signals`：Madgrades 等外部指标、样本量和时间
- `saved_plans` / `plan_items`：用户调整后的学期规划

数据库文件 `data/courseoptimizer.db` 会在本地生成，不提交到 Git。

## 数据可信度

| 数据 | 来源 | 使用方式 |
|---|---|---|
| 专业要求 | UW–Madison Guide | 硬约束；必须按 catalog year 审核 |
| 课程与 requisite 原文 | UW Guide；当前全量检索可由 UW Courses snapshot 派生 | 课程库与 prerequisite candidate |
| 当期 section、时间、seat | Course Search & Enroll | 尚未实时接入 |
| 学生正式完成情况 | DARS / 用户输入 | 当前由用户输入，DARS 是最终依据 |
| 历史成绩 | Madgrades API | 软参考，不作为毕业硬约束 |
| 教授评价 | Link-out / 未来正式授权数据 | 不将非官方抓取作为核心依赖 |

UW Courses 是开源第三方项目，不是 UW 官方。同步器只把它作为可追踪的派生课程快照；专业毕业要求不会以它替代 UW Guide。

## Madgrades API

Madgrades 当前要求用户在其官网通过 GitHub 登录取得 token。取得 token 后，在启动后端前设置：

```bash
set MADGRADES_API_TOKEN=your_token
```

`src/integrations/madgrades.py` 只在服务端读取该变量，不把 token 发给浏览器或写入仓库。由于 API contract 可能变化，实际 endpoint 应从账号中的当前文档配置，不依赖未记录的私有接口。

## 仍需完成的生产工作

当前课程库已全量化，但专业 requirement blocks 仍是三个专业的 pilot core coverage。下一阶段应：

1. 按 2026–2027 UW Guide 逐专业导入并人工复核 requirement blocks。
2. 完整表达“任选 N 门”、最低学分、upper-level、residence、学校/学院间 double-count policy。
3. 接入 current-term Course Search & Enroll section 数据。
4. 对接 DARS 导入或学生授权的数据流程。
5. 配置 Madgrades token，并缓存按课程、教师、学期聚合的分布数据。
6. 加入账户、鉴权、PostgreSQL migration 和隐私策略后再部署为多人服务。

更详细的原型审计见 [docs/ANALYSIS.md](docs/ANALYSIS.md)。
