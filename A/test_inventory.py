import pytest
from io import StringIO
import sys
from A.inventory import main as inventory_main

def run_inventory(input_str):
    sys.stdin = StringIO(input_str)
    captured_output = StringIO()
    sys.stdout = captured_output
    inventory_main()
    sys.stdin = sys.__stdin__
    sys.stdout = sys.__stdout__
    return captured_output.getvalue().strip().splitlines()

def test_normal_reserve_success():
    input_data = "100 1\nevent001 orderA RESERVE 20"
    result_lines = run_inventory(input_data)
    assert result_lines[0] == "OK 80 20"

def test_duplicate_event_id_idempotent():
    input_data = "100 2\nevent001 orderA RESERVE 20\nevent001 orderA RESERVE 20"
    result_lines = run_inventory(input_data)
    assert result_lines[0] == "OK 80 20"
    assert result_lines[1] == "DUPLICATE 80 20"

def test_over_stock_reject():
    input_data = "100 1\nevent002 orderB RESERVE 120"
    result_lines = run_inventory(input_data)
    assert result_lines[0] == "REJECTED 100 0"
