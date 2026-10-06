# CourseOptimizer 审计与完善记录

更新日期：2026-09-30

## 1. 完善前的问题（第二轮审计）

第一轮已把架构改成 `SQLite → Python API → 网页`，但数据层几乎是空的：

| 问题 | 完善前 | 影响 |
|---|---|---|
| 先修关系 | 8,958 门课只有 **5 条** prerequisite | 导入器的 AST 解析失败，先修校验形同虚设 |
| 开课季节 | 27 门课有 Fall/Spring | 其他课程无法判断何时能修 |
| 专业 | 3 个（CS / Econ / Math），共 16 门必修 | 双专业只是两个短列表取交集 |
| 要求模型 | 只读 `all_of`；`choose_n` / `min_credits` 未使用 | 无法表达“任选 N 门”“N 学分”“选一个方向” |
| 学位 / 通识 | 无 | 算不出 120 学分、breadth、Comm A/B、QR 是否满足 |
| Madgrades / RMP | 30 条 hackathon 假数据 | GPA 显示不可信 |
| 前端 | 无 audit 面板、无课程详情、无转学分映射 | 离 “DARS” 差距大 |
| 交叉列名 | `COMP SCI 240` 与 `MATH 240` 被当成两门课 | 专业要求匹配失败 |

## 2. 本轮完成内容

### 数据

- **UW Guide 2026–27 全量抓取**：10,445 个课程块（合并交叉列名后 8,982 门课）、204 个本科专业、58 个 named option。`scripts/scrape_uw_guide.py` 可每年重跑，输出与本次浏览器抽取逐字节一致（有测试）。
- **先修解析器**（`src/requisites.py`）：从 Guide 原文 + 链接课程代码生成 AND/OR 树；处理简写（`MATH 211, 217, or 221`）、已停开课程、`(215 prior to Fall 2024)` 历史注释、句中 `not open to` 互斥、`concurrent enrollment in X` 同学期 co-req、placement、年级要求、ESL 限制。7,830 门课有结构化先修。
- **Madgrades + RMP**：来自 uwcourses.com 的开源数据仓库（MIT）。8,536 门课的成绩分布（累计 + 最近 10 学期，含授课教师），2,195 位教师的 RMP 汇总。只保存汇总数字，不保存评论。
- **开课季节**：以 5 年成绩记录为主，发布的 “typically offered” 字段只做并集（该字段在导出中只反映最近一个学期，单独使用会把 SPANISH 101 误判为只在夏季开）。

### 要求解析（`src/ingest/guide_parser.py`）

识别 `Complete one/two:`、`(three required)`、`N credits from`、`one course from four of the eight categories`、`Option A/B`、`X Emphasis` 同级方向、Named Options、表格合计学分行（用来判断“全部必修”还是“学分池”）、段落里的规则句。每个块带置信度：

| 置信度 | 专业数 |
|---|---|
| high | 137 |
| medium | 92 |
| low | 24 |
| 无固定要求（Individual Major 等） | 9 |

### 规划引擎（`src/planner.py` + `src/audit.py`）

1. 按要求块选课，打分考虑：双专业重合（最高权重）、是否同时满足 gen-ed、先修链长度、是否近年开过课、Guide 四年样例、Madgrades GPA（按偏好加权）、互斥课冲突。
2. 先修展开：OR 分支选最便宜路径；排除“依赖当前课程的已计划课”造成的环（SPANISH 226 ← 204 or 311，而 311 又需要 226）。
3. 删除被共享课程取代的冗余课，再重新填充。
4. 学院 / 通识规则用高选课量、低门槛、一次覆盖多个标签的课程补足（不推荐 ESL / ROTC / honors-only）。
5. 排学期：关键路径优先、co-req 同学期、按学期数推算年级、每学期最多 3 门 400+ 和 2 门历史 GPA < 3.0 的课、专业课均匀分布、选修补足 120 学分并均匀摊开。
6. 同一个校验函数用于生成结果和用户拖拽后的方案。

### 回归结果

对全部 253 个有要求的专业逐一生成四年方案（Fall 2026 → Spring 2030，无暑期，15 学分目标）：

| 专业要求满足率 | 专业数 |
|---|---|
| 100% | 147 |
| ≥ 90% | 169 |
| ≥ 75% | 215 |
| ≥ 50% | 245 |

CS BS + Data Science BS 双专业：两个专业、学院与 Core GenEd 全部满足，9 门课共享，无先修冲突。

## 3. 仍需人工或后续工作

1. **低置信专业**：音乐表演各方向、亚洲语言（按语种选一条路线）、Agroecology、Horticulture 等要求结构特殊，需要逐个人工校对或写专门规则。
2. **学分上限与重复计算**：各学院对双专业共享学分、major 内 “只能计一次” 的限制目前只在文字中提示。
3. **Course Search & Enroll 实时 section 数据**（时间冲突、座位）未接入；Madgrades 历史有约一学期延迟。
4. **AP/IB 学分对照表**：目前由学生手动映射到 UW 课程；可以抓取 UW 官方 AP 表自动映射。
5. **多人部署**：需要账户、鉴权和 PostgreSQL 后再对外提供服务。
