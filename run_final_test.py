import subprocess
import sys

result = subprocess.run(
    [sys.executable, "test_regression.py"],
    capture_output=True,
    text=True,
    cwd="d:\\SOLO-2\\AI_solo_coder_task_A_033"
)

# 找到最后的总结部分
lines = result.stdout.split('\n')
in_summary = False
for line in lines:
    if 'REGRESSION TEST SUMMARY' in line:
        in_summary = True
    if in_summary:
        print(line)

print(f"\nExit code: {result.returncode}")
if result.returncode == 0:
    print("\n✅ ALL TESTS PASSED!")
else:
    print("\n❌ SOME TESTS FAILED!")
    if result.stderr:
        print("Stderr:", result.stderr)
