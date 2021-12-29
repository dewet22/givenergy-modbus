"""Console script for givenergy_modbus."""

import click


@click.command()
def main():
    """Main entrypoint."""
    click.echo("givenergy-modbus")
    click.echo("=" * len("givenergy-modbus"))
    click.echo(
        "A python library to access GivEnergy inverters via Modbus TCP, with no dependency on the GivEnergy Cloud."
    )


if __name__ == "__main__":
    main()  # pragma: no cover
