from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    username: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    hashed_password: Mapped[str] = mapped_column(String(255))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    workouts: Mapped[list["Workout"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    goals: Mapped[list["Goal"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    notifications: Mapped[list["Notification"]] = relationship(
        back_populates="user", cascade="all, delete-orphan"
    )
    progress: Mapped[list["Progress"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    workout_plans: Mapped[list["WorkoutPlan"]] = relationship(back_populates="user", cascade="all, delete-orphan")
    streak: Mapped["Streak | None"] = relationship(back_populates="user", cascade="all, delete-orphan", uselist=False)
    user_badges: Mapped[list["UserBadge"]] = relationship(back_populates="user", cascade="all, delete-orphan")


class Workout(Base):
    __tablename__ = "workouts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    workout_name: Mapped[str] = mapped_column(String(100))
    category: Mapped[str] = mapped_column(String(20))
    duration: Mapped[int] = mapped_column(Integer)
    calories_burned: Mapped[int] = mapped_column(Integer)
    workout_date: Mapped[date] = mapped_column(Date, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped[User] = relationship(back_populates="workouts")


class Progress(Base):
    __tablename__ = "progress"
    __table_args__ = (UniqueConstraint("user_id", "date", name="uq_progress_user_date"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    total_workouts: Mapped[int] = mapped_column(Integer, default=0)
    total_calories: Mapped[int] = mapped_column(Integer, default=0)
    total_duration: Mapped[int] = mapped_column(Integer, default=0)
    date: Mapped[date] = mapped_column(Date, index=True)

    user: Mapped[User] = relationship(back_populates="progress")


class Goal(Base):
    __tablename__ = "goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    goal_type: Mapped[str] = mapped_column(String(30))
    target_value: Mapped[float] = mapped_column(Float)
    current_value: Mapped[float] = mapped_column(Float, default=0)
    deadline: Mapped[date] = mapped_column(Date)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped[User] = relationship(back_populates="goals")


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(100))
    message: Mapped[str] = mapped_column(String(500))
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped[User] = relationship(back_populates="notifications")


class Exercise(Base):
    __tablename__ = "exercises"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    category: Mapped[str] = mapped_column(String(20), index=True)
    description: Mapped[str] = mapped_column(String(500))
    duration: Mapped[int] = mapped_column(Integer)


class WorkoutPlan(Base):
    __tablename__ = "workout_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500), default="")
    scheduled_date: Mapped[date] = mapped_column(Date, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    user: Mapped[User] = relationship(back_populates="workout_plans")
    exercises: Mapped[list["WorkoutPlanExercise"]] = relationship(cascade="all, delete-orphan")


class WorkoutPlanExercise(Base):
    __tablename__ = "workout_plan_exercises"
    __table_args__ = (UniqueConstraint("plan_id", "exercise_id", name="uq_plan_exercise"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    plan_id: Mapped[int] = mapped_column(ForeignKey("workout_plans.id", ondelete="CASCADE"), index=True)
    exercise_id: Mapped[int] = mapped_column(ForeignKey("exercises.id", ondelete="CASCADE"), index=True)
    exercise: Mapped[Exercise] = relationship()


class Streak(Base):
    __tablename__ = "streaks"
    __table_args__ = (UniqueConstraint("user_id", name="uq_streak_user"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    current_streak: Mapped[int] = mapped_column(Integer, default=0)
    longest_streak: Mapped[int] = mapped_column(Integer, default=0)
    last_workout_date: Mapped[date | None] = mapped_column(Date)

    user: Mapped[User] = relationship(back_populates="streak")


class Badge(Base):
    __tablename__ = "badges"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)
    description: Mapped[str] = mapped_column(String(250))
    icon: Mapped[str] = mapped_column(String(20))


class UserBadge(Base):
    __tablename__ = "user_badges"
    __table_args__ = (UniqueConstraint("user_id", "badge_id", name="uq_user_badge"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    badge_id: Mapped[int] = mapped_column(ForeignKey("badges.id", ondelete="CASCADE"), index=True)
    earned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    badge: Mapped[Badge] = relationship()
    user: Mapped[User] = relationship(back_populates="user_badges")
