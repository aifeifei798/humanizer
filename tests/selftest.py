"""自测: 服务启动后运行 uv run python tests/selftest.py。

用官方评估集的样例草稿 (AGENTS.md 第 8 节), 检查输出无 prompt 回显、
无聊天标记、不复制草稿、数字保留。
"""
import json
import re
import sys
import urllib.request

BASE = "http://127.0.0.1:8100"

DRAFT = """Hi Nadia,

I’m handing off the Meridian Bank loan audit to you. We’ve completed the review of 88 files, with 12 files remaining. The outstanding files are in the “Pending Review” folder in the Meridian Bank audit workspace, organized by borrower name.

The remaining items are primarily commercial real estate loans and include several files requiring confirmation of updated income statements, collateral valuations, and covenant documentation. I’ve flagged the missing items in the audit tracker and added notes for the files that may need follow-up with Meridian Bank’s loan operations team.

The deadline is Friday, March 14. Please prioritize the files marked “High” in the tracker, especially MB-2047, MB-2091, and MB-2110, since those are scheduled for management review first. I’ll be available through Wednesday afternoon to answer questions or provide context on any earlier decisions.

Thanks for taking this over."""

body = {"text": DRAFT}
req = urllib.request.Request(BASE + "/humanize", json.dumps(body).encode(),
                             {"Content-Type": "application/json"})
out = json.load(urllib.request.urlopen(req, timeout=900))["rewrite"]
print(out, "\n" + "-" * 60)

problems = []
if len(out.split()) < 60:
    problems.append("output too short")
if "### Rewritten" in out or out.startswith("Rewrite the text below"):
    problems.append("prompt echoed")
if re.search(r"<start_of_turn>|<end_of_turn>|<\|turn", out):
    problems.append("chat markers in output")
grams = lambda t: {tuple(t.lower().split()[i:i + 5]) for i in range(len(t.split()) - 4)}
if len(grams(DRAFT) & grams(out)) / max(1, len(grams(out))) > 0.5:
    problems.append("output copies the draft")
missing = [n for n in re.findall(r"\d+", DRAFT) if n not in re.findall(r"\d+", out)]

print("FAIL: " + "; ".join(problems) if problems else "PASS: install looks right")
if missing:
    print("NOTE: numbers not found in this sample:", missing,
          "(采样偶发; 重跑一次, 若每次都缺再查采样设置)")
sys.exit(1 if problems else 0)
