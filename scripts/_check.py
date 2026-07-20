import pathlib
t = pathlib.Path("D:/workspace/q_project/code_v4/run_research.py").read_text(encoding="utf-8")
NL = chr(10)
Q = chr(34)
S = chr(32)
old1 = S*8 + Q + "if composite.empty:" + Q + " + NL"
old1 += S*12 + Q + "logger.error(" + Q + " + NL"
old1 += S*16 + Q + "Regime composite failed to produce scores. " + Q + " + NL"
old1 += S*16 + Q + "Check regime config and index data coverage. " + Q + " + NL"
old1 += S*16 + Q + "Error: %s" + Q + ", regime_diag.get(" + Q + "error" + Q + ", " + Q + "unknown" + Q + ")," + Q + " + NL"
old1 += S*12 + Q + ")" + Q + " + NL"
old1 += S*12 + Q + "return 1" + Q + " + NL"
old1 += S*4 + Q + "else:" + Q + " + NL"
print("P1 found:", old1 in t)
