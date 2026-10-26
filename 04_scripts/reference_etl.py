"""Reference ETL + QA answer key.
Parses the RAW files the same way the Power Automate Desktop flow should, writes the
expected clean outputs, checks them against generator ground truth, and computes every
dashboard number independently of Power BI."""
import pandas as pd, numpy as np, re, os
AS_OF = pd.Timestamp("2016-09-30")
P = "project_files"
os.makedirs(f"{P}/02_clean_expected", exist_ok=True)
os.makedirs(f"{P}/03_qa", exist_ok=True)
log = []

# ---------- Employees ----------
raw = pd.read_csv(f"{P}/01_raw/employees/HRDataset_v14.csv", encoding="utf-8-sig", dtype=str)
log.append(("Employees", "raw rows", len(raw)))
emp = pd.DataFrame({
    "EmpID": raw.EmpID.str.strip(),
    "EmployeeName": raw.Employee_Name.str.replace(r"\s+", " ", regex=True).str.replace(r",\s*", ", ", regex=True).str.strip(),
    "Department": raw.Department.str.strip(),
    "Position": raw.Position.str.strip(),
    "ManagerName": raw.ManagerName.str.strip(),
    "HireDate": pd.to_datetime(raw.DateofHire, format="%m/%d/%Y"),
    "TerminationDate": pd.to_datetime(raw.DateofTermination, format="%m/%d/%Y"),
    "TermReason": raw.TermReason.str.strip(),
    "EmploymentStatus": raw.EmploymentStatus.str.strip(),
    "RecruitmentSource": raw.RecruitmentSource.str.strip(),
    "PerformanceScore": raw.PerformanceScore.str.strip(),
})
log.append(("Employees", "clean rows", len(emp)))
emp.to_csv(f"{P}/02_clean_expected/Employees_Clean.csv", index=False, date_format="%Y-%m-%d")
tmap = pd.read_csv(f"{P}/00_reference/TermReasonMap.csv").fillna("")
emp = emp.merge(tmap, left_on="TermReason", right_on="RawTermReason", how="left")
assert emp.ReasonCategory.notna().all()
# separation type comes from the HRIS status field (authoritative), not from the free-text reason
emp["ReasonGroup"] = emp.EmploymentStatus.map({"Voluntarily Terminated": "Voluntary", "Terminated for Cause": "Involuntary", "Active": ""})

# as-of snapshot logic
e = emp[emp.HireDate <= AS_OF].copy()
e.loc[e.TerminationDate > AS_OF, ["TerminationDate"]] = pd.NaT
e.loc[e.TerminationDate.isna(), ["ReasonCategory", "ReasonGroup"]] = ""
log.append(("Employees", "in scope as of 2016-09-30 (hired on/before)", len(e)))

def fy(d): return d.dt.year + (d.dt.month >= 10)
def fy_bounds(y): return pd.Timestamp(f"{y-1}-10-01"), pd.Timestamp(f"{y}-09-30")
def hc(d): return int(((e.HireDate <= d) & (e.TerminationDate.isna() | (e.TerminationDate > d))).sum())

wf = []
for y in (2014, 2015, 2016):
    s, t = fy_bounds(y)
    hs, he = hc(s - pd.Timedelta(days=1)), hc(t)
    hires = int(e.HireDate.between(s, t).sum())
    lv = e[e.TerminationDate.between(s, t)]
    avg = (hs + he) / 2
    wf.append(dict(FiscalYear=f"FY{y}", HeadcountStart=hs, Hires=hires, Leavers=len(lv),
                   Voluntary=int((lv.ReasonGroup == "Voluntary").sum()),
                   Involuntary=int((lv.ReasonGroup == "Involuntary").sum()),
                   HeadcountEnd=he, BridgeCheck_OK=(hs + hires - len(lv) == he),
                   AvgHeadcount=avg, AttritionRate=round(len(lv) / avg, 4)))
wf = pd.DataFrame(wf)
for i in range(1, 3):
    wf.loc[i, "Headcount_YoY_pct"] = round(wf.HeadcountEnd[i] / wf.HeadcountEnd[i-1] - 1, 4)
    wf.loc[i, "Leavers_YoY_pct"] = round(wf.Leavers[i] / wf.Leavers[i-1] - 1, 4)

dept = []
for y in (2014, 2015, 2016):
    s, t = fy_bounds(y)
    for d, g in e.groupby("Department"):
        hs = int(((g.HireDate < s) & (g.TerminationDate.isna() | (g.TerminationDate >= s))).sum())
        he = int(((g.HireDate <= t) & (g.TerminationDate.isna() | (g.TerminationDate > t))).sum())
        lv = int(g.TerminationDate.between(s, t).sum()); hi = int(g.HireDate.between(s, t).sum())
        avg = (hs + he) / 2
        dept.append(dict(FiscalYear=f"FY{y}", Department=d, HeadcountStart=hs, Hires=hi, Leavers=lv,
                         HeadcountEnd=he, NetChange=hi - lv, AttritionRate=round(lv / avg, 4) if avg else None))
dept = pd.DataFrame(dept)

months = pd.period_range("2013-10", "2016-09", freq="M")
mon = pd.DataFrame({"Month": months.astype(str),
                    "Hires": [int((e.HireDate.dt.to_period("M") == m).sum()) for m in months],
                    "Leavers": [int((e.TerminationDate.dt.to_period("M") == m).sum()) for m in months]})
mon["FiscalYear"] = ["FY%d" % (p.year + (p.month >= 10)) for p in months]
mon["FiscalMonthNo"] = [(p.month + 2) % 12 + 1 for p in months]

reasons = e[e.TerminationDate.between(pd.Timestamp("2013-10-01"), AS_OF)].assign(
    FiscalYear=lambda x: "FY" + fy(x.TerminationDate).astype(str)).pivot_table(
    index=["ReasonGroup", "ReasonCategory"], columns="FiscalYear", values="EmpID", aggfunc="count", fill_value=0).reset_index()

# ---------- Onboarding ----------
ob = pd.read_excel(f"{P}/01_raw/onboarding/OnboardingTasks_Export_20160930.xlsx", header=2, dtype=str)
log.append(("OnboardingTasks", "raw data rows (after skipping 2 title rows)", len(ob)))
ob = ob.dropna(how="all"); log.append(("OnboardingTasks", "after removing blank rows", len(ob)))
ob = ob.drop(columns=["Employee", "Last Modified By", "Row Version", "Notes"])
ob.columns = ["TaskID", "EmpID", "TaskName", "OwnerTeam", "AssignedTo", "DueDate", "Status", "CompletedDate"]
ob = ob.drop_duplicates(); log.append(("OnboardingTasks", "after removing exact duplicates", len(ob)))
ob["EmpID"] = ob.EmpID.str.replace("E", "", regex=False).str.strip()
def pdate(x):
    if pd.isna(x) or str(x).strip() == "": return pd.NaT
    x = str(x).strip()[:10] if re.match(r"\d{4}-\d{2}-\d{2}", str(x)) else str(x).strip()
    if "/" in x: return pd.to_datetime(x, format="%m/%d/%Y")
    if re.search("[A-Za-z]", x): return pd.to_datetime(x, format="%d-%b-%Y")
    return pd.to_datetime(x, format="%Y-%m-%d")
ob["DueDate"] = ob.DueDate.map(pdate); ob["CompletedDate"] = ob.CompletedDate.map(pdate)
vm = pd.read_csv(f"{P}/00_reference/ValueMap.csv")
def vmap(series, field):
    m = vm[vm.Field == field].set_index("RawValueNormalized").CleanValue
    norm = series.str.strip().str.lower().str.replace("-", " ", regex=False)
    out = norm.map(m)
    assert out.notna().all(), (field, sorted(norm[out.isna()].unique()))
    return out
ob["Status"] = vmap(ob.Status, "Status")
ob["OwnerTeam"] = vmap(ob.OwnerTeam, "OwnerTeam")
assert ob.Status.notna().all()
ob = ob.sort_values("TaskID").reset_index(drop=True)
ob.to_csv(f"{P}/02_clean_expected/OnboardingTasks_Clean.csv", index=False, date_format="%Y-%m-%d")

truth = pd.read_pickle("truth_tasks.pkl").drop(columns="Employee").sort_values("TaskID").reset_index(drop=True)
chk = ob.copy(); chk.equals(truth)
for c in truth.columns:
    a, b = chk[c], truth[c]
    same = ((a == b) | (a.isna() & b.isna())).all()
    assert same, c
log.append(("OnboardingTasks", "clean output matches generator ground truth", "YES"))

def bucket(r):
    if r.Status == "Cancelled": return "Cancelled"
    if r.Status == "Completed": return "Completed On Time" if r.CompletedDate <= r.DueDate else "Completed Late"
    return "Open - Overdue" if r.DueDate < AS_OF else "Open - Not Yet Due"
ob["Bucket"] = ob.apply(bucket, axis=1)
ob = ob.merge(emp[["EmpID", "EmployeeName", "Department", "HireDate", "TerminationDate"]], on="EmpID", how="left")
assert ob.Department.notna().all()
order = ["Completed On Time", "Completed Late", "Open - Overdue", "Open - Not Yet Due", "Cancelled"]
bc = ob.Bucket.value_counts().reindex(order).fillna(0).astype(int)
accountable = bc["Completed On Time"] + bc["Completed Late"] + bc["Open - Overdue"]
kpi = [
    ("As-of date", "2016-09-30"),
    ("WORKFORCE", ""),
    ("Headcount (active on as-of date)", hc(AS_OF)),
    ("FY2016 Hires", int(wf.Hires[2])), ("FY2016 Leavers", int(wf.Leavers[2])),
    ("FY2016 Net change", int(wf.Hires[2] - wf.Leavers[2])),
    ("FY2016 Attrition rate (Leavers / avg headcount)", float(wf.AttritionRate[2])),
    ("FY2016 Voluntary leavers", int(wf.Voluntary[2])),
    ("ONBOARDING (all tasks in tracker, FY2014-FY2016 hires)", ""),
    ("Total tasks", len(ob)),
] + [(f"  {k}", int(v)) for k, v in bc.items()] + [
    ("  -> check: buckets sum to total", int(bc.sum()) == len(ob)),
    ("Completed (on time + late)", int(bc["Completed On Time"] + bc["Completed Late"])),
    ("Open (overdue + not yet due)", int(bc["Open - Overdue"] + bc["Open - Not Yet Due"])),
    ("Accountable tasks (completed + open overdue)", int(accountable)),
    ("On-Time Rate  = Completed On Time / Accountable", round(bc["Completed On Time"] / accountable, 4)),
    ("Late Rate     = Completed Late / Accountable", round(bc["Completed Late"] / accountable, 4)),
    ("Overdue Rate  = Open - Overdue / Accountable", round(bc["Open - Overdue"] / accountable, 4)),
    ("  -> check: three rates sum to 100%", round((bc["Completed On Time"] + bc["Completed Late"] + bc["Open - Overdue"]) / accountable, 4)),
    ("Open tasks due in next 30 days (Oct 1 - Oct 30, 2016)", int(((ob.Bucket == "Open - Not Yet Due") & (ob.DueDate <= AS_OF + pd.Timedelta(days=30))).sum())),
]

ob["DueFY"] = "FY" + fy(ob.DueDate).astype(str)
due_fy = ob.pivot_table(index="DueFY", columns="Bucket", values="TaskID", aggfunc="count", fill_value=0).reindex(columns=order, fill_value=0)
due_fy["TotalTasks"] = due_fy.sum(axis=1)
_acc = due_fy["Completed On Time"] + due_fy["Completed Late"] + due_fy["Open - Overdue"]
due_fy["Accountable"] = _acc
due_fy["OnTimeRate"] = (due_fy["Completed On Time"] / _acc).round(4)
due_fy["LateRate"] = (due_fy["Completed Late"] / _acc).round(4)
due_fy["OverdueRate"] = (due_fy["Open - Overdue"] / _acc).round(4)
due_fy = due_fy.reset_index()
owner_fy = ob.assign(OnTime=ob.Bucket.eq("Completed On Time"), Acc=ob.Bucket.isin(["Completed On Time", "Completed Late", "Open - Overdue"]))
owner_fy = owner_fy[owner_fy.Acc].pivot_table(index="OwnerTeam", columns="DueFY", values="OnTime", aggfunc="mean").round(4).reset_index()
# employee onboarding status (one status per employee, mutually exclusive)
eo = ob.groupby("EmpID").Bucket.agg(list).reset_index().merge(e[["EmpID", "EmployeeName", "Department", "HireDate", "TerminationDate"]], on="EmpID")
def estatus(r):
    if pd.notna(r.TerminationDate): return "Left Company"
    if "Open - Overdue" in r.Bucket: return "In Progress - Has Overdue"
    if "Open - Not Yet Due" in r.Bucket: return "In Progress - On Track"
    return "Onboarding Complete"
eo["OnboardingStatus"] = eo.apply(estatus, axis=1)
emp_status = eo.OnboardingStatus.value_counts().rename_axis("OnboardingStatus").reset_index(name="Employees")
owner = ob.pivot_table(index="OwnerTeam", columns="Bucket", values="TaskID", aggfunc="count", fill_value=0).reindex(columns=order, fill_value=0).reset_index()
owner["OnTimeRate"] = (owner["Completed On Time"] / (owner["Completed On Time"] + owner["Completed Late"] + owner["Open - Overdue"])).round(4)
queue = ob[ob.Bucket == "Open - Overdue"].sort_values("DueDate")[["TaskID", "EmployeeName", "Department", "TaskName", "OwnerTeam", "AssignedTo", "DueDate", "Status"]]

# new-hire cohort retention (only cohorts with a full 12 months elapsed)
coh = e[(e.HireDate >= pd.Timestamp("2013-10-01")) & (e.HireDate <= AS_OF - pd.Timedelta(days=365))].copy()
coh["LeftWithin12m"] = coh.TerminationDate.notna() & ((coh.TerminationDate - coh.HireDate).dt.days < 365)
coh["HireFY"] = "FY" + fy(coh.HireDate).astype(str)
cr = coh.groupby("HireFY").agg(Hires=("EmpID", "count"), LeftWithin12m=("LeftWithin12m", "sum")).reset_index()
cr["FirstYearAttrition"] = (cr.LeftWithin12m / cr.Hires).round(4)
ob_emp = ob[ob.Bucket.isin(["Completed On Time", "Completed Late", "Open - Overdue"])].groupby("EmpID").Bucket.apply(
    lambda s: (s == "Completed On Time").mean()).rename("EmpOnTimeRate").reset_index()
link = coh.merge(ob_emp, on="EmpID", how="left")
link["Group"] = np.where(link.LeftWithin12m, "Left within 12 months", "Stayed 12+ months")
link_s = link.groupby("Group").agg(Employees=("EmpID", "count"), AvgOnboardingOnTimeRate=("EmpOnTimeRate", "mean")).round(4).reset_index()

# ---------- Attendance ----------
long = []
for y in (2014, 2015, 2016):
    a = pd.read_excel(f"{P}/01_raw/attendance/Attendance_FY{y}.xlsx", header=1, dtype=str)
    log.append((f"Attendance FY{y}", "raw wide shape (depts x columns)", f"{a.shape[0]} x {a.shape[1]}"))
    m = a.melt(id_vars="Dept", var_name="WeekHeader", value_name="SubmittedDate")
    long.append(m)
att = pd.concat(long)
log.append(("Attendance", "rows after unpivot + combine 3 files", len(att)))
att["Department"] = vmap(att.Dept, "Department")
att["WeekEnding"] = pd.to_datetime(att.WeekHeader.str.replace("WE ", "", regex=False), format="%d-%b-%y")
att["SubmittedDate"] = pd.to_datetime(att.SubmittedDate, format="%m/%d/%Y")
att = att[["Department", "WeekEnding", "SubmittedDate"]].sort_values(["WeekEnding", "Department"])
att.to_csv(f"{P}/02_clean_expected/AttendanceSubmissions_Clean.csv", index=False, date_format="%Y-%m-%d")
att["DueDate"] = att.WeekEnding + pd.Timedelta(days=3)
att["SubStatus"] = np.select([att.DueDate > AS_OF, att.SubmittedDate.isna(), att.SubmittedDate <= att.DueDate],
                             ["Not Yet Due", "Missing", "On Time"], "Late")
att["FiscalYear"] = "FY" + fy(att.WeekEnding).astype(str)
ad = att[att.SubStatus != "Not Yet Due"].pivot_table(index=["FiscalYear", "Department"], columns="SubStatus",
                                                     values="WeekEnding", aggfunc="count", fill_value=0).reset_index()
ad["ExpectedWeeks"] = ad[["Late", "Missing", "On Time"]].sum(axis=1)
ad["OnTimeSubmissionRate"] = (ad["On Time"] / ad.ExpectedWeeks).round(4)
ad["SubmittedAnyRate"] = ((ad["On Time"] + ad["Late"]) / ad.ExpectedWeeks).round(4)
kpi += [("ATTENDANCE (weekly submissions, due Monday after week-ending Friday)", ""),
        ("Department-weeks expected (excl. not-yet-due)", int(ad.ExpectedWeeks.sum())),
        ("Not-yet-due department-weeks excluded", int((att.SubStatus == "Not Yet Due").sum())),
        ("FY2016 on-time submission rate (all depts)", round(ad[ad.FiscalYear == "FY2016"]["On Time"].sum() / ad[ad.FiscalYear == "FY2016"].ExpectedWeeks.sum(), 4)),
        ("FY2016 missing submissions (all depts)", int(ad[ad.FiscalYear == "FY2016"].Missing.sum()))]

with pd.ExcelWriter(f"{P}/03_qa/QA_Answer_Key.xlsx", engine="openpyxl") as w:
    pd.DataFrame([
        ["What this is", "Expected values computed in Python straight from the raw files, independent of Power BI. Every card/visual in the report must match these. If it does not, the DAX or ETL is wrong."],
        ["As-of date", "2016-09-30 (end of FY2016). Terminations after this date are treated as still active; hires after it are excluded."],
        ["Fiscal year", "Oct 1 - Sep 30, named by the year it ends (FY2016 = Oct 1 2015 - Sep 30 2016)."],
        ["Headcount", "Employees with HireDate <= date AND (no TerminationDate OR TerminationDate > date)."],
        ["Headcount start of FY", "Headcount at end of Sep 30 of the prior FY."],
        ["Bridge check", "HeadcountStart + Hires - Leavers must equal HeadcountEnd."],
        ["Attrition rate", "Leavers in period / ((HeadcountStart + HeadcountEnd) / 2)."],
        ["Task buckets", "Completed On Time | Completed Late | Open - Overdue | Open - Not Yet Due | Cancelled. Mutually exclusive, always sum to Total Tasks."],
        ["Accountable tasks", "Completed + Open - Overdue (tasks that are done or should be done). Denominator for On-Time / Late / Overdue rates, which therefore sum to 100%."],
        ["First-year attrition", "Only hire cohorts with 12 full months elapsed (hired on/before 2015-09-30)."],
    ], columns=["Item", "Definition"]).to_excel(w, sheet_name="README", index=False)
    pd.DataFrame(kpi, columns=["KPI", "Expected value"]).to_excel(w, sheet_name="KPI_Cards", index=False)
    wf.to_excel(w, sheet_name="Workforce_by_FY", index=False)
    dept.to_excel(w, sheet_name="Workforce_by_Dept_FY", index=False)
    mon.to_excel(w, sheet_name="Monthly_Hires_Leavers", index=False)
    reasons.to_excel(w, sheet_name="Leaver_Reasons_by_FY", index=False)
    owner.to_excel(w, sheet_name="Onboarding_by_Owner", index=False)
    due_fy.to_excel(w, sheet_name="Onboarding_by_DueFY", index=False)
    queue.to_excel(w, sheet_name="Overdue_Action_Queue", index=False)
    owner_fy.to_excel(w, sheet_name="OnTimeRate_Owner_by_DueFY", index=False)
    emp_status.to_excel(w, sheet_name="Employee_Onboarding_Status", index=False)
    cr.to_excel(w, sheet_name="NewHire_Cohort_Retention", index=False)
    link_s.to_excel(w, sheet_name="Onboarding_vs_Attrition", index=False)
    ad.to_excel(w, sheet_name="Attendance_by_FY_Dept", index=False)
    pd.DataFrame(log, columns=["Table", "Step", "Rows / result"]).to_excel(w, sheet_name="ETL_Row_Counts", index=False)

pd.set_option("display.width", 200)
for x in (due_fy, owner_fy, emp_status): print(x.to_string(), "\n")
print(dept[dept.FiscalYear == "FY2016"].to_string())
print(ad[ad.FiscalYear == "FY2016"].to_string())
print(reasons.to_string())
