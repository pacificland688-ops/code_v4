"""Photoresist panic live alert system.

Research-only online pipeline on top of the frozen primary_5d signal:
data update -> quality gate -> PIT universe -> basket -> frozen gate ->
state machine -> severity/reversal/commonality explanation -> alert ->
forward outcome tracking.

No auto-trading. TRADE_READY is always False in v1.
"""
