"""Minimal example: connect through the CellerLab Bluetooth 5.3 adapter and read APS."""

import asyncio

from kometa import KometaClient


async def main() -> None:
    async with KometaClient() as kometa:
        settings = await kometa.get_aps_all()
        print("APS:", settings)
        print("VOL:", await kometa.get_aps("VOL"))
        runtime = await kometa.get_apd("TICKS", "BLE_CON", "POWER_MODE")
        print("APD:", runtime)


if __name__ == "__main__":
    asyncio.run(main())
