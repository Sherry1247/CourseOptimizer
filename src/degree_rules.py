"""University and school/college degree requirements, encoded from the 2026–27 UW Guide.

These rules are attribute based (course designations, levels, credits) rather
than course lists, so they are written by hand from the Guide tables and kept
small and reviewable.  Every rule carries the Guide URL it was taken from.

Designation tags used by courses (see ``ingest/designations.py``):
    comm_a comm_b qr_a qr_b ethnic hum lit ss bio phys nat lang las
    level_e level_i level_a
    ge_cl ge_mqr ge_nsw ge_nswl ge_sbs ge_ha ge_cp   (Core GenEd, Summer 2026+)
"""

from __future__ import annotations

GUIDE = "https://guide.wisc.edu/undergraduate/"
LS_URL = "https://guide.wisc.edu/undergraduate/letters-science/#requirementstext"

CORE_GENED_START = ("Summer", 2026)  # applies to students whose first college term is Summer 2026 or later


def _d(rid, name, tags, *, credits=None, courses=None, min_course_credits=None,
       placement=False, exclude_subjects=None, group=None, note=None, url=GUIDE):
    return {
        "id": rid, "name": name, "type": "designation", "tags": tags,
        "credits": credits, "courses": courses, "min_course_credits": min_course_credits,
        "placement": placement, "exclude_subjects": exclude_subjects or [],
        "group": group, "note": note, "url": url,
    }


def _c(rid, name, options, *, count=1, note=None, url=GUIDE):
    return {"id": rid, "name": name, "type": "course_list", "options": options,
            "count": count, "note": note, "url": url}


def _manual(rid, name, note, url=GUIDE):
    return {"id": rid, "name": name, "type": "manual", "note": note, "url": url}


TOTAL_120 = {"id": "total", "name": "Total degree credits", "type": "total_credits", "credits": 120, "url": GUIDE}

CORE_GENED = [
    _d("ge_cp", "Core GenEd: Civics & Perspectives", ["ge_cp"], credits=3),
    _d("ge_cl", "Core GenEd: Communication & Literacy", ["ge_cl"], credits=6, placement=True,
       note="May be partially satisfied by a qualifying English placement score."),
    _d("ge_ha", "Core GenEd: Humanities & Arts", ["ge_ha"], credits=6),
    _d("ge_mqr", "Core GenEd: Mathematics & Quantitative Reasoning", ["ge_mqr"], credits=6, placement=True,
       note="May be partially satisfied by a qualifying math placement score."),
    _d("ge_nsw", "Core GenEd: Natural Science & Wellness", ["ge_nsw", "ge_nswl"], credits=6),
    _d("ge_nswl", "Core GenEd: one Natural Science & Wellness + Lab course", ["ge_nswl"], courses=1),
    _d("ge_sbs", "Core GenEd: Social & Behavioral Science", ["ge_sbs"], credits=3),
]

LEGACY_GENED = [
    _d("g_comm_a", "Gen Ed: Communication A", ["comm_a"], courses=1, placement=True),
    _d("g_comm_b", "Gen Ed: Communication B", ["comm_b"], courses=1),
    _d("g_qr_a", "Gen Ed: Quantitative Reasoning A", ["qr_a"], courses=1, placement=True),
    _d("g_qr_b", "Gen Ed: Quantitative Reasoning B", ["qr_b"], courses=1),
    _d("g_ethnic", "Gen Ed: Ethnic Studies", ["ethnic"], courses=1, min_course_credits=3),
    _d("g_hum", "Gen Ed breadth: Humanities/Literature/Arts", ["hum", "lit"], credits=6),
    _d("g_nat", "Gen Ed breadth: Natural Science", ["bio", "phys", "nat"], credits=4,
       note="4–6 credits: one 4–5 credit lab course or two courses totaling 6 credits."),
    _d("g_ss", "Gen Ed breadth: Social Studies", ["ss"], credits=3),
]

UNIVERSITY_EXTRA = [
    _manual("u_language", "University language requirement",
            "Two high school units of one language, or one course with the second-semester language designation."),
]

LS_COMMON = [
    _d("ls_comm_a", "L&S Communication A", ["comm_a"], courses=1, placement=True, url=LS_URL),
    _d("ls_comm_b", "L&S Communication B", ["comm_b"], courses=1, url=LS_URL),
    _d("ls_qr_a", "L&S Quantitative Reasoning A", ["qr_a"], courses=1, placement=True, url=LS_URL),
    _d("ls_qr_b", "L&S Quantitative Reasoning B", ["qr_b"], courses=1, url=LS_URL),
    _d("ls_ethnic", "L&S Ethnic Studies", ["ethnic"], courses=1, min_course_credits=3, url=LS_URL),
    _d("ls_hum", "L&S Breadth: Humanities", ["hum", "lit"], credits=12, url=LS_URL),
    _d("ls_lit", "L&S Breadth: Literature (within Humanities)", ["lit"], credits=6, url=LS_URL),
    _d("ls_ss", "L&S Breadth: Social Sciences", ["ss"], credits=12, url=LS_URL),
    {"id": "ls_las", "name": "Liberal Arts & Science coursework", "type": "tag_credits", "tags": ["las"], "credits": 108, "url": LS_URL},
    {"id": "ls_depth", "name": "Intermediate/Advanced coursework", "type": "tag_credits", "tags": ["level_i", "level_a"], "credits": 60, "url": LS_URL},
    TOTAL_120,
]

LS_BS = LS_COMMON + [
    _d("ls_nat", "L&S Breadth: Natural Sciences", ["bio", "phys", "nat"], credits=12, url=LS_URL),
    _d("ls_bio", "L&S Breadth: Biological Science (within Natural Sciences)", ["bio"], credits=6, url=LS_URL),
    _d("ls_phys", "L&S Breadth: Physical Science (within Natural Sciences)", ["phys"], credits=6, url=LS_URL),
    {"id": "ls_bs_math", "name": "BS Mathematics", "type": "ls_bs_math", "courses": 2, "url": LS_URL,
     "note": "Two 3+ credit Intermediate/Advanced MATH, COMP SCI, or STAT courses; at most one each from COMP SCI and STAT."},
    _manual("ls_language", "L&S BS Language", "Third unit of a language other than English (high school units count).", LS_URL),
]

LS_BA = LS_COMMON + [
    _d("ls_nat", "L&S Breadth: Natural Sciences", ["bio", "phys", "nat"], credits=12, url=LS_URL),
    _d("ls_bio1", "L&S Breadth: one 3+ credit Biological Science course", ["bio"], courses=1, min_course_credits=3, url=LS_URL),
    _d("ls_phys1", "L&S Breadth: one 3+ credit Physical Science course", ["phys"], courses=1, min_course_credits=3, url=LS_URL),
    _manual("ls_language", "L&S BA Language",
            "Fourth unit of one language, or third unit of one language plus second unit of another.", LS_URL),
]

LS_BM = [
    _d("ls_comm_a", "Communication A", ["comm_a"], courses=1, placement=True),
    _d("ls_comm_b", "Communication B", ["comm_b"], courses=1),
    _d("ls_qr_a", "Quantitative Reasoning A", ["qr_a"], courses=1, placement=True),
    _d("ls_qr_b", "Quantitative Reasoning B", ["qr_b"], courses=1),
    _d("ls_ethnic", "Ethnic Studies", ["ethnic"], courses=1, min_course_credits=3),
    _d("bm_hum", "Breadth: Humanities", ["hum", "lit"], credits=6),
    _d("bm_ss", "Breadth: Social Sciences", ["ss"], credits=3),
    _d("bm_nat", "Breadth: Natural Sciences", ["bio", "phys", "nat"], credits=4),
    {"id": "ls_depth", "name": "Intermediate/Advanced coursework", "type": "tag_credits", "tags": ["level_i", "level_a"], "credits": 60},
    _manual("ls_language", "Language", "Second unit of one language other than English."),
    TOTAL_120,
]

ENGINEERING = [
    _d("egr_comm_a", "Engineering Communication 1 (Comm A)", ["comm_a"], courses=1, placement=True),
    _d("egr_hum", "Humanities or Literature (6 cr)", ["hum", "lit"], credits=6),
    _d("egr_ss", "Social Sciences (3 cr)", ["ss"], credits=3),
    _d("egr_ethnic", "Ethnic Studies", ["ethnic"], courses=1, min_course_credits=3),
    TOTAL_120,
]

CALS = [
    _c("cals_chem", "CALS Introductory Chemistry", [["CHEM 103"], ["CHEM 108"], ["CHEM 109"]]),
    _d("cals_ethnic", "CALS Ethnic Studies", ["ethnic"], credits=3),
    _d("cals_comm_a", "CALS Communication A", ["comm_a"], courses=1, placement=True),
    _d("cals_comm_b", "CALS Communication B", ["comm_b"], courses=1),
    _d("cals_qr_a", "CALS Quantitative Reasoning A", ["qr_a"], courses=1, placement=True),
    _d("cals_qr_b", "CALS Quantitative Reasoning B", ["qr_b"], courses=1),
    _d("cals_bio", "CALS Biological Science (5 cr)", ["bio"], credits=5),
    _d("cals_addl_sci", "CALS Additional Science (3 cr)", ["bio", "phys", "nat"], credits=3),
    _d("cals_sci_breadth", "CALS Science Breadth (3 cr)", ["bio", "phys", "nat", "ss"], credits=3),
    _d("cals_hum", "CALS Humanities (6 cr)", ["hum", "lit"], credits=6),
    _d("cals_ss", "CALS Social Sciences (3 cr)", ["ss"], credits=3),
    TOTAL_120,
]

BUS_EXCLUDE = ["ACCT I S", "ACT SCI", "FINANCE", "GEN BUS", "INFO SYS", "INTL BUS", "M H R", "MARKETNG", "OTM", "R M I", "REAL EST"]
BUSINESS = [
    _d("bus_comm_a", "BBA Communication A", ["comm_a"], courses=1, placement=True),
    _c("bus_micro", "BBA Microeconomics", [["ECON 101"], ["ECON 111"], ["A A E 101"]]),
    _c("bus_macro", "BBA Macroeconomics", [["ECON 102"], ["ECON 111"]]),
    _d("bus_ss", "BBA Social Science (one 3+ cr course)", ["ss"], courses=1, min_course_credits=3, exclude_subjects=BUS_EXCLUDE),
    _c("bus_calc", "BBA Calculus", [["MATH 211"], ["MATH 221"]]),
    _d("bus_lit", "BBA Literature (one 3+ cr course)", ["lit"], courses=1, min_course_credits=3),
    _d("bus_hum", "BBA Humanities (one 3+ cr course)", ["hum"], courses=1, min_course_credits=3),
    _d("bus_sci", "BBA Science (6 cr)", ["bio", "phys", "nat"], credits=6, exclude_subjects=["MATH", "STAT"]),
    _d("bus_ethnic", "BBA Ethnic Studies", ["ethnic"], courses=1, min_course_credits=3),
    _c("bus_ethics", "BBA Ethics", [["PHILOS 241"], ["PHILOS 243"], ["PHILOS 244"], ["PHILOS 341"], ["PHILOS/ENVIR ST 441"], ["L I S 461"]]),
    TOTAL_120,
]

EDUCATION = [
    _d("ed_comm_a", "Education Communication A", ["comm_a"], courses=1, placement=True),
    _d("ed_comm_b", "Education Communication B", ["comm_b"], courses=1),
    _d("ed_qr_a", "Education Quantitative Reasoning A", ["qr_a"], courses=1, placement=True),
    _d("ed_qr_b", "Education Quantitative Reasoning B", ["qr_b"], courses=1),
    _d("ed_lit", "Education Literature (2+ cr)", ["lit"], courses=1, min_course_credits=2),
    _d("ed_hum", "Education Humanities (9 cr)", ["hum", "lit", "lang"], credits=9),
    _d("ed_ss", "Education Social Studies (9 cr)", ["ss"], credits=9),
    _d("ed_phys", "Education Physical Science", ["phys"], courses=1),
    _d("ed_bio", "Education Biological Science", ["bio"], courses=1),
    _d("ed_sci", "Education Science (9 cr)", ["bio", "phys", "nat"], credits=9),
    _d("ed_ethnic", "Education Ethnic Studies", ["ethnic"], credits=3),
    _manual("ed_extra", "History / Global Perspectives / Fine Arts",
            "US or European History (3 cr), Global Perspectives (3 cr) and Fine Arts (2 cr) come from Guide lists; verify in DARS."),
    TOTAL_120,
]

HUMAN_ECOLOGY = [
    _d("he_comm_a", "SoHE Communication A", ["comm_a"], courses=1, placement=True),
    _d("he_comm_b", "SoHE Communication B", ["comm_b"], courses=1),
    _d("he_qr_a", "SoHE Quantitative Reasoning A", ["qr_a"], courses=1, placement=True),
    _d("he_qr_b", "SoHE Quantitative Reasoning B", ["qr_b"], courses=1),
    _d("he_hum", "SoHE Humanities/Literature/Arts (9 cr)", ["hum", "lit", "lang"], credits=9),
    _d("he_ss", "SoHE Social Science (9 cr)", ["ss"], credits=9),
    _d("he_nat", "SoHE Natural Science (9 cr)", ["bio", "phys", "nat"], credits=9),
    _d("he_ethnic", "SoHE Ethnic Studies", ["ethnic"], credits=3),
    _manual("he_breadth", "Human Ecology Breadth",
            "6 credits in SoHE subjects (CNSR SCI, CSCS, DS, HDFS, INTER-HE) outside the major's home department."),
    TOTAL_120,
]

NURSING = [
    _c("n_chem", "Nursing Chemistry", [["CHEM 103"], ["CHEM 108"], ["CHEM 109"]]),
    _c("n_micro", "Nursing Microbiology", [["MICROBIO 101"], ["CHEM 343"], ["NUTR SCI 332"]]),
    _c("n_anat", "Nursing Anatomy", [["ANAT&PHY 337"]]),
    _c("n_phys", "Nursing Physiology", [["ANAT&PHY 235"], ["ANAT&PHY 335"]]),
    _c("n_psych", "Nursing Psychology", [["PSYCH 202"]]),
    _c("n_hgd", "Human Growth and Development", [["HDFS 262"], ["HDFS 263"], ["ED PSYCH 320"], ["ED PSYCH 321"], ["ED PSYCH 331"], ["PSYCH 464"]]),
    _d("n_comm_a", "Communication A", ["comm_a"], courses=1, placement=True),
    _d("n_comm_b", "Communication B", ["comm_b"], courses=1),
    _d("n_qr_a", "Quantitative Reasoning A", ["qr_a"], courses=1, placement=True),
    _d("n_qr_b", "Quantitative Reasoning B", ["qr_b"], courses=1),
    _d("n_hum", "Humanities (6 cr)", ["hum", "lit", "lang"], credits=6),
    _d("n_ethnic", "Ethnic Studies", ["ethnic"], courses=1),
    TOTAL_120,
]

PHARMACY = [
    _d("p_comm_a", "Communication A", ["comm_a"], courses=1, placement=True),
    _d("p_comm_b", "Communication B", ["comm_b"], courses=1),
    _d("p_qr_a", "Quantitative Reasoning A", ["qr_a"], courses=1, placement=True),
    _d("p_qr_b", "Quantitative Reasoning B", ["qr_b"], courses=1),
    _d("p_ethnic", "Ethnic Studies", ["ethnic"], courses=1),
    _d("p_nat", "Natural Science (6 cr)", ["bio", "phys", "nat"], credits=6),
    _d("p_ss", "Social Science (3 cr)", ["ss"], credits=3),
    _d("p_hum", "Humanities (6 cr)", ["hum", "lit", "lang"], credits=6),
    TOTAL_120,
]

PROFILES = {
    "LS_BS": ("College of Letters & Science — Bachelor of Science", LS_BS),
    "LS_BA": ("College of Letters & Science — Bachelor of Arts", LS_BA),
    "LS_BM": ("College of Letters & Science — Bachelor of Music", LS_BM),
    "ENGR": ("College of Engineering common requirements", ENGINEERING),
    "CALS": ("College of Agricultural and Life Sciences", CALS),
    "BUS": ("Wisconsin School of Business — BBA", BUSINESS),
    "EDU": ("School of Education", EDUCATION),
    "SOHE": ("School of Human Ecology", HUMAN_ECOLOGY),
    "NURS": ("School of Nursing", NURSING),
    "PHARM": ("School of Pharmacy", PHARMACY),
    "GENERIC": ("University degree requirements", [TOTAL_120]),
}


def profile_for(college: str, degree: str) -> str:
    """Pick the school/college rule profile for a program."""

    college = (college or "").lower()
    degree = (degree or "").upper()
    if "letters" in college:
        if degree == "BM":
            return "LS_BM"
        if degree in {"BA", "BSW"}:
            return "LS_BA"
        if degree in {"BS", "BLA", "BS AMEP"}:
            return "LS_BS"
        return "LS_BA"
    if "engineering" in college:
        return "ENGR"
    if "agricultural" in college:
        return "CALS"
    if "business" in college:
        return "BUS"
    if "education" in college:
        return "EDU"
    if "human ecology" in college:
        return "SOHE"
    if "nursing" in college:
        return "NURS"
    if "pharmacy" in college:
        return "PHARM"
    return "GENERIC"


def gened_rules(first_term_season: str, first_term_year: int) -> list[dict]:
    """Core GenEd applies to students whose first college term is Summer 2026 or later."""

    order = {"Spring": 0, "Summer": 1, "Fall": 2}
    start = (first_term_year, order.get(first_term_season, 2))
    cutoff = (CORE_GENED_START[1], order[CORE_GENED_START[0]])
    rules = CORE_GENED if start >= cutoff else LEGACY_GENED
    return [dict(rule, scope="university") for rule in rules + UNIVERSITY_EXTRA]


def degree_rules(profile: str) -> list[dict]:
    title, rules = PROFILES.get(profile, PROFILES["GENERIC"])
    return [dict(rule, scope="college", profile=profile, profile_title=title) for rule in rules]
