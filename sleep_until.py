import sys
import time
from datetime import datetime, timezone

def wait_until(target_hour, target_minute):
    now = datetime.now(timezone.utc)
    target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    
    # If the target is in the past, it means we ran late or it's for tomorrow.
    # In GitHub Actions, it means the queue delayed us so much we missed the window, 
    # so we should just execute immediately.
    if now >= target:
        print(f"Current time ({now.strftime('%H:%M:%S UTC')}) is past the target time ({target.strftime('%H:%M:%S UTC')}). Proceeding immediately.")
        return
        
    diff = (target - now).total_seconds()
    print(f"Holding runner execution... sleeping for {diff:.1f} seconds until {target.strftime('%H:%M:%S UTC')}.")
    
    # Sleep until exactly the target UTC time
    time.sleep(diff)
    print(f"Target time reached! Executing pipeline at {datetime.now(timezone.utc).strftime('%H:%M:%S UTC')}.")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python sleep_until.py HH:MM")
        sys.exit(1)
        
    time_str = sys.argv[1]
    
    try:
        hour, minute = map(int, time_str.split(':'))
        wait_until(hour, minute)
    except Exception as e:
        print(f"Failed to parse target time '{time_str}': {e}")
        # Fail open: if something goes wrong formatting, just run the pipeline
        sys.exit(0)
