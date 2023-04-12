from datetime import datetime
from typing import Any

from pydantic.utils import GetterDict


class RegisterGetter(GetterDict):
    """GetterDict implementation to consolidate register data structures."""

    def get(self, key: Any, default: Any = None) -> Any:
        """Getter that computes some virtual attributes."""
        if key.endswith('serial_number'):
            serial1 = self.get(f'{key}_1_2', None)
            serial2 = self.get(f'{key}_3_4', None)
            serial3 = self.get(f'{key}_5_6', None)
            serial4 = self.get(f'{key}_7_8', None)
            serial5 = self.get(f'{key}_9_10', None)
            if None in (serial1, serial2, serial3, serial4, serial5):
                return None
            return ''.join([serial1, serial2, serial3, serial4, serial5])

        if key in ['num_mppt', 'num_phases']:
            obj = self.get('num_mppt_and_num_phases', None)
            if obj is None:
                return None
            elif key == 'num_mppt':
                return obj[0]
            return obj[1]

        if key == 'system_time':
            year = self.get('system_time_year', None)
            month = self.get('system_time_month', None)
            day = self.get('system_time_day', None)
            hour = self.get('system_time_hour', None)
            minute = self.get('system_time_minute', None)
            second = self.get('system_time_second', None)
            if (year, month, day, hour, minute, second).count(None) > 0:
                return None
            return datetime(year + 2000, month, day, hour, minute, second)

        if key in ('charge_slot_1', 'charge_slot_2', 'discharge_slot_1', 'discharge_slot_2'):
            start = self.get(f'{key}_start', None)
            end = self.get(f'{key}_end', None)
            if None in (start, end):
                return None
            return start, end

        if key == 'inverter_firmware_version':
            dsp_firmware_version = self.get('dsp_firmware_version', None)
            arm_firmware_version = self.get('arm_firmware_version', None)
            if None in (dsp_firmware_version, arm_firmware_version):
                return None
            return f'D0.{dsp_firmware_version}-A0.{arm_firmware_version}'

        # PV power & energy aggregates
        if key == 'p_pv':
            return self.get('p_pv1') + self.get('p_pv2')
        if key == 'e_pv_day':
            return self.get('e_pv1_day') + self.get('e_pv2_day')

        return getattr(self._obj, key, default)
