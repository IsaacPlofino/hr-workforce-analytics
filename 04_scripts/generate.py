"""Generate synthetic onboarding-task and weekly-attendance RAW exports
on top of the real Kaggle HRDataset_v14 hire/termination dates.
Seeded, so re-running gives identical files."""
import numpy as np, pandas as pd, os
from openpyxl import Workbook

rng = np.random.default_rng(20160930)
AS_OF = pd.Timestamp("2016-09-30")
WIN_START = pd.Timestamp("2013-10-01")
OUT = "project_files"
os.makedirs(f"{OUT}/01_raw/onboarding", exist_ok=True)
os.makedirs(f"{OUT}/01_raw/attendance", exist_ok=True)
os.makedirs(f"{OUT}/01_raw/employees", exist_ok=True)
os.makedirs(f"{OUT}/00_reference", exist_ok=True)

emp = pd.read_csv("HRDataset_v14.csv", encoding="utf-8-sig", dtype=str)
import shutil; shutil.copy("HRDataset_v14.csv", f"{OUT}/01_raw/employees/HRDataset_v14.csv")  # untouched copy
emp["hire"] = pd.to_datetime(emp.DateofHire)
emp["term"] = pd.to_datetime(emp.DateofTermination)
emp["dept"] = emp.Department.str.strip()

# ---------------- reference: checklist template ----------------
checklist = pd.DataFrame([
    # code, name, owner, offset, phase
    ("OB01", "Offer & Contract Signed",        "HR Ops",         -14, "Pre-boarding"),
    ("OB02", "Background Check Cleared",       "HR Ops",          -7, "Pre-boarding"),
    ("OB03", "IT Equipment Ready",             "IT Helpdesk",     -1, "Pre-boarding"),
    ("OB04", "Systems Access Provisioned",     "IT Helpdesk",      0, "Day 1"),
    ("OB05", "Day-1 Orientation",              "HR Ops",           0, "Day 1"),
    ("OB06", "Team Introduction & Role Plan",  "Hiring Manager",   3, "Week 1"),
    ("OB07", "Payroll & Benefits Enrollment",  "Payroll",         14, "First 30 Days"),
    ("OB08", "Compliance Training",            "Learning & Dev",  30, "First 30 Days"),
    ("OB09", "30-Day Check-in",                "Hiring Manager",  30, "First 30 Days"),
    ("OB10", "90-Day Probation Review",        "Hiring Manager",  90, "First 90 Days"),
    ("OB11", "6-Month Performance Review",     "Hiring Manager", 180, "First 6 Months"),
], columns=["TaskCode", "TaskName", "OwnerTeam", "DueOffsetDays", "Phase"])
checklist.to_csv(f"{OUT}/00_reference/OnboardingChecklist.csv", index=False)

term_map = {
    "N/A-StillEmployed": ("", ""),
    "Another position": ("Career Move", "Voluntary"), "career change": ("Career Move", "Voluntary"),
    "more money": ("Compensation", "Voluntary"), "unhappy": ("Job Satisfaction", "Voluntary"),
    "hours": ("Work Schedule", "Voluntary"), "return to school": ("Personal / Life Event", "Voluntary"),
    "relocation out of area": ("Personal / Life Event", "Voluntary"), "military": ("Personal / Life Event", "Voluntary"),
    "maternity leave - did not return": ("Personal / Life Event", "Voluntary"),
    "medical issues": ("Personal / Life Event", "Voluntary"), "retiring": ("Retirement", "Voluntary"),
    "attendance": ("Attendance", "Involuntary"), "no-call, no-show": ("Attendance", "Involuntary"),
    "performance": ("Performance", "Involuntary"), "gross misconduct": ("Misconduct", "Involuntary"),
    "Learned that he is a gangster": ("Misconduct", "Involuntary"), "Fatal attraction": ("Misconduct", "Involuntary"),
}
pd.DataFrame([(k, v[0]) for k, v in term_map.items()],
             columns=["RawTermReason", "ReasonCategory"]).to_csv(
    f"{OUT}/00_reference/TermReasonMap.csv", index=False)

# ---------------- onboarding tasks ----------------
hires = emp[(emp.hire >= WIN_START) & (emp.hire <= AS_OF)].copy().sort_values(["hire", "EmpID"])
cohort = hires.groupby("hire").EmpID.transform("count")
hires["cohort"] = cohort

base_late = {"HR Ops": .06, "IT Helpdesk": .12, "Payroll": .08, "Learning & Dev": .15, "Hiring Manager": .14}
terms = emp[emp.term.notna()]

def mgr_recent_leavers(mgr, d):
    t = terms[(terms.ManagerName == mgr) & (terms.term <= d) & (terms.term > d - pd.Timedelta(days=90))]
    return len(t)

rows = []
tid = 1
for _, e in hires.iterrows():
    for _, c in checklist.iterrows():
        due = e.hire + pd.Timedelta(days=int(c.DueOffsetDays))
        owner = c.OwnerTeam
        assigned = e.ManagerName if owner == "Hiring Manager" else f"{owner} Team"
        p_late = base_late[owner]
        if e.cohort >= 8 and owner in ("IT Helpdesk", "HR Ops"):
            p_late += .10  # big hiring batches overload IT/HR
        p_stuck = .02
        if owner == "Hiring Manager":
            n = mgr_recent_leavers(e.ManagerName, due)
            p_late += .05 * n
            p_stuck += .08 * n  # managers backfilling leavers let check-ins slide
        p_never = {"Hiring Manager": .025, "Learning & Dev": .02}.get(owner, .008)
        r = rng.random()
        if r < p_never:
            comp = pd.Timestamp("2099-12-31")  # never actioned -> still open at snapshot
        elif r - p_never < p_stuck:
            comp = due + pd.Timedelta(days=int(rng.integers(25, 120)))
        elif r - p_never < p_stuck + p_late:
            comp = due + pd.Timedelta(days=int(min(rng.geometric(.25), 21)))
        else:
            comp = due - pd.Timedelta(days=int(rng.choice([0, 0, 0, 0, 1, 1, 2, 3, 5])))
        status, cdate = "Completed", comp
        if pd.notna(e.term) and e.term <= AS_OF and (e.term < due or comp > e.term):
            # employee left before the task was due / done -> task closed as Cancelled at offboarding
            status, cdate = "Cancelled", pd.NaT
        elif comp > AS_OF:
            cdate = pd.NaT
            status = "In Progress" if rng.random() < .45 else "Not Started"
        rows.append(dict(TaskID=f"TSK{tid:05d}", EmpID=e.EmpID, Employee=e.Employee_Name.strip(),
                         TaskName=c.TaskName, OwnerTeam=owner, AssignedTo=assigned,
                         DueDate=due, Status=status, CompletedDate=cdate))
        tid += 1

tasks = pd.DataFrame(rows)
tasks.to_pickle("truth_tasks.pkl")  # ground truth before dirt, for QA

# ---- inject dirt for the RAW export ----
dirty = tasks.copy()
def fmt_date(d):
    if pd.isna(d): return ""
    r = rng.random()
    if r < .70: return d.strftime("%Y-%m-%d")
    if r < .90: return d.strftime("%m/%d/%Y")
    return d.strftime("%d-%b-%Y")
dirty["DueDate"] = dirty.DueDate.map(fmt_date)
dirty["CompletedDate"] = dirty.CompletedDate.map(fmt_date)
status_variants = {"Completed": ["Completed", "completed", "COMPLETED", "Completed ", "Complete"],
                   "In Progress": ["In Progress", "In progress", "in-progress"],
                   "Not Started": ["Not Started", "not started", "Not started "],
                   "Cancelled": ["Cancelled", "Canceled", "cancelled"]}
dirty["Status"] = [s if rng.random() < .8 else rng.choice(status_variants[s]) for s in dirty.Status]
owner_variants = {"IT Helpdesk": ["IT HelpDesk", "IT Help Desk"], "Learning & Dev": ["L&D", "Learning and Dev"],
                  "HR Ops": ["HR Operations"], "Payroll": ["payroll"], "Hiring Manager": ["Hiring Mgr"]}
dirty["OwnerTeam"] = [o if rng.random() < .9 else rng.choice(owner_variants[o]) for o in dirty.OwnerTeam]
dirty["EmpID"] = [("E" + i) if rng.random() < .1 else i for i in dirty.EmpID]
dirty["LastModifiedBy"] = rng.choice(["svc_hris", "jdoe", "mlee", "svc_hris", "svc_hris"], len(dirty))
dirty["RowVersion"] = rng.integers(1, 9, len(dirty))
dirty["Notes"] = ""
# duplicates + blank rows
dups = dirty.sample(7, random_state=1)
dirty = pd.concat([dirty, dups]).sort_values("TaskID", kind="stable").reset_index(drop=True)
blank_at = sorted(rng.choice(len(dirty), 3, replace=False))

wb = Workbook(); ws = wb.active; ws.title = "Export"
ws.append(["Onboarding Task Export - HRIS Task Module"])
ws.append(["Generated: 30/09/2016 18:05  |  Rows are one task per new hire"])
header = ["Task ID", "Emp ID", "Employee", "task_name", "Owner Team", "Assigned To", "Due Date",
          "Status ", "Date Completed", "Last Modified By", "Row Version", "Notes"]
ws.append(header)
cols = ["TaskID", "EmpID", "Employee", "TaskName", "OwnerTeam", "AssignedTo", "DueDate", "Status",
        "CompletedDate", "LastModifiedBy", "RowVersion", "Notes"]
for i, r in dirty.iterrows():
    if i in blank_at: ws.append([None] * len(header))
    ws.append([r[c] if r[c] != "" else None for c in cols])
wb.save(f"{OUT}/01_raw/onboarding/OnboardingTasks_Export_20160930.xlsx")

# ---------------- weekly attendance (wide, one file per FY) ----------------
att_names = {"Production": "Production", "IT/IS": "IT / IS", "Sales": "Sales",
             "Software Engineering": "Software Eng.", "Admin Offices": "Admin Offices",
             "Executive Office": "Exec Office"}
p_missing = {"Production": .05, "IT/IS": .03, "Sales": .06, "Software Engineering": .04,
             "Admin Offices": .02, "Executive Office": .02}
p_late = {"Production": .12, "IT/IS": .08, "Sales": .15, "Software Engineering": .08,
          "Admin Offices": .05, "Executive Office": .04}
att_truth = []
for fy in (2014, 2015, 2016):
    start = pd.Timestamp(f"{fy-1}-10-01"); end = pd.Timestamp(f"{fy}-09-30")
    weeks = pd.date_range(start, end, freq="W-FRI")
    wb = Workbook(); ws = wb.active; ws.title = "Submissions"
    ws.append([f"Weekly Attendance Submission Log - FY{fy} (Oct {fy-1} - Sep {fy})"])
    ws.append(["Dept"] + [f"WE {w.strftime('%d-%b-%y')}" for w in weeks])
    for dept, label in att_names.items():
        row = [label]
        for w in weeks:
            due = w + pd.Timedelta(days=3)  # due the Monday after week-ending Friday
            pm, pl = p_missing[dept], p_late[dept]
            if dept == "Production" and fy == 2016:
                pm, pl = .14, .25  # supervisors stretched during the FY2016 attrition spike
            r = rng.random()
            if r < pm:
                sub = pd.NaT
            elif r < pm + pl:
                sub = due + pd.Timedelta(days=int(rng.integers(1, 6)))
            else:
                sub = due - pd.Timedelta(days=int(rng.choice([0, 0, 1, 2, 3])))
            if pd.notna(sub) and sub > AS_OF:
                sub = pd.NaT  # not submitted yet as of the snapshot date
            att_truth.append(dict(Department=dept, WeekEnding=w, DueDate=due, SubmittedDate=sub))
            row.append(None if pd.isna(sub) else sub.strftime("%m/%d/%Y"))
        ws.append(row)
    wb.save(f"{OUT}/01_raw/attendance/Attendance_FY{fy}.xlsx")
pd.DataFrame(att_truth).to_pickle("truth_att.pkl")

t = tasks
print("tasks", len(t), t.Status.value_counts().to_dict())
op = t[t.Status.isin(["In Progress", "Not Started"])]
print("open", len(op), "overdue", (op.DueDate < AS_OF).sum())
print(op[op.DueDate < AS_OF][["Employee", "TaskName", "OwnerTeam", "DueDate"]])
c = t[t.Status == "Completed"]
print("late completions", (c.CompletedDate > c.DueDate).sum(), "of", len(c))
