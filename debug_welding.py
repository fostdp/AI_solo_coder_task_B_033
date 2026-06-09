import math
from datetime import datetime, timedelta
from backend.config import settings

print("Testing welding detection periodicity calculation...")
print(f"FIRE_WELDING_TEMP_FLUCTUATION: {settings.FIRE_WELDING_TEMP_FLUCTUATION}")
print(f"FIRE_WELDING_CYCLE_SECONDS: {settings.FIRE_WELDING_CYCLE_SECONDS}")
print(f"Threshold: {5.0 / settings.FIRE_WELDING_CYCLE_SECONDS:.4f} per minute")

base_time = datetime.utcnow()

welding_history = []
for i in range(30):
    temp = 50.0 + 10.0 * math.sin(i * 0.5)
    welding_history.append((
        base_time - timedelta(seconds=i * 10),
        temp,
        1.0
    ))

temps = [h[1] for h in welding_history]
times = [h[0] for h in welding_history]

print(f"\nTemperature sequence (first 10):")
for i in range(10):
    diff_str = f"{temps[i]-temps[i-1]:.2f}" if i>0 else 'N/A'
    print(f"  i={i}: temp={temps[i]:.2f}, diff={diff_str}")

temp_max = max(temps)
temp_min = min(temps)
temp_mean = sum(temps) / len(temps)
temp_std = math.sqrt(sum((t - temp_mean) ** 2 for t in temps) / len(temps))

duration_minutes = abs((times[-1] - times[0]).total_seconds()) / 60.0

print(f"\nTemperature stats:")
print(f"  max: {temp_max:.2f}")
print(f"  min: {temp_min:.2f}")
print(f"  mean: {temp_mean:.2f}")
print(f"  std: {temp_std:.2f}")
print(f"  duration: {duration_minutes:.2f} minutes")

fluctuation_count = 0
diffs = []
for i in range(1, len(temps)):
    diffs.append(temps[i] - temps[i-1])

print(f"\nFluctuation detection (improved algorithm):")
for i in range(1, len(diffs)):
    diff1 = diffs[i-1]
    diff2 = diffs[i]
    product = diff1 * diff2
    is_extremum = product < 0
    
    window_size = min(3, i, len(diffs) - i - 1)
    if window_size >= 1:
        left_max = max(temps[i-window_size:i+1])
        left_min = min(temps[i-window_size:i+1])
        right_max = max(temps[i:i+window_size+2])
        right_min = min(temps[i:i+window_size+2])
        peak_to_peak = max(left_max, right_max) - min(left_min, right_min)
    else:
        peak_to_peak = abs(temps[i+1] - temps[i-1])
    
    is_large_enough = peak_to_peak > settings.FIRE_WELDING_TEMP_FLUCTUATION / 4
    if is_extremum and is_large_enough:
        fluctuation_count += 1
        print(f"  i={i}: diff1={diff1:.2f}, diff2={diff2:.2f}, peak_to_peak={peak_to_peak:.2f} -> FLUCTUATION #{fluctuation_count}")
    elif is_extremum:
        print(f"  i={i}: diff1={diff1:.2f}, diff2={diff2:.2f}, peak_to_peak={peak_to_peak:.2f} -> extremum but too small")

temp_range = temp_max - temp_min
has_significant_range = temp_range > settings.FIRE_WELDING_TEMP_FLUCTUATION
has_significant_std = temp_std > settings.FIRE_WELDING_TEMP_FLUCTUATION / 2

print(f"\nTotal fluctuation count: {fluctuation_count}")
if duration_minutes > 0:
    fluctuation_frequency = fluctuation_count / duration_minutes
else:
    fluctuation_frequency = 0.0

print(f"\nTemperature range: {temp_range:.2f}")
print(f"Has significant range (> {settings.FIRE_WELDING_TEMP_FLUCTUATION}): {has_significant_range}")
print(f"Has significant std (> {settings.FIRE_WELDING_TEMP_FLUCTUATION / 2}): {has_significant_std}")
print(f"Number of data points: {len(temps)}")
print(f"Fluctuation frequency: {fluctuation_frequency:.4f} per minute")
print(f"Frequency threshold: {0.5 / settings.FIRE_WELDING_CYCLE_SECONDS:.4f} per minute")

condition1 = fluctuation_frequency >= (0.5 / settings.FIRE_WELDING_CYCLE_SECONDS)
condition2 = has_significant_range and has_significant_std and len(temps) >= 10
print(f"\nCondition 1 (frequency): {condition1}")
print(f"Condition 2 (range+std+length): {condition2}")
print(f"Is periodic: {condition1 or condition2}")
