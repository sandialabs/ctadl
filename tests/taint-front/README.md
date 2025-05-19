# Taint-front test runner

Any .tnt testcases in this directory are run.
If there is a corresponding .json file, we test the ctadlir against with test_ctadlir.py.
If there is a .codeflows file (can be empty), we check for code flows with sarif_has_code_flows.py.
If there is a .nocodeflows file, we check for absence of code flows.
