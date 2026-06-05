from motor.motor_asyncio import AsyncIOMotorClient
from config.settings import settings

client: AsyncIOMotorClient = None


async def connect_to_mongo():
    global client
    client = AsyncIOMotorClient(settings.MONGODB_URL)


async def close_mongo_connection():
    client.close()


def get_database():
    return client[settings.MONGODB_DB]


def get_collection(name: str):
    return get_database()[name]
