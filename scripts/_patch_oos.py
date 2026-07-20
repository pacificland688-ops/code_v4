import pathlib
p = pathlib.Path('D:/workspace/q_project/code_v4/tests/test_regime_warmup_oos.py')
text = p.read_text(encoding='utf-8')
OLD = (
    chr(32)*12 + '# OOS dates should be covered when data_end_date includes them\n'
    + chr(32)*12 + '# and there' + chr(39) + 's enough history\n'
    + chr(32)*12 + 'oos_covered = oos_set & prob_dates\n'
    + chr(32)*12 + 'if oos_covered:\n'
    + chr(32)*16 + 'assert len(oos_covered) > 0, ' + chr(34) + 'OOS dates should have regime probs' + chr(34) + '\n'
)
NEW = (
    chr(32)*12 + '# OOS dates should be covered when data_end_date includes them\n'
    + chr(32)*12 + '# and there' + chr(39) + 's enough history. With scoring-signal-date\n'
    + chr(32)*12 + '# warmup, the regime engine has full rolling IC history for\n'
    + chr(32)*12 + '# every OOS date, so the entire OOS subset must be present.\n'
    + chr(32)*12 + 'oos_covered = oos_set & prob_dates\n'
    + chr(32)*12 + 'assert oos_set.issubset(prob_dates), (\n'
    + chr(32)*16 + 'f' + chr(34) + 'OOS dates missing from regime probs: ' + chr(34) + '\n'
    + chr(32)*16 + 'f' + chr(34) + '{sorted(oos_set - prob_dates)[:5]}... ' + chr(34) + '\n'
    + chr(32)*16 + 'f' + chr(34) + 'covered={len(oos_covered)}/{len(oos_set)}' + chr(34) + '\n'
    + chr(32)*12 + ')\n'
)
print('found:', OLD in text)
text2 = text.replace(OLD, NEW)
print('changed:', text != text2)
if text != text2:
    p.write_text(text2, encoding='utf-8')
print('done')
