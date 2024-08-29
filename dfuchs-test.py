import asyncio

from faststream import FastStream
from faststream.kafka import KafkaBroker
from faststream.security import SASLPlaintext

security = SASLPlaintext(
    username="telegraf",
    password="7c03Ry9oDLA=",
)
broker = KafkaBroker("localhost:9092", security=security)
app = FastStream(broker)

# publisher = broker.publisher("lsst.square.metrics.dfuchs-test")


async def main():
    async with broker as br:
        await br.publish("dfuchs-test", "lsst.square.metrics.dfuchs-test")


if __name__ == "__main__":
    asyncio.run(main())
