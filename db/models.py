from sqlalchemy import BigInteger, func, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
import datetime

class Base(DeclarativeBase):
    pass

class User(Base):
    __tablename__ = "users"

    user_id: Mapped[int] = mapped_column(BigInteger, primary_key=True,
                                               autoincrement=False, index=True)
    user_name: Mapped[str] = mapped_column()
    user_first_name: Mapped[str] = mapped_column()
    created_at: Mapped[datetime.datetime] = mapped_column(server_default=func.now())

    liked_films: Mapped[list["LikedFilms"]] = relationship("LikedFilms", back_populates="user")

class Films(Base):
    __tablename__ = "films"

    code: Mapped[int] = mapped_column(primary_key=True, autoincrement=False, index=True)
    title: Mapped[str] = mapped_column()
    description: Mapped[str] = mapped_column()
    image_url: Mapped[str] = mapped_column()

    liked_by_users: Mapped[list["LikedFilms"]] = relationship("LikedFilms", back_populates="film")

class LikedFilms(Base):
    __tablename__ = "liked_films"
    __table_args__ = (UniqueConstraint("user_id", "film_code", name="uq_liked_user_film"),)

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, ForeignKey("users.user_id"))
    film_code: Mapped[int] = mapped_column(ForeignKey("films.code"))

    user = relationship("User", back_populates="liked_films")
    film = relationship("Films", back_populates="liked_by_users")
