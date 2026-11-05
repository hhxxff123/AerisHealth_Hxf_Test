import pytest
from io import StringIO
import sys
from B.split_optimiser import main as split_main

def run_split(input_str):
    sys.stdin = StringIO(input_str)
    captured_output = StringIO()
    sys.stdout = captured_output
    split_main()
    sys.stdin = sys.__stdin__
    sys.stdout = sys.__stdout__
    return captured_output.getvalue().strip().splitlines()

def test_split_success():
    input_data = "2 30\nwh1 20 5.0 1.0\nwh2 20 5.0 1.0"
    res = run_split(input_data)
    assert res[0] == "1 25.0"
    assert res[1] == "wh1 20"

def test_split_no_stock():
    input_data = "2 50\nwh1 20 5.0 1.0\nwh2 20 5.0 1.0"
    res = run_split(input_data)
    assert res[0] == "-1"

def test_split_multi_warehouse():
    input_data = "2 30\nwh2 20 5.0 1.0\nwh1 20 5.0 1.0"
    res = run_split(input_data)
    assert res[0] == "2 37.0"
