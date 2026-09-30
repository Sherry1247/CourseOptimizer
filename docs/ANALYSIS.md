# CourseOptimizer 现状审计与完善路线

更新日期：2026-09-29

## 结论

原仓库是一个 hackathon 展示原型：视觉页面、Java API、Streamlit 入口和 JSON 数据同时存在，但没有共享同一套数据模型。它可以演示概念，不能可靠回答“我还缺什么课、何时能修、双专业能省多少学分”。第一轮先修复了规划正确性；第二轮把产品主线升级为 `SQLite → Python planning/API → draggable web workspace`，Java、Streamlit 与旧静态页保留为 legacy prototype。

## 原有关键问题

### 1. 数据和代码互相脱节

- Java `CourseRepository` 只有约十门硬编码课程，没有读取 `uw_madison_data.json`。
- `DoubleMajorHelper` 又维护一份独立的专业课程清单，其中一些课程根本不在 repository。
- 网页使用 `CS 200`，JSON 使用 `COMP SCI 200`，专业名称也存在缩写/全称两套表示。
- JSON 声称来源于 UW Guide，但成绩、教授评分、workload 等字段没有 provenance，不能验证。

结果：页面看似能规划，实际经常静默遗漏课程。

### 2. 原排课逻辑有 correctness bug

- `StudentProfile.completedCourses` 被解析但未注入 optimizer 的初始 completed state。
- 某学期加入课程后立刻更新 completed set，后面的课程可能在同一学期错误地把它当作已完成 prerequisite。
- `PrerequisiteGraph.topologicalSort()` 未实现。
- difficulty balancer 可能移动课程，但没有完整重新验证 prerequisite 顺序和开课学期。
- “避免早八”会把 required course 过滤掉，而不是给出 trade-off/警告。
- 只生成固定八学期，不真正使用网页上的 3/4/5 年输入。

### 3. 双专业模型过度简化

- 原逻辑只是对两个硬编码列表做 union。
- overlap 依赖 `Course.majors`，但 repository 中多数课程没有设置 majors，因此高优先级逻辑基本失效。
- 没有表达学院之间的 double-counting 限制、resident credit、upper-level credit、选修组等规则。
- 展示页的 overlap/saved credits 是写死数字，不来自规划结果。

### 4. 外部资源“写在 README”，没有真实集成

- Madgrades、Rate My Professors 仅存在于宣传文案和虚构字段。
- 教授评分被错误建模成 course-level 属性；真实情况应绑定 term/section/instructor。
- Rate My Professors 没有稳定的公开官方 API，直接抓取会带来维护与条款风险。
- 当前-term sections、时间冲突、seat availability 没有数据源。

### 5. 工程化不足

- README 要求 Node/npm，但仓库没有 `package.json`。
- Streamlit 页面只有标题，真正的 demo 在静态 HTML 中并依赖另起 Java server。
- API 手写 JSON parser/serializer，字符串转义、嵌套对象与错误响应都不健壮。
- CORS 为 `*`，没有 schema validation、health endpoint、结构化错误或测试。
- 没有 dependency file、自动测试或数据校验。

## 本轮已经完成

- 新增独立、可测试的 `src/planner.py`。
- 已修课程被纳入初始状态。
- prerequisite 只能由更早学期满足。
- 开课季、规划年限和每学期学分上限成为真实约束。
- 双专业使用 requirement union 规划，用 intersection 展示重合候选。
- 缺失 catalog 数据和未排入课程不再静默丢失。
- Streamlit 页面覆盖规划、重合分析、先修图、课程浏览、来源边界和 CSV 导出。
- 课程页整合 UW Guide、Course Search & Enroll、DARS、Madgrades、RMP 的入口。
- 对 demo 指标做显著标注，不再把模拟数字冒充实时数据。
- 新增标准库单元测试和正确的 Python 启动说明。
- 新增浅色 UW 深红产品界面、first-year/transfer 入口与 graduation-year timeline。
- 新增原生 HTML5 课程拖拽，拖动后重新验证 prerequisite、offering 和 credit load。
- 新增 SQLite catalog、requirement/provenance、external signal 和 saved-plan schema。
- 新增 UW Courses 公开 Parquet snapshot 导入器；本地已验证导入 8,952 门课程。
- 新增 server-side Madgrades token client，密钥不会进入浏览器。

## 正确的产品数据模型

后续不应把专业要求继续压成一个课程列表。至少需要：

```text
ProgramVersion
  school/college + program + degree + catalog_year
  RequirementBlock[]
    type: all_of | choose_n | min_credits | level | designation
    CourseSet / subject filters / exclusions
    double_count_policy

CourseVersion
  canonical course id + effective term
  requisites (AND/OR groups, concurrent allowed, placement/consent conditions)
  credits range + designations

Section
  term + section + instructor + meetings + seats + modality

OutcomeSignal
  source + observed_at + sample_size + aggregation level
  grade distribution / rating / workload
```

规划结果也需要保留每门课满足了哪个 requirement block，才能解释“为什么推荐这门课”和“两个专业分别算到了哪里”。

## 数据接入建议

### UW Guide / program requirements

按 catalog year 保存快照，并进行结构化抽取 + 人工 review。任何规则变化都要可 diff、可回滚。仅解析自然语言 prerequisite 会有歧义，应保留原文与结构化版本。

### Course Search & Enroll / DARS

Course Search & Enroll 是当前 section 和正式选课检查的来源；DARS 是 degree audit。若没有学校授权，不应假设存在稳定公开 API。MVP 可以让用户手工勾选已修课或导入自己下载的报告，且不要收集不必要的学生身份信息。

### Madgrades

官网当前提供需 token 的 API。生产接入应使用 server-side secret、缓存、限流、source timestamp 和 sample size；历史 GPA 只能作为偏好信号，不应转成“容易课”承诺。

### Rate My Professors

当前采用 link-out。若未来要在站内展示，优先寻求正式许可/授权数据，并把 instructor identity matching、样本量、时间衰减与偏差提示纳入设计。不要把评分存成课程固有属性。

## 推荐迭代顺序

1. **数据可信度**：先完成一个专业、一个 catalog year 的全量 requirement blocks 与 course prerequisites。
2. **可解释 audit**：显示每个 requirement 的 satisfied / planned / missing 状态。
3. **交互规划**：锁定、拖动、替换课程后实时验证 prerequisite 与 offering。
4. **section 层**：接入当期时间、教师、seat 和冲突检查。
5. **优化器**：采用 CP-SAT/ILP，生成多个方案并解释 infeasibility。
6. **扩专业**：在 schema 和验证流程稳定后再增加 majors，而不是先追求课程数量。

## 验收标准

- 所有硬约束都有 source + catalog year。
- 任意 prerequisite 关系都能通过测试证明不会同学期误满足。
- 任何未安排 requirement 必须出现在显式 warning 中。
- 双专业每个 overlap 都能追踪到两个 requirement blocks，而非只按 subject 猜测。
- 成绩/评分数据带来源、时间和样本量，并能在缺失时正常降级。
- 用户在提交正式选课前始终看到 DARS / Course Search & Enroll 的核验入口。
