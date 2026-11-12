"""E14 hand-written invariants (arm A8') for the four generated paper-subjects apps.

Written from policy.txt and policy.expected.json ONLY, before any .html file,
ground_truth.json or README.md of those apps was opened (the only other
information used was the list of file names in each directory). They are
expressed in the XPath subset of Python's ElementTree (exact text equality,
attribute equality), over element types, link targets and visible text. They
must not be edited after results are seen; if they are wrong, that is the result.

Format per clause: (expectation_id, kind, page_scope, queries)
  kind        "forbidden_present" (violation if ANY query matches on a page)
              "required_absent"   (violation if NO query matches on a page)
  page_scope  "all" | "all_but_login" | an explicit page file name
Double-negation clauses ("must not fail to find", "should never be unable to
find") are encoded as REQUIRED presence, as policy.expected.json does.
Roles are taken from policy.expected.json by the runner.
"""

INVARIANTS = {
    "shop-hub": [
        ("exp-shop-0", "forbidden_present", "all", [".//a[@href='admin-dashboard.html']"]),
        ("exp-shop-2", "forbidden_present", "all",
         [".//button[.='Complete Purchase']", ".//button[.='Complete purchase']", ".//button[.='Place Order']"]),
        ("exp-shop-1", "required_absent", "index.html", [".//a[@href='products.html']"]),
        ("exp-shop-3", "required_absent", "all",
         [".//a[@href='support.html']", ".//a[.='Contact Support']", ".//a[.='Support']"]),
    ],
    "med-clinic": [
        ("exp-med-0", "forbidden_present", "all",
         [".//a[.='All Patients']", ".//a[.='Patient Directory']", ".//a[.='View Other Patients']"]),
        ("exp-med-2", "forbidden_present", "all",
         [".//a[@href='staff-portal.html']", ".//a[.='Clinical Dashboard']"]),
        ("exp-med-1", "required_absent", "all_but_login",
         [".//a[@href='appointments.html']", ".//button[.='Schedule Appointment']", ".//a[.='Schedule Appointment']"]),
        ("exp-med-3", "required_absent", "all_but_login",
         [".//a[@href='emergency.html']", ".//a[.='Emergency Contacts']", ".//a[.='Emergency Contact']"]),
    ],
    "hr-suite": [
        ("exp-hr-0", "forbidden_present", "all",
         [".//a[@href='salary-view.html']", ".//a[.='Team Salaries']", ".//a[.='Employee Salaries']"]),
        ("exp-hr-2", "forbidden_present", "all",
         [".//a[@href='payroll-calc.html']", ".//button[.='Run Payroll']", ".//button[.='Calculate Payroll']"]),
        ("exp-hr-1", "required_absent", "all_but_login",
         [".//a[@href='pay-stubs.html']", ".//button[.='Download Pay Stub']", ".//a[.='Download Pay Stub']"]),
        ("exp-hr-3", "required_absent", "all_but_login",
         [".//a[@href='benefits.html']", ".//a[.='Benefit Enrollment']"]),
    ],
    "config-portal": [
        ("exp-cfg-0", "forbidden_present", "all", [".//a[@href='billing.html']"]),
        ("exp-cfg-3", "forbidden_present", "all",
         [".//button[.='Save Organization Settings']", ".//button[.='Update Organization']",
          ".//button[.='Edit Organization Settings']"]),
        ("exp-cfg-1", "required_absent", "settings.html",
         [".//*[@id='subscription-level']", ".//*[@id='current-plan']"]),
        ("exp-cfg-2", "required_absent", "all_but_login", [".//a[@href='password-change.html']"]),
    ],
}
