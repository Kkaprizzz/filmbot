from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from core.config import settings

engine = create_async_engine(settings.DB_URL)
async_session = async_sessionmaker(engine,
                                   class_=AsyncSession, 
                                   expire_on_commit=False)