from sqlalchemy import select, update, delete, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload

from db.session import async_session
from db.models import User, Films, LikedFilms

from core.logger import get_logger

logger = get_logger(__name__)

class Database:
    # === Users ===

    def __init__(self):
        logger.info("Инициализация базы данных...")

    async def add_user(self, user_id: int, user_name: str, first_name: str):
        async with async_session() as session:
            async with session.begin():
                stmt = insert(User).values(user_id=user_id, user_name=user_name, user_first_name=first_name)
                stmt = stmt.on_conflict_do_nothing(index_elements=['user_id'])
                await session.execute(stmt)

    async def get_user_count(self) -> int:
        async with async_session() as session:
            result = await session.execute(select(func.count()).select_from(User))
            return result.scalar()
        
    async def get_all_users(self):
        async with async_session() as session:
            result = await session.execute(select(User))
            return result.scalars().all()
        
    # === Films ===
    async def add_movie(self, code: int, title: str, description: str, image_url: str):
        async with async_session() as session:
            async with session.begin():
                stmt = insert(Films).values(code=code, title=title, description=description, image_url=image_url)
                stmt = stmt.on_conflict_do_update(
                    index_elements=['code'],
                    set_=dict(title=title, description=description, image_url=image_url)
                )
                await session.execute(stmt)

    async def delete_movie(self, code: int):
        async with async_session() as session:
            async with session.begin():
                await session.execute(delete(Films).where(Films.code == code))
    
    async def get_movie_by_code(self, code: int):
        async with async_session() as session:
            result = await session.execute(select(Films).where(Films.code == code))
            return result.scalar_one_or_none()
        
    async def get_all_films(self):
        async with async_session() as session:
            result = await session.execute(select(Films).order_by(Films.code.desc()))
            return result.scalars().all()
        
    async def get_all_films_count(self) -> int:
        async with async_session() as session:
            result = await session.execute(select(func.count()).select_from(Films))
            return result.scalar()
        
    async def get_free_code(self) -> int:
        async with async_session() as session:
            result = await session.execute(select(func.max(Films.code)))
            for code in range(1, (result.scalar() or 0) + 2):
                existing = await session.execute(select(Films).where(Films.code == code))
                if not existing.scalar_one_or_none():
                    return code
            return None
        
    # === LikedFilms ===
    async def add_liked_movie(self, user_id: int, film_code: int):
        async with async_session() as session:
            async with session.begin():
                stmt = insert(LikedFilms).values(user_id=user_id, film_code=film_code)
                stmt = stmt.on_conflict_do_nothing(index_elements=['user_id', 'film_code'])
                await session.execute(stmt)

    async def get_liked_movies(self, user_id: int):
        async with async_session() as session:
            result = await session.execute(select(LikedFilms.film_code).where(LikedFilms.user_id == user_id))
            return [row[0] for row in result.fetchall()]
        
    async def remove_liked_movie(self, user_id: int, film_code: int):
        async with async_session() as session:
            async with session.begin():
                await session.execute(delete(LikedFilms).where(LikedFilms.user_id == user_id, LikedFilms.film_code == film_code))

    # === Statistics ===

    async def get_statistics(self):
        async with async_session() as session:
            u_count = await session.execute(select(func.count()).select_from(User))
            f_count = await session.execute(select(func.count()).select_from(Films))
            return {
                "users_count": u_count.scalar(),
                "films_count": f_count.scalar()
            }
        
database = Database()