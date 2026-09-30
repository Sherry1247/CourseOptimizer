from __future__ import annotations

from datetime import date
from pathlib import Path

import streamlit as st

from planner import (
    COURSE_SEARCH_URL,
    DEGREE_AUDIT_URL,
    Catalog,
    generate_plan,
    guide_url,
    madgrades_url,
    prerequisite_depth,
    rate_my_professors_url,
)


APP_DIR = Path(__file__).resolve().parent
DATA_PATH = APP_DIR / "uw_madison_data.json"

st.set_page_config(
    page_title="BadgerPlan · UW–Madison Course Planner",
    page_icon="🦡",
    layout="wide",
)

st.markdown(
    """
    <style>
      .block-container {max-width: 1280px; padding-top: 2rem;}
      [data-testid="stMetric"] {background:#fff7f7; border:1px solid #f2d6d7;
        border-radius:14px; padding:14px 18px;}
      .course-card {border:1px solid #e6e6e6; border-left:5px solid #c5050c;
        border-radius:12px; padding:14px 16px; margin:8px 0; background:white;}
      .course-code {font-weight:750; color:#9b0000;}
      .muted {color:#666; font-size:.9rem;}
      .source-note {background:#f5f7fa; border-radius:12px; padding:14px 16px;}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_resource
def load_catalog() -> Catalog:
    return Catalog.from_json(DATA_PATH)


catalog = load_catalog()


def format_course(code: str) -> str:
    course = catalog.courses[code]
    return f"{code} · {course.name}"


def render_course_card(
    course, *, is_overlap: bool = False, is_supporting: bool = False
) -> None:
    badges = [f"{course.credits} credits", "/".join(course.semesters)]
    if is_overlap:
        badges.append("double-count candidate")
    if is_supporting:
        badges.append("supporting prerequisite")
    if course.prerequisites:
        badges.append("Prereq: " + ", ".join(course.prerequisites))
    st.markdown(
        f"""
        <div class="course-card">
          <div class="course-code">{course.code}</div>
          <div>{course.name}</div>
          <div class="muted">{' · '.join(badges)}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

st.title("🦡 BadgerPlan")
st.caption("UW–Madison degree planning prototype · prerequisite-aware · double-major aware")

with st.sidebar:
    st.header("Build your plan")
    major_names = list(catalog.majors)
    primary_major = st.selectbox("Primary major", major_names)
    add_second_major = st.checkbox("Add a second major")
    second_options = [name for name in major_names if name != primary_major]
    second_major = (
        st.selectbox("Second major", second_options) if add_second_major else None
    )

    st.divider()
    completed = st.multiselect(
        "Completed / transferred courses",
        options=sorted(catalog.courses),
        format_func=format_course,
        help="These courses count as completed before the first planned term.",
    )
    col1, col2 = st.columns(2)
    start_term = col1.selectbox("Start term", ["Fall", "Spring"])
    start_year = col2.number_input(
        "Start year", min_value=date.today().year, max_value=date.today().year + 6
    )
    years = st.slider("Planning horizon", 1, 5, 4, format="%d years")
    max_credits = st.slider("Max major credits / term", 3, 18, 15)
    priority_label = st.selectbox(
        "Preference",
        ["Balanced", "GPA-friendly", "More challenging"],
        help="Prerequisites and scarce offerings always outrank soft preferences.",
    )
    priority = {
        "Balanced": "balanced",
        "GPA-friendly": "gpa",
        "More challenging": "challenge",
    }[priority_label]

majors = [primary_major] + ([second_major] if second_major else [])
result = generate_plan(
    catalog,
    majors,
    completed,
    start_term=start_term,
    start_year=int(start_year),
    years=years,
    max_credits_per_term=max_credits,
    priority=priority,
)

known_completed = set(completed) & result.required_courses
overlap_credits = sum(
    catalog.courses[code].credits
    for code in result.overlap_courses
    if code in catalog.courses
)
overlap_limit = catalog.double_major_rules.get("max_overlap_credits")
counted_overlap_credits = (
    min(overlap_credits, int(overlap_limit)) if overlap_limit else overlap_credits
)

metric_columns = st.columns(4)
metric_columns[0].metric("Required courses", len(result.required_courses))
metric_columns[1].metric("Already completed", len(known_completed))
metric_columns[2].metric("Planned major credits", result.planned_credits)
metric_columns[3].metric(
    "Overlap credits", counted_overlap_credits if len(majors) > 1 else 0
)

st.info(
    "This is a planning aid built from a small demo catalog—not an official degree audit. "
    "Confirm requirements in DARS and current sections in Course Search & Enroll."
)

for warning in result.warnings:
    st.warning(warning)

tab_plan, tab_overlap, tab_graph, tab_explorer, tab_sources = st.tabs(
    ["Semester plan", "Double-major fit", "Prerequisite map", "Course explorer", "Sources"]
)

with tab_plan:
    st.subheader("Major-course sequence")
    st.caption(
        "Only explicit major requirements are scheduled. Empty space is intentionally left "
        "for general education, electives, certificates, and non-course commitments."
    )

    columns = st.columns(2)
    for index, term in enumerate(result.terms):
        with columns[index % 2]:
            with st.container(border=True):
                st.markdown(f"#### {term.label}")
                st.caption(f"{term.credits} planned major credits")
                if not term.courses:
                    st.write("Open for general education / electives")
                for course in term.courses:
                    render_course_card(
                        course,
                        is_overlap=course.code in result.overlap_courses,
                        is_supporting=course.code in result.supporting_courses,
                    )

    if result.unscheduled_courses or result.missing_catalog_courses:
        st.subheader("Needs attention")
        if result.unscheduled_courses:
            st.write(
                "Not placed: " + ", ".join(sorted(result.unscheduled_courses))
            )
        if result.missing_catalog_courses:
            st.write(
                "Required but absent from demo catalog: "
                + ", ".join(sorted(result.missing_catalog_courses))
            )

    export_rows = []
    for term in result.terms:
        for course in term.courses:
            export_rows.append(
                {
                    "term": term.label,
                    "course": course.code,
                    "name": course.name,
                    "credits": course.credits,
                    "prerequisites": "; ".join(course.prerequisites),
                    "double_count_candidate": course.code in result.overlap_courses,
                }
            )
    if export_rows:
        csv_lines = [
            "term,course,name,credits,prerequisites,double_count_candidate"
        ]
        for row in export_rows:
            values = [
                str(row[key]).replace('"', '""')
                for key in (
                    "term",
                    "course",
                    "name",
                    "credits",
                    "prerequisites",
                    "double_count_candidate",
                )
            ]
            csv_lines.append(",".join(f'"{value}"' for value in values))
        st.download_button(
            "Download plan as CSV",
            data="\n".join(csv_lines),
            file_name="badgerplan.csv",
            mime="text/csv",
        )

with tab_overlap:
    if len(majors) == 1:
        st.write("Add a second major in the sidebar to compare requirement overlap.")
    else:
        st.subheader(f"{majors[0]} + {majors[1]}")
        if result.overlap_courses:
            st.success(
                f"Found {len(result.overlap_courses)} shared required courses "
                f"({overlap_credits} catalog credits)."
            )
            if overlap_limit:
                st.caption(
                    f"The demo data currently records an overlap cap of {overlap_limit} credits; "
                    "verify the rule for your schools/colleges and catalog year."
                )
            for code in sorted(result.overlap_courses):
                render_course_card(catalog.courses[code], is_overlap=True)
        else:
            st.warning("No exact required-course overlap exists in the local demo data.")

        first = set(catalog.majors[majors[0]]["required_courses"])
        second = set(catalog.majors[majors[1]]["required_courses"])
        col1, col2 = st.columns(2)
        col1.markdown(f"#### Only {majors[0]}")
        col1.write(", ".join(sorted(first - second)) or "None")
        col2.markdown(f"#### Only {majors[1]}")
        col2.write(", ".join(sorted(second - first)) or "None")

with tab_graph:
    st.subheader("Prerequisite chains")
    relevant = result.required_courses & set(catalog.courses)
    dot_lines = [
        "digraph prerequisites {",
        'rankdir="LR";',
        'node [shape="box", style="rounded,filled", fillcolor="#fff7f7", color="#c5050c"];',
    ]
    for code in sorted(relevant):
        course = catalog.courses[code]
        dot_lines.append(f'"{code}" [label="{code}"];')
        for prerequisite in course.prerequisites:
            dot_lines.append(f'"{prerequisite}" -> "{code}";')
    dot_lines.append("}")
    st.graphviz_chart("\n".join(dot_lines), width="stretch")

    rows = []
    for code in sorted(relevant, key=lambda value: prerequisite_depth(value, catalog.courses)):
        course = catalog.courses[code]
        rows.append(
            {
                "Course": code,
                "Prerequisites": ", ".join(course.prerequisites) or "None",
                "Chain depth": prerequisite_depth(code, catalog.courses),
                "Typical terms": ", ".join(course.semesters),
            }
        )
    st.dataframe(rows, width="stretch", hide_index=True)

with tab_explorer:
    selected_code = st.selectbox(
        "Course", sorted(catalog.courses), format_func=format_course
    )
    course = catalog.courses[selected_code]
    st.subheader(f"{course.code} · {course.name}")
    st.write(course.description)
    detail_columns = st.columns(4)
    detail_columns[0].metric("Credits", course.credits)
    detail_columns[1].metric(
        "Demo avg GPA", f"{course.avg_gpa:.2f}" if course.avg_gpa is not None else "—"
    )
    detail_columns[2].metric(
        "Demo A rate",
        f"{course.grade_a_rate:.0%}" if course.grade_a_rate is not None else "—",
    )
    detail_columns[3].metric(
        "Demo difficulty",
        f"{course.difficulty:.0f}/5" if course.difficulty is not None else "—",
    )
    st.write(
        "**Prerequisites:** "
        + (", ".join(course.prerequisites) if course.prerequisites else "None in demo data")
    )
    st.write("**Usually offered:** " + ", ".join(course.semesters))
    if course.typical_workload:
        st.write("**Demo workload estimate:** " + course.typical_workload)

    link_columns = st.columns(4)
    link_columns[0].link_button("Official Course Guide", guide_url(course.code))
    link_columns[1].link_button("Course Search & Enroll", COURSE_SEARCH_URL)
    link_columns[2].link_button("Madgrades", madgrades_url(course.code))
    link_columns[3].link_button("Rate My Professors", rate_my_professors_url())
    st.caption(
        "Professor ratings belong to instructors/sections, not to a course as a whole. "
        "Use them as one subjective signal, not as a scheduling constraint."
    )

with tab_sources:
    st.subheader("What each source is for")
    st.markdown(
        """
        - **UW Guide:** authoritative catalog descriptions, requisites, designations, and program requirements.
        - **Course Search & Enroll:** current-term sections, seats, times, instructors, and enrollment checks.
        - **DARS:** the student's official degree audit and the final source for requirement completion.
        - **Madgrades:** historical grade distributions; useful context, never a guarantee of future outcomes.
        - **Rate My Professors:** subjective reviews. This prototype links out instead of scraping or republishing reviews.
        """
    )
    st.link_button("Open DARS information", DEGREE_AUDIT_URL)
    st.link_button("Open Course Search & Enroll", COURSE_SEARCH_URL)

    st.subheader("Local data status")
    st.write(
        f"Catalog: **{catalog.metadata.get('academic_year', 'unknown')}** · "
        f"last marked update: **{catalog.metadata.get('last_updated', 'unknown')}**"
    )
    issues = catalog.validate()
    if issues:
        st.warning(f"The demo data has {len(issues)} integrity issue(s):")
        for issue in issues:
            st.write("- " + issue)
    else:
        st.success("All local prerequisite and requirement references resolve.")

    st.markdown(
        """
        <div class="source-note">
        <strong>Important:</strong> the grade, difficulty, workload, professor-rating, and some
        offering fields in this hackathon dataset are demo estimates. They are labeled as such in
        the interface and must be replaced by timestamped source-backed records before production.
        </div>
        """,
        unsafe_allow_html=True,
    )
