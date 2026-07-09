"""Cross-model decode-convention invariants.

These guard conventions that span every register map, so a new Def that violates one
fails CI regardless of which model it lives in. Born from #379: several temperature
fields declared a negative ``min`` bound but decoded as unsigned, so a genuine sub-zero
reading wrapped to a huge positive and was silently suppressed. The firmware register map
(v4.1.6) marks every temperature ``signed``; the invariant below generalises that.
"""

from givenergy_modbus.model.aio_battery import AioBatteryModuleRegisterGetter
from givenergy_modbus.model.battery import BatteryRegisterGetter
from givenergy_modbus.model.ems import EmsRegisterGetter
from givenergy_modbus.model.gateway import GatewayV1RegisterGetter, GatewayV2RegisterGetter
from givenergy_modbus.model.hv_bcu import BcuRegisterGetter, BmuRegisterGetter
from givenergy_modbus.model.inverter import SinglePhaseInverterRegisterGetter
from givenergy_modbus.model.inverter_threephase import ThreePhaseInverterRegisterGetter
from givenergy_modbus.model.lv_bcu import LvBcuRegisterGetter
from givenergy_modbus.model.meter import MeterRegisterGetter

_GETTERS = {
    "SinglePhaseInverter": SinglePhaseInverterRegisterGetter,
    "ThreePhaseInverter": ThreePhaseInverterRegisterGetter,
    "Battery": BatteryRegisterGetter,
    "Bcu": BcuRegisterGetter,
    "Bmu": BmuRegisterGetter,
    "AioBatteryModule": AioBatteryModuleRegisterGetter,
    "LvBcu": LvBcuRegisterGetter,
    "Ems": EmsRegisterGetter,
    "GatewayV1": GatewayV1RegisterGetter,
    "GatewayV2": GatewayV2RegisterGetter,
    "Meter": MeterRegisterGetter,
}

# Converters that yield a signed value: the width converters, and the power-factor
# converters, which sign-convert internally (pf_signed wraps int16; pf applies a -1 offset).
_SIGNED_CONVERTERS = {"int16", "int32", "pf", "pf_signed"}


def _conv_name(c) -> str | None:
    if c is None:
        return None
    if isinstance(c, tuple):
        return _conv_name(c[0])
    return getattr(c, "__name__", str(c))


def test_negative_floor_fields_decode_signed():
    """A Def declaring ``min < 0`` must decode signed — otherwise the floor is unreachable.

    An unsigned decode can never produce a value below zero (a two's-complement negative
    wraps to a large positive that the ``max`` bound suppresses), so a negative ``min`` on
    an unsigned field is either dead or, worse, silently drops genuine negative readings.
    """
    offenders = []
    for gname, getter in _GETTERS.items():
        for attr, defn in getter.REGISTER_LUT.items():
            if defn.min_value is None or defn.min_value >= 0:
                continue
            convs = {_conv_name(defn.pre_conv), _conv_name(defn.post_conv)}
            if not (convs & _SIGNED_CONVERTERS):
                addrs = [r._idx for r in defn.registers]
                offenders.append(f"{gname}.{attr} IR{addrs} min={defn.min_value} convs={convs - {None}}")
    assert not offenders, "negative-floor fields decoding unsigned:\n  " + "\n  ".join(offenders)
