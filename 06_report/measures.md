# DAX measures

All measures used in the HR Workforce & Onboarding Dashboard.

```dax
DEFINE
    MEASURE '_Measures'[As Of Date] = MAX ( Settings[AsOfDate] )
    MEASURE '_Measures'[Headcount End] = VAR PStart = MIN ( DimDate[Date] )
VAR PeriodEnd = MIN ( MAX ( DimDate[Date] ), [As Of Date] )
RETURN
    IF ( ISBLANK ( PStart ) || PStart > [As Of Date], BLANK (),
        CALCULATE ( COUNTROWS ( Employees ),
            Employees[HireDate] <= PeriodEnd,
            ISBLANK ( Employees[TerminationDate] ) || Employees[TerminationDate] > PeriodEnd ) )
    MEASURE '_Measures'[Headcount Start] = VAR PStart = MIN ( DimDate[Date] )
VAR DayBefore = PStart - 1
RETURN
    IF ( ISBLANK ( PStart ) || DayBefore >= [As Of Date], BLANK (),
        CALCULATE ( COUNTROWS ( Employees ),
            Employees[HireDate] <= DayBefore,
            ISBLANK ( Employees[TerminationDate] ) || Employees[TerminationDate] > DayBefore ) )
    MEASURE '_Measures'[Hires] = VAR PStart = MIN ( DimDate[Date] )
VAR PEnd   = MAX ( DimDate[Date] )
RETURN
    IF ( ISBLANK ( PStart ), BLANK (),
        COALESCE ( CALCULATE ( COUNTROWS ( Employees ),
            Employees[HireDate] >= PStart, Employees[HireDate] <= PEnd ), 0 ) )
    MEASURE '_Measures'[Leavers] = VAR PStart = MIN ( DimDate[Date] )
VAR PEnd   = MAX ( DimDate[Date] )
RETURN
    IF ( ISBLANK ( PStart ), BLANK (),
        COALESCE ( CALCULATE ( COUNTROWS ( Employees ),
            NOT ISBLANK ( Employees[TerminationDate] ),
            Employees[TerminationDate] >= PStart, Employees[TerminationDate] <= PEnd ), 0 ) )
    MEASURE '_Measures'[Voluntary Leavers] = CALCULATE ( [Leavers], Employees[SeparationType] = "Voluntary" )
    MEASURE '_Measures'[Involuntary Leavers] = CALCULATE ( [Leavers], Employees[SeparationType] = "Involuntary" )
    MEASURE '_Measures'[Net Change] = [Hires] - [Leavers]
    MEASURE '_Measures'[Avg Headcount] = DIVIDE ( [Headcount Start] + [Headcount End], 2 )
    MEASURE '_Measures'[Attrition Rate] = DIVIDE ( [Leavers], [Avg Headcount] )
    MEASURE '_Measures'[Leavers PY] = CALCULATE ( [Leavers], DATEADD ( DimDate[Date], -1, YEAR ) )
    MEASURE '_Measures'[Headcount End PY] = CALCULATE ( [Headcount End], DATEADD ( DimDate[Date], -1, YEAR ) )
    MEASURE '_Measures'[Attrition Rate PY] = CALCULATE ( [Attrition Rate], DATEADD ( DimDate[Date], -1, YEAR ) )
    MEASURE '_Measures'[Leavers YoY %] = DIVIDE ( [Leavers] - [Leavers PY], [Leavers PY] )
    MEASURE '_Measures'[Headcount YoY %] = DIVIDE ( [Headcount End] - [Headcount End PY], [Headcount End PY] )
    MEASURE '_Measures'[First-Year Attrition Rate] = VAR PStart = MIN ( DimDate[Date] )
VAR Cutoff = MIN ( MAX ( DimDate[Date] ), [As Of Date] - 365 )
VAR Cohort =
    CALCULATETABLE ( Employees,
        Employees[HireDate] >= PStart, Employees[HireDate] <= Cutoff )
VAR CohortSize = COUNTROWS ( Cohort )
VAR LeftEarly =
    COALESCE ( COUNTROWS ( FILTER ( Cohort,
        NOT ISBLANK ( Employees[TerminationDate] )
            && Employees[TerminationDate] - Employees[HireDate] < 365 ) ), 0 )
RETURN
    IF ( CohortSize > 0, DIVIDE ( LeftEarly, CohortSize ) )
    MEASURE '_Measures'[Total Tasks] = COUNTROWS ( OnboardingTasks )
    MEASURE '_Measures'[Tasks Completed On Time] = COALESCE ( CALCULATE ( [Total Tasks], OnboardingTasks[TaskOutcome] = "Completed On Time" ), 0 )
    MEASURE '_Measures'[Tasks Completed Late] = COALESCE ( CALCULATE ( [Total Tasks], OnboardingTasks[TaskOutcome] = "Completed Late" ), 0 )
    MEASURE '_Measures'[Tasks Open Overdue] = COALESCE ( CALCULATE ( [Total Tasks], OnboardingTasks[TaskOutcome] = "Open - Overdue" ), 0 )
    MEASURE '_Measures'[Tasks Open Not Yet Due] = COALESCE ( CALCULATE ( [Total Tasks], OnboardingTasks[TaskOutcome] = "Open - Not Yet Due" ), 0 )
    MEASURE '_Measures'[Tasks Cancelled] = COALESCE ( CALCULATE ( [Total Tasks], OnboardingTasks[TaskOutcome] = "Cancelled" ), 0 )
    MEASURE '_Measures'[Completed Tasks] = [Tasks Completed On Time] + [Tasks Completed Late]
    MEASURE '_Measures'[Open Tasks] = [Tasks Open Overdue] + [Tasks Open Not Yet Due]
    MEASURE '_Measures'[Accountable Tasks] = [Completed Tasks] + [Tasks Open Overdue]
    MEASURE '_Measures'[On-Time Rate] = DIVIDE ( [Tasks Completed On Time], [Accountable Tasks] )
    MEASURE '_Measures'[Late Rate] = DIVIDE ( [Tasks Completed Late], [Accountable Tasks] )
    MEASURE '_Measures'[Overdue Rate] = DIVIDE ( [Tasks Open Overdue], [Accountable Tasks] )
    MEASURE '_Measures'[Overdue Now] = CALCULATE ( [Tasks Open Overdue], REMOVEFILTERS ( DimDate ) )
    MEASURE '_Measures'[Tasks Due Next 30 Days] = VAR d = [As Of Date]
        RETURN CALCULATE ( [Tasks Open Not Yet Due], REMOVEFILTERS ( DimDate ), OnboardingTasks[DueDate] <= d + 30 )
    MEASURE '_Measures'[Employee Onboarding Status] = IF ( HASONEVALUE ( Employees[EmpID] ),
            VAR HasTasks = CALCULATE ( [Total Tasks], REMOVEFILTERS ( DimDate ) ) > 0
            RETURN SWITCH ( TRUE (),
                NOT HasTasks, BLANK (),                                  -- hired before the tracker went live
                NOT ISBLANK ( SELECTEDVALUE ( Employees[TerminationDate] ) ), "Left Company",
                CALCULATE ( [Tasks Open Overdue], REMOVEFILTERS ( DimDate ) ) > 0, "In Progress - Has Overdue",
                CALCULATE ( [Tasks Open Not Yet Due], REMOVEFILTERS ( DimDate ) ) > 0, "In Progress - On Track",
                "Onboarding Complete" ) )
    MEASURE '_Measures'[Completed Tasks by Completion Month] = CALCULATE ( [Completed Tasks], USERELATIONSHIP ( DimDate[Date], OnboardingTasks[CompletedDate] ) )
    MEASURE '_Measures'[Expected Submissions] = CALCULATE ( COUNTROWS ( Attendance ), Attendance[SubmissionStatus] <> "Not Yet Due" )
    MEASURE '_Measures'[On-Time Submissions] = COALESCE ( CALCULATE ( COUNTROWS ( Attendance ), Attendance[SubmissionStatus] = "On Time" ), 0 )
    MEASURE '_Measures'[Late Submissions] = COALESCE ( CALCULATE ( COUNTROWS ( Attendance ), Attendance[SubmissionStatus] = "Late" ), 0 )
    MEASURE '_Measures'[Missing Submissions] = COALESCE ( CALCULATE ( COUNTROWS ( Attendance ), Attendance[SubmissionStatus] = "Missing" ), 0 )
    MEASURE '_Measures'[On-Time Submission Rate] = DIVIDE ( [On-Time Submissions], [Expected Submissions] )
    MEASURE '_Measures'[Weeks All Departments On Time] = COUNTROWS ( FILTER ( VALUES ( Attendance[WeekEnding] ),
            CALCULATE ( [Expected Submissions] ) > 0
                && CALCULATE ( [On-Time Submissions] ) = CALCULATE ( [Expected Submissions] ) ) )
    MEASURE '_Measures'[Selected FY] = SELECTEDVALUE ( DimDate[Fiscal Year], "all years" )
    MEASURE '_Measures'[Headcount Bridge Text] = "Started " & [Selected FY] & " at " & [Headcount Start] & " · +" & [Hires] & " hired · −"
            & [Leavers] & " left · ended at " & [Headcount End]
    MEASURE '_Measures'[Attrition Subtitle] = [Leavers] & " leavers ÷ " & FORMAT ( [Avg Headcount], "0.0" ) & " average headcount"
    MEASURE '_Measures'[On-Time Subtitle] = FORMAT ( [Tasks Completed On Time], "#,0" ) & " of " & FORMAT ( [Accountable Tasks], "#,0" )
            & " tasks due in " & [Selected FY] & " were done on time"
    MEASURE '_Measures'[Top Leaver Department] = VAR t = TOPN ( 1, VALUES ( Departments[Department] ), [Leavers] )
        RETURN CONCATENATEX ( t,
            Departments[Department] & " (" & [Leavers] & " of " & CALCULATE ( [Leavers], ALL ( Departments ) ) & " leavers)",
            ", " )
    MEASURE '_Measures'[As Of Label] = "Data as of " & FORMAT ( [As Of Date], "d mmm yyyy" ) & " (fixed for this portfolio project)"
    MEASURE '_Measures'[Check Headcount Bridge] = [Headcount Start] + [Hires] - [Leavers] - [Headcount End]
    MEASURE '_Measures'[Check Task Outcomes] = [Tasks Completed On Time] + [Tasks Completed Late] + [Tasks Open Overdue]
            + [Tasks Open Not Yet Due] + [Tasks Cancelled] - [Total Tasks]
    MEASURE '_Measures'[Check Rates Sum] = IF ( [Accountable Tasks] > 0, ROUND ( [On-Time Rate] + [Late Rate] + [Overdue Rate] - 1, 6 ) )
    MEASURE '_Measures'[Check Attendance] = [On-Time Submissions] + [Late Submissions] + [Missing Submissions] - [Expected Submissions]
    MEASURE '_Measures'[Bridge Value] = SWITCH ( SELECTEDVALUE ( BridgeSteps[Step] ),
    "Start", [Headcount Start],
    "Hired", [Hires],
    "Left", - [Leavers] )
    MEASURE '_Measures'[Week Status Color] = SWITCH ( [Week Status],
    "On Time", "#FFFFFF",
    "Late", "#9C9CC0",
    "Missing", "#F0405E",
    "#E1E1EA" )
    MEASURE '_Measures'[Week Status] = SELECTEDVALUE ( Attendance[SubmissionStatus] )
    MEASURE '_Measures'[Attrition PY Text] = "Last year: " & FORMAT ( [Attrition Rate PY], "0.0%" )
    MEASURE '_Measures'[Leavers Split Text] = [Voluntary Leavers] & " voluntary · " & [Involuntary Leavers] & " involuntary"
    MEASURE '_Measures'[Leavers (chart)] = IF ( [Leavers] > 0, [Leavers] )
    MEASURE '_Measures'[Attrition Target] = 0.20
    MEASURE '_Measures'[Attrition Colour] = IF ( [Attrition Rate] >= [Attrition Target], "#FF4F69" )
    MEASURE '_Measures'[Days Overdue] = DATEDIFF ( MAX ( OnboardingTasks[DueDate] ), [As Of Date], DAY )

EVALUATE
    SUMMARIZECOLUMNS(
        "As Of Date", [As Of Date],
        "Headcount End", [Headcount End],
        "Headcount Start", [Headcount Start],
        "Hires", [Hires],
        "Leavers", [Leavers],
        "Voluntary Leavers", [Voluntary Leavers],
        "Involuntary Leavers", [Involuntary Leavers],
        "Net Change", [Net Change],
        "Avg Headcount", [Avg Headcount],
        "Attrition Rate", [Attrition Rate],
        "Leavers PY", [Leavers PY],
        "Headcount End PY", [Headcount End PY],
        "Attrition Rate PY", [Attrition Rate PY],
        "Leavers YoY %", [Leavers YoY %],
        "Headcount YoY %", [Headcount YoY %],
        "First-Year Attrition Rate", [First-Year Attrition Rate],
        "Total Tasks", [Total Tasks],
        "Tasks Completed On Time", [Tasks Completed On Time],
        "Tasks Completed Late", [Tasks Completed Late],
        "Tasks Open Overdue", [Tasks Open Overdue],
        "Tasks Open Not Yet Due", [Tasks Open Not Yet Due],
        "Tasks Cancelled", [Tasks Cancelled],
        "Completed Tasks", [Completed Tasks],
        "Open Tasks", [Open Tasks],
        "Accountable Tasks", [Accountable Tasks],
        "On-Time Rate", [On-Time Rate],
        "Late Rate", [Late Rate],
        "Overdue Rate", [Overdue Rate],
        "Overdue Now", [Overdue Now],
        "Tasks Due Next 30 Days", [Tasks Due Next 30 Days],
        "Employee Onboarding Status", [Employee Onboarding Status],
        "Completed Tasks by Completion Month", [Completed Tasks by Completion Month],
        "Expected Submissions", [Expected Submissions],
        "On-Time Submissions", [On-Time Submissions],
        "Late Submissions", [Late Submissions],
        "Missing Submissions", [Missing Submissions],
        "On-Time Submission Rate", [On-Time Submission Rate],
        "Weeks All Departments On Time", [Weeks All Departments On Time],
        "Selected FY", [Selected FY],
        "Headcount Bridge Text", [Headcount Bridge Text],
        "Attrition Subtitle", [Attrition Subtitle],
        "On-Time Subtitle", [On-Time Subtitle],
        "Top Leaver Department", [Top Leaver Department],
        "As Of Label", [As Of Label],
        "Check Headcount Bridge", [Check Headcount Bridge],
        "Check Task Outcomes", [Check Task Outcomes],
        "Check Rates Sum", [Check Rates Sum],
        "Check Attendance", [Check Attendance],
        "Bridge Value", [Bridge Value],
        "Week Status Color", [Week Status Color],
        "Week Status", [Week Status],
        "Attrition PY Text", [Attrition PY Text],
        "Leavers Split Text", [Leavers Split Text],
        "Leavers (chart)", [Leavers (chart)],
        "Attrition Target", [Attrition Target],
        "Attrition Colour", [Attrition Colour],
        "Days Overdue", [Days Overdue]
    )
```