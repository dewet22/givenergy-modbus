from givenergy_modbus.model.plant import Plant


class ModelMixin:
    """Modeling of the entire Plant."""

    plant: Plant

    def __init__(self, *args, **kwargs):
        super().__init__()
        self.plant = Plant()

    @property
    def number_batteries(self):
        """Convenience accessor."""
        return self.plant.number_batteries
