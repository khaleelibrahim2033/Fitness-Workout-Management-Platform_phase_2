import os
from calendar import monthrange
from datetime import date, timedelta

from dotenv import load_dotenv
from fastapi import Depends, FastAPI, HTTPException, Query, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

load_dotenv()

from .auth import create_access_token, get_current_user, hash_password, verify_password
from .database import Base, engine, get_db
from .models import (
    Badge,
    Exercise,
    Goal,
    Notification,
    Progress,
    Streak,
    User,
    UserBadge,
    Workout,
    WorkoutPlan,
    WorkoutPlanExercise,
)
from .schemas import (
    GoalCreate,
    GoalResponse,
    GoalUpdate,
    BadgeResponse,
    ComparisonResponse,
    DashboardResponse,
    ExerciseCategory,
    ExerciseResponse,
    NotificationResponse,
    ProgressDay,
    ReportSummary,
    StreakResponse,
    TokenResponse,
    UserCreate,
    UserResponse,
    WorkoutCreate,
    WorkoutPlanCreate,
    WorkoutPlanResponse,
    WorkoutResponse,
    WorkoutUpdate,
)


if os.getenv("APP_ENV", "development").lower() == "production" and (
    not os.getenv("JWT_SECRET_KEY") or os.getenv("JWT_SECRET_KEY") == "development-only-secret-change-before-deploying"
):
    raise RuntimeError("Set a strong JWT_SECRET_KEY before running in production")

Base.metadata.create_all(bind=engine)
SEED_EXERCISES = [
    ("Outdoor Run", "Cardio", "Steady-paced run to build cardiovascular endurance.", 30),
    ("Cycling", "Cardio", "A low-impact ride for endurance and leg strength.", 40),
    ("Jump Rope", "Cardio", "A quick full-body cardio session.", 15),
    ("Brisk Walk", "Cardio", "An accessible walk to keep your body moving.", 30),
    ("High Knees", "Cardio", "A short, energetic cardio interval.", 10),
    ("Bodyweight Squats", "Strength", "Build lower-body strength with controlled squats.", 15),
    ("Push-ups", "Strength", "A classic upper-body and core strength exercise.", 15),
    ("Dumbbell Rows", "Strength", "Strengthen your back with a controlled row.", 20),
    ("Plank", "Strength", "Build core stability with a strong plank hold.", 5),
    ("Glute Bridges", "Strength", "Activate and strengthen the glutes and hips.", 12),
    ("Sun Salutation", "Yoga", "A flowing sequence to warm up the whole body.", 12),
    ("Child's Pose", "Yoga", "A restorative stretch for the back and hips.", 5),
    ("Warrior Flow", "Yoga", "A standing flow for balance and lower-body strength.", 18),
    ("Seated Twist", "Yoga", "A gentle seated spinal mobility stretch.", 6),
    ("Breathwork", "Yoga", "A calming guided breathing practice.", 8),
]
with Session(bind=engine) as seed_db:
    for exercise_name, exercise_category, exercise_description, exercise_duration in SEED_EXERCISES:
        if seed_db.scalar(select(Exercise.id).where(Exercise.name == exercise_name)) is None:
            seed_db.add(Exercise(
                name=exercise_name,
                category=exercise_category,
                description=exercise_description,
                duration=exercise_duration,
            ))
    seed_db.commit()
SEED_BADGES = [
    ("First Step", "Log your first workout.", "🌱"),
    ("10 Workouts", "Complete 10 workouts.", "🏅"),
    ("50 Workouts", "Complete 50 workouts.", "🏆"),
    ("7-day Streak", "Work out 7 days in a row.", "🔥"),
    ("30-day Streak", "Work out 30 days in a row.", "⚡"),
    ("Goal Getter", "Complete a fitness goal.", "🎯"),
]
with Session(bind=engine) as seed_db:
    for badge_name, badge_description, badge_icon in SEED_BADGES:
        if seed_db.scalar(select(Badge).where(Badge.name == badge_name)) is None:
            seed_db.add(Badge(name=badge_name, description=badge_description, icon=badge_icon))
    seed_db.commit()
openapi_tags = [
    {"name": "Authentication", "description": "Register, sign in, and inspect the current account."},
    {"name": "Workouts", "description": "Create, list, update, and delete your workouts."},
    {"name": "Progress", "description": "Review daily workout totals for a date range."},
    {"name": "Reports", "description": "View weekly and monthly activity summaries."},
    {"name": "Goals", "description": "Set fitness goals and track their progress."},
    {"name": "Notifications", "description": "View reminders and goal alerts and manage their read status."},
    {"name": "Workout Plans", "description": "Schedule upcoming workouts and add exercises to your plans."},
    {"name": "Exercises", "description": "Search and filter the exercise library."},
    {"name": "Achievements", "description": "Track workout streaks and earned badges."},
    {"name": "Dashboard", "description": "Personalized daily fitness summary."},
    {"name": "System", "description": "Service health and status."},
]
app = FastAPI(title="FitTrack API", version="1.0.0", openapi_tags=openapi_tags)
allowed_origins = [origin.strip() for origin in os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").split(",")]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def update_daily_progress(db: Session, user_id: int, workout_date: date) -> None:
    db.flush()
    totals = db.execute(
        select(
            func.count(Workout.id),
            func.coalesce(func.sum(Workout.calories_burned), 0),
            func.coalesce(func.sum(Workout.duration), 0),
        ).where(Workout.user_id == user_id, Workout.workout_date == workout_date)
    ).one()
    progress = db.scalar(
        select(Progress).where(Progress.user_id == user_id, Progress.date == workout_date)
    )
    if totals[0] == 0:
        if progress is not None:
            db.delete(progress)
        return
    if progress is None:
        progress = Progress(user_id=user_id, date=workout_date)
        db.add(progress)
    progress.total_workouts = totals[0]
    progress.total_calories = totals[1]
    progress.total_duration = totals[2]


def award_badge(db: Session, user_id: int, name: str) -> None:
    badge = db.scalar(select(Badge).where(Badge.name == name))
    if badge is None:
        raise RuntimeError(f"Configured badge is missing: {name}")
    existing = db.scalar(
        select(UserBadge.id).where(UserBadge.user_id == user_id, UserBadge.badge_id == badge.id)
    )
    if existing is None:
        db.add(UserBadge(user_id=user_id, badge_id=badge.id))
        db.add(Notification(user_id=user_id, title=f"Badge earned: {badge.name}", message=badge.description))


def update_streak_and_badges(db: Session, user_id: int) -> None:
    today = date.today()
    workout_dates = db.scalars(
        select(Workout.workout_date)
        .where(Workout.user_id == user_id, Workout.workout_date <= today)
        .distinct()
        .order_by(Workout.workout_date.desc())
    ).all()
    date_set = set(workout_dates)
    latest = workout_dates[0] if workout_dates else None
    current = 0
    if latest is not None and latest >= today - timedelta(days=1):
        cursor = latest
        while cursor in date_set:
            current += 1
            cursor -= timedelta(days=1)
    longest = 0
    run = 0
    previous = None
    for workout_day in sorted(date_set):
        run = run + 1 if previous is not None and workout_day == previous + timedelta(days=1) else 1
        longest = max(longest, run)
        previous = workout_day
    streak = db.scalar(select(Streak).where(Streak.user_id == user_id))
    if streak is None:
        streak = Streak(user_id=user_id, current_streak=0, longest_streak=0)
        db.add(streak)
    streak.current_streak = current
    streak.longest_streak = max(longest, streak.longest_streak)
    streak.last_workout_date = latest

    completed_workouts = db.scalar(
        select(func.count(Workout.id)).where(Workout.user_id == user_id, Workout.workout_date <= today)
    ) or 0
    if completed_workouts >= 1:
        award_badge(db, user_id, "First Step")
    if completed_workouts >= 10:
        award_badge(db, user_id, "10 Workouts")
    if completed_workouts >= 50:
        award_badge(db, user_id, "50 Workouts")
    if streak.current_streak >= 7:
        award_badge(db, user_id, "7-day Streak")
    if streak.current_streak >= 30:
        award_badge(db, user_id, "30-day Streak")


def goal_status(goal: Goal) -> str:
    if goal.current_value >= goal.target_value:
        return "completed"
    if goal.deadline < date.today():
        return "overdue"
    return "active"


def goal_response(goal: Goal) -> GoalResponse:
    return GoalResponse(
        id=goal.id,
        user_id=goal.user_id,
        goal_type=goal.goal_type,
        target_value=goal.target_value,
        current_value=goal.current_value,
        deadline=goal.deadline,
        created_at=goal.created_at,
        status=goal_status(goal),
    )


def get_owned_workout(db: Session, workout_id: int, user_id: int) -> Workout:
    workout = db.scalar(select(Workout).where(Workout.id == workout_id, Workout.user_id == user_id))
    if workout is None:
        raise HTTPException(status_code=404, detail="Workout not found")
    return workout


def report_for_range(db: Session, user_id: int, start: date, end: date) -> ReportSummary:
    rows = db.scalars(
        select(Progress)
        .where(Progress.user_id == user_id, Progress.date >= start, Progress.date <= end)
        .order_by(Progress.date)
    ).all()
    by_date = {row.date: row for row in rows}
    days = [
        ProgressDay(
            date=day,
            total_workouts=by_date[day].total_workouts if day in by_date else 0,
            total_calories=by_date[day].total_calories if day in by_date else 0,
            total_duration=by_date[day].total_duration if day in by_date else 0,
        )
        for day in (start + timedelta(days=index) for index in range((end - start).days + 1))
    ]
    return ReportSummary(
        start_date=start,
        end_date=end,
        total_workouts=sum(day.total_workouts for day in days),
        total_calories=sum(day.total_calories for day in days),
        total_duration=sum(day.total_duration for day in days),
        days=days,
    )


@app.get("/api/health", tags=["System"])
def health_check():
    return {"status": "ok"}


@app.post(
    "/api/auth/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Authentication"],
)
def register(payload: UserCreate, db: Session = Depends(get_db)):
    existing = db.scalar(
        select(User).where((User.email == payload.email.lower()) | (User.username == payload.username))
    )
    if existing is not None:
        raise HTTPException(status_code=409, detail="Email or username is already registered")
    user = User(
        username=payload.username,
        email=payload.email.lower(),
        hashed_password=hash_password(payload.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return TokenResponse(access_token=create_access_token(user.id), user=user)


@app.post("/api/auth/login", response_model=TokenResponse, tags=["Authentication"])
def login(
    payload: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    identifier = payload.username.strip()
    user = db.scalar(
        select(User).where(
            (User.username == identifier) | (User.email == identifier.lower())
        )
    )
    if (
        user is None
        or not payload.password
        or len(payload.password.encode("utf-8")) > 72
        or not verify_password(payload.password, user.hashed_password)
    ):
        raise HTTPException(status_code=401, detail="Incorrect username/email or password")
    return TokenResponse(access_token=create_access_token(user.id), user=user)


@app.get("/api/auth/me", response_model=UserResponse, tags=["Authentication"])
def current_user(user: User = Depends(get_current_user)):
    return user


@app.get("/api/workouts", response_model=list[WorkoutResponse], tags=["Workouts"])
def list_workouts(
    start_date: date | None = None,
    end_date: date | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = select(Workout).where(Workout.user_id == user.id)
    if start_date is not None:
        query = query.where(Workout.workout_date >= start_date)
    if end_date is not None:
        query = query.where(Workout.workout_date <= end_date)
    return db.scalars(query.order_by(Workout.workout_date.desc(), Workout.id.desc())).all()


@app.post(
    "/api/workouts",
    response_model=WorkoutResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Workouts"],
)
def create_workout(
    payload: WorkoutCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workout = Workout(**payload.model_dump(), user_id=user.id)
    db.add(workout)
    update_daily_progress(db, user.id, workout.workout_date)
    update_streak_and_badges(db, user.id)
    db.commit()
    db.refresh(workout)
    return workout


@app.patch("/api/workouts/{workout_id}", response_model=WorkoutResponse, tags=["Workouts"])
def update_workout(
    workout_id: int,
    payload: WorkoutUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workout = get_owned_workout(db, workout_id, user.id)
    old_date = workout.workout_date
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(workout, field, value)
    update_daily_progress(db, user.id, old_date)
    if workout.workout_date != old_date:
        update_daily_progress(db, user.id, workout.workout_date)
    update_streak_and_badges(db, user.id)
    db.commit()
    db.refresh(workout)
    return workout


@app.delete("/api/workouts/{workout_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Workouts"])
def delete_workout(
    workout_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    workout = get_owned_workout(db, workout_id, user.id)
    workout_date = workout.workout_date
    db.delete(workout)
    db.flush()
    update_daily_progress(db, user.id, workout_date)
    update_streak_and_badges(db, user.id)
    db.commit()


@app.get("/api/progress", response_model=list[ProgressDay], tags=["Progress"])
def daily_progress(
    start_date: date = Query(default_factory=lambda: date.today() - timedelta(days=29)),
    end_date: date = Query(default_factory=date.today),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if start_date > end_date or (end_date - start_date).days > 366:
        raise HTTPException(status_code=422, detail="Date range must be ordered and no longer than 367 days")
    return report_for_range(db, user.id, start_date, end_date).days


@app.get("/api/reports/weekly", response_model=ReportSummary, tags=["Reports"])
def weekly_report(
    week_start: date | None = None,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    start = week_start or date.today() - timedelta(days=date.today().weekday())
    return report_for_range(db, user.id, start, start + timedelta(days=6))


@app.get("/api/reports/monthly", response_model=ReportSummary, tags=["Reports"])
def monthly_report(
    year: int = Query(default_factory=lambda: date.today().year, ge=2000, le=2100),
    month: int = Query(default_factory=lambda: date.today().month, ge=1, le=12),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    return report_for_range(db, user.id, start, end)


@app.get("/api/goals", response_model=list[GoalResponse], tags=["Goals"])
def list_goals(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    goals = db.scalars(select(Goal).where(Goal.user_id == user.id).order_by(Goal.deadline)).all()
    return [goal_response(goal) for goal in goals]


@app.post(
    "/api/goals",
    response_model=GoalResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Goals"],
)
def create_goal(
    payload: GoalCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    goal = Goal(**payload.model_dump(), user_id=user.id)
    db.add(goal)
    db.flush()
    db.add(
        Notification(
            user_id=user.id,
            title="New goal set",
            message=f"Your {goal.goal_type.lower()} goal is ready. Keep moving toward your target!",
        )
    )
    db.commit()
    db.refresh(goal)
    return goal_response(goal)


@app.patch("/api/goals/{goal_id}", response_model=GoalResponse, tags=["Goals"])
def update_goal(
    goal_id: int,
    payload: GoalUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    goal = db.scalar(select(Goal).where(Goal.id == goal_id, Goal.user_id == user.id))
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    was_completed = goal.current_value >= goal.target_value
    goal.current_value = payload.current_value
    is_completed = goal.current_value >= goal.target_value
    if is_completed and not was_completed:
        award_badge(db, user.id, "Goal Getter")
        db.add(
            Notification(
                user_id=user.id,
                title="Goal achieved!",
                message=f"You reached your {goal.goal_type.lower()} goal. Congratulations!",
            )
        )
    db.commit()
    db.refresh(goal)
    return goal_response(goal)


@app.delete("/api/goals/{goal_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Goals"])
def delete_goal(
    goal_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    goal = db.scalar(select(Goal).where(Goal.id == goal_id, Goal.user_id == user.id))
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    db.delete(goal)
    db.commit()


@app.get("/api/notifications", response_model=list[NotificationResponse], tags=["Notifications"])
def list_notifications(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = date.today()
    has_workout_today = db.scalar(
        select(Workout.id).where(Workout.user_id == user.id, Workout.workout_date == today).limit(1)
    )
    reminder_exists = db.scalar(
        select(Notification.id).where(
            Notification.user_id == user.id,
            Notification.title == "Daily workout reminder",
            func.date(Notification.created_at) == today.isoformat(),
        )
    )
    if has_workout_today is None and reminder_exists is None:
        db.add(
            Notification(
                user_id=user.id,
                title="Daily workout reminder",
                message="A little movement goes a long way. Log a workout when you are ready.",
            )
        )
        db.commit()
    return db.scalars(
        select(Notification)
        .where(Notification.user_id == user.id)
        .order_by(Notification.created_at.desc())
        .limit(50)
    ).all()


@app.patch(
    "/api/notifications/{notification_id}/read",
    response_model=NotificationResponse,
    tags=["Notifications"],
)
def mark_notification_read(
    notification_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    notification = db.scalar(
        select(Notification).where(Notification.id == notification_id, Notification.user_id == user.id)
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="Notification not found")
    notification.is_read = True
    db.commit()
    db.refresh(notification)
    return notification


@app.patch(
    "/api/notifications/read-all",
    status_code=status.HTTP_204_NO_CONTENT,
    tags=["Notifications"],
)
def mark_all_notifications_read(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    db.query(Notification).filter(Notification.user_id == user.id, Notification.is_read.is_(False)).update(
        {Notification.is_read: True}
    )
    db.commit()


def plan_response(plan: WorkoutPlan) -> WorkoutPlanResponse:
    return WorkoutPlanResponse(
        id=plan.id,
        user_id=plan.user_id,
        title=plan.title,
        description=plan.description,
        scheduled_date=plan.scheduled_date,
        created_at=plan.created_at,
        exercises=[entry.exercise for entry in plan.exercises],
    )


def streak_response(db: Session, user_id: int) -> StreakResponse:
    streak = db.scalar(select(Streak).where(Streak.user_id == user_id))
    if streak is None:
        return StreakResponse(current_streak=0, longest_streak=0, last_workout_date=None)
    current = streak.current_streak
    if streak.last_workout_date is None or streak.last_workout_date < date.today() - timedelta(days=1):
        current = 0
        if streak.current_streak != 0:
            streak.current_streak = 0
            db.commit()
    return StreakResponse(
        current_streak=current,
        longest_streak=streak.longest_streak,
        last_workout_date=streak.last_workout_date,
    )


def badge_responses(db: Session, user_id: int) -> list[BadgeResponse]:
    earned = {
        row.badge_id: row.earned_at
        for row in db.scalars(select(UserBadge).where(UserBadge.user_id == user_id)).all()
    }
    badges = db.scalars(select(Badge).order_by(Badge.id)).all()
    return [
        BadgeResponse(
            id=badge.id,
            name=badge.name,
            description=badge.description,
            icon=badge.icon,
            earned_at=earned.get(badge.id),
        )
        for badge in badges
    ]


@app.get("/api/exercises", response_model=list[ExerciseResponse], tags=["Exercises"])
def list_exercises(
    search: str | None = Query(default=None, max_length=100),
    category: ExerciseCategory | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = select(Exercise)
    if search:
        query = query.where(Exercise.name.ilike(f"%{search.strip()}%"))
    if category is not None:
        query = query.where(Exercise.category == category.value)
    return db.scalars(query.order_by(Exercise.category, Exercise.name)).all()


@app.get("/api/workout-plans", response_model=list[WorkoutPlanResponse], tags=["Workout Plans"])
def list_workout_plans(
    upcoming_only: bool = False,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = select(WorkoutPlan).options(
        selectinload(WorkoutPlan.exercises).selectinload(WorkoutPlanExercise.exercise)
    ).where(WorkoutPlan.user_id == user.id)
    if upcoming_only:
        query = query.where(WorkoutPlan.scheduled_date >= date.today())
    plans = db.scalars(query.order_by(WorkoutPlan.scheduled_date, WorkoutPlan.id)).all()
    return [plan_response(plan) for plan in plans]


@app.post(
    "/api/workout-plans",
    response_model=WorkoutPlanResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Workout Plans"],
)
def create_workout_plan(
    payload: WorkoutPlanCreate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    exercise_ids = set(payload.exercise_ids)
    exercises = db.scalars(select(Exercise).where(Exercise.id.in_(exercise_ids))).all() if exercise_ids else []
    if len(exercises) != len(exercise_ids):
        raise HTTPException(status_code=422, detail="One or more selected exercises do not exist")
    plan = WorkoutPlan(
        user_id=user.id,
        title=payload.title.strip(),
        description=payload.description.strip(),
        scheduled_date=payload.scheduled_date,
        exercises=[WorkoutPlanExercise(exercise=exercise) for exercise in exercises],
    )
    db.add(plan)
    db.commit()
    db.refresh(plan)
    loaded_plan = db.scalar(
        select(WorkoutPlan)
        .options(selectinload(WorkoutPlan.exercises).selectinload(WorkoutPlanExercise.exercise))
        .where(WorkoutPlan.id == plan.id, WorkoutPlan.user_id == user.id)
    )
    if loaded_plan is None:
        raise RuntimeError("Created workout plan could not be reloaded")
    return plan_response(loaded_plan)


@app.delete("/api/workout-plans/{plan_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Workout Plans"])
def delete_workout_plan(
    plan_id: int,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    plan = db.scalar(select(WorkoutPlan).where(WorkoutPlan.id == plan_id, WorkoutPlan.user_id == user.id))
    if plan is None:
        raise HTTPException(status_code=404, detail="Workout plan not found")
    db.delete(plan)
    db.commit()


@app.get("/api/streak", response_model=StreakResponse, tags=["Achievements"])
def get_streak(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return streak_response(db, user.id)


@app.get("/api/badges", response_model=list[BadgeResponse], tags=["Achievements"])
def get_badges(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    return badge_responses(db, user.id)


@app.get("/api/reports/comparison", response_model=ComparisonResponse, tags=["Reports"])
def compare_progress(
    period: str = Query(default="weekly", pattern="^(weekly|monthly)$"),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    today = date.today()
    if period == "weekly":
        current_start = today - timedelta(days=today.weekday())
        current_end = current_start + timedelta(days=6)
        previous_start = current_start - timedelta(days=7)
        previous_end = current_start - timedelta(days=1)
    else:
        current_start = today.replace(day=1)
        previous_end = current_start - timedelta(days=1)
        previous_start = previous_end.replace(day=1)
        current_end = date(today.year, today.month, monthrange(today.year, today.month)[1])
    current = report_for_range(db, user.id, current_start, current_end)
    previous = report_for_range(db, user.id, previous_start, previous_end)
    return ComparisonResponse(
        period=period,
        current=current,
        previous=previous,
        workout_change=current.total_workouts - previous.total_workouts,
        calorie_change=current.total_calories - previous.total_calories,
        duration_change=current.total_duration - previous.total_duration,
    )


@app.get("/api/dashboard", response_model=DashboardResponse, tags=["Dashboard"])
def personalized_dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    today = date.today()
    plans = db.scalars(
        select(WorkoutPlan)
        .options(selectinload(WorkoutPlan.exercises).selectinload(WorkoutPlanExercise.exercise))
        .where(
            WorkoutPlan.user_id == user.id,
            WorkoutPlan.scheduled_date >= today,
        )
        .order_by(WorkoutPlan.scheduled_date, WorkoutPlan.id)
        .limit(5)
    ).all()
    goals = db.scalars(select(Goal).where(Goal.user_id == user.id).order_by(Goal.deadline)).all()
    return DashboardResponse(
        today=report_for_range(db, user.id, today, today),
        upcoming_workouts=[plan_response(plan) for plan in plans],
        goals=[goal_response(goal) for goal in goals],
        streak=streak_response(db, user.id),
        badges=badge_responses(db, user.id),
    )
