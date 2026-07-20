"""
Live trading infrastructure for code_v4.

Modules:
- signal_service: Generate target signals from latest data
- order_builder: Convert signals to trade orders
- risk_gate: Pre-trade risk checks
- paper_broker: Simulated execution with fill tracking
- run_shadow: End-to-end shadow trading loop
"""
