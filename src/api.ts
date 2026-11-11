const API_BASE = import.meta.env.VITE_API_URL ?? "/api";

export type User = { id: number; username: string; email: string; created_at: string };
export type Workout = {
  id: number;
  user_id: number;
  workout_name: string;
  category: "Cardio" | "Strength" | "Yoga";
  duration: number;
  calories_burned: number;
  workout_date: string;
  created_at: string;
};
export type ProgressDay = {
  date: string;
  total_workouts: number;
  total_calories: number;
  total_duration: number;
};
export type Goal = {
  id: number;
  user_id: number;
  goal_type: "Weight Loss" | "Muscle Gain" | "Steps";
  target_value: number;
  current_value: number;
  deadline: string;
  created_at: string;
  status: "active" | "completed" | "overdue";
};
export type Notification = {
  id: number;
  title: string;
  message: string;
  is_read: boolean;
  created_at: string;
};
export type Report = {
  start_date: string;
  end_date: string;
  total_workouts: number;
  total_calories: number;
  total_duration: number;
  days: ProgressDay[];
};
export type Exercise = {
  id: number;
  name: string;
  category: Workout["category"];
  description: string;
  duration: number;
};
export type WorkoutPlan = {
  id: number;
  user_id: number;
  title: string;
  description: string;
  scheduled_date: string;
  created_at: string;
  exercises: Exercise[];
};
export type Streak = {
  current_streak: number;
  longest_streak: number;
  last_workout_date: string | null;
};
export type Badge = {
  id: number;
  name: string;
  description: string;
  icon: string;
  earned_at: string | null;
};
export type Comparison = {
  period: "weekly" | "monthly";
  current: Report;
  previous: Report;
  workout_change: number;
  calorie_change: number;
  duration_change: number;
};
export type DashboardData = {
  today: Report;
  upcoming_workouts: WorkoutPlan[];
  goals: Goal[];
  streak: Streak;
  badges: Badge[];
};
export type WorkoutInput = Omit<Workout, "id" | "user_id" | "created_at">;
export type GoalInput = Pick<Goal, "goal_type" | "target_value" | "current_value" | "deadline">;
export type TokenResponse = { access_token: string; token_type: string; user: User };

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

export async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const headers = new Headers(options.headers);
  if (options.body instanceof URLSearchParams) {
    headers.set("Content-Type", "application/x-www-form-urlencoded");
  } else if (!(options.body instanceof FormData)) {
    headers.set("Content-Type", "application/json");
  }
  const token = localStorage.getItem("fittrack_token");
  if (token) headers.set("Authorization", `Bearer ${token}`);

  const response = await fetch(`${API_BASE}${path}`, { ...options, headers });
  if (!response.ok) {
    let message = `Request failed (${response.status})`;
    try {
      const data = (await response.json()) as { detail?: string };
      message = data.detail ?? message;
    } catch {
      // Keep the HTTP status message when the server response is not JSON.
    }
    throw new ApiError(message, response.status);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function send<T>(path: string, method: string, body?: unknown): Promise<T> {
  return request<T>(path, {
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
}
