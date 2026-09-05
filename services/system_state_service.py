from dataclasses import dataclass
import sys
from pathlib import Path

@dataclass(frozen=True)
class SystemState:
    idle_seconds: float|None=None
    battery_percent: int|None=None
    on_battery: bool|None=None
    charging: bool|None=None

class SystemStateService:
    @staticmethod
    def snapshot() -> SystemState:
        if sys.platform=="win32":return SystemStateService._windows_snapshot()
        if sys.platform.startswith("linux"):return SystemStateService._linux_snapshot()
        return SystemState()
    @staticmethod
    def _windows_snapshot() -> SystemState:
        try:
            import ctypes
            class LASTINPUTINFO(ctypes.Structure):_fields_=[("cbSize",ctypes.c_uint),("dwTime",ctypes.c_uint)]
            class SYSTEM_POWER_STATUS(ctypes.Structure):_fields_=[("ACLineStatus",ctypes.c_ubyte),("BatteryFlag",ctypes.c_ubyte),("BatteryLifePercent",ctypes.c_ubyte),("SystemStatusFlag",ctypes.c_ubyte),("BatteryLifeTime",ctypes.c_uint),("BatteryFullLifeTime",ctypes.c_uint)]
            user32=ctypes.windll.user32;kernel32=ctypes.windll.kernel32;last=LASTINPUTINFO();last.cbSize=ctypes.sizeof(last);idle=None
            if user32.GetLastInputInfo(ctypes.byref(last)):idle=((kernel32.GetTickCount()-last.dwTime)&0xFFFFFFFF)/1000.0
            power=SYSTEM_POWER_STATUS();battery=None;on_battery=None;charging=None
            if kernel32.GetSystemPowerStatus(ctypes.byref(power)):
                battery=None if power.BatteryLifePercent==255 else int(power.BatteryLifePercent);on_battery=None if power.ACLineStatus==255 else power.ACLineStatus==0;charging=bool(power.BatteryFlag&8) if power.BatteryFlag!=255 else None
            return SystemState(idle,battery,on_battery,charging)
        except (AttributeError,OSError,ValueError):return SystemState()
    @staticmethod
    def _linux_snapshot() -> SystemState:
        for folder in sorted(Path("/sys/class/power_supply").glob("BAT*")):
            try:
                percent=int((folder/"capacity").read_text().strip());status=(folder/"status").read_text().strip().casefold();return SystemState(None,percent,status=="discharging",status=="charging")
            except (OSError,ValueError):continue
        return SystemState()

def automatic_pause_reasons(state:SystemState,idle_enabled:bool,idle_minutes:int,battery_enabled:bool,battery_threshold:int,battery_resume_hysteresis:int,was_battery_paused:bool=False) -> set[str]:
    reasons=set()
    if idle_enabled and state.idle_seconds is not None and state.idle_seconds>=max(1,idle_minutes)*60:reasons.add(f"Computer idle ≥ {max(1,idle_minutes)} min")
    resume_level=min(100,battery_threshold+max(0,battery_resume_hysteresis));battery_limit=resume_level if was_battery_paused else battery_threshold
    if battery_enabled and state.on_battery is True and state.battery_percent is not None and state.battery_percent<=battery_limit:reasons.add(f"Battery low ({state.battery_percent}% ≤ {battery_threshold}%)")
    return reasons
