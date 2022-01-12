import datetime

from pydantic import BaseModel

from givenergy_modbus.model.register_getter import RegisterGetter
from tests.model.test_register_cache import register_cache  # noqa: F401


class TestModel(BaseModel):
    """Structured format for all inverter attributes."""

    class Config:  # noqa: D106
        orm_mode = True
        getter_dict = RegisterGetter
        allow_mutation = False

    __test__ = False  # squelch PytestCollectionWarning
    inverter_serial_number: str
    battery_serial_number: str
    system_time: datetime.datetime
    discharge_slot_2: tuple[datetime.time, datetime.time]
    inverter_firmware_version: str
    num_mppt: int
    num_phases: int


class AttrDict(dict):  # noqa: D101
    def __init__(self, *args, **kwargs) -> None:  # noqa: D103
        super().__init__(*args, **kwargs)
        self.__dict__ = self


def test_get(register_cache):  # noqa: F811
    """Test the getter correctly transcribes fields."""
    tm = TestModel.from_orm(
        AttrDict(
            {
                'inverter_serial_number_1_2': 'fo',
                'inverter_serial_number_3_4': 'ob',
                'inverter_serial_number_5_6': 'ar',
                'inverter_serial_number_7_8': '12',
                'inverter_serial_number_9_10': '34',
                'battery_serial_number_1_2': '98',
                'battery_serial_number_3_4': '76',
                'battery_serial_number_5_6': '54',
                'battery_serial_number_7_8': '32',
                'battery_serial_number_9_10': '10',
                'system_time_year': 22,
                'system_time_month': 12,
                'system_time_day': 22,
                'system_time_hour': 22,
                'system_time_minute': 22,
                'system_time_second': 22,
                'discharge_slot_2_start': datetime.time(2, 3),
                'discharge_slot_2_end': datetime.time(4, 5),
                'dsp_firmware_version': 299,
                'arm_firmware_version': 959,
                'num_mppt_and_num_phases': (6, 9),
            }
        )
    )

    assert tm.dict() == {
        'inverter_serial_number': 'foobar1234',
        'battery_serial_number': '9876543210',
        'system_time': datetime.datetime(2022, 12, 22, 22, 22, 22),
        'discharge_slot_2': (datetime.time(2, 3), datetime.time(4, 5)),
        'inverter_firmware_version': 'D0.299-A0.959',
        'num_mppt': 6,
        'num_phases': 9,
    }
