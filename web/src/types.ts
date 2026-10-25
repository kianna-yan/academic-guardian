export type Level = "red" | "yellow" | "green";
export type Role = "student" | "counselor" | "admin" | "parent";

export interface Factor {
  key: string;
  label: string;
  value: number;
  weight: number;
  points: number;
}

export interface RawMetrics {
  absence_ratio: number;
  absent: number;
  sessions: number;
  miss_ratio: number;
  hw_submitted: number;
  hw_assigned: number;
  mid_avg: number;
  cohort_avg: number;
  z: number;
  credits_deficit: number;
}

export interface Trend {
  last_score: number;
  delta: number;
  label: string;
  direction: "up" | "down" | "flat";
}

export interface CourseFail {
  code: string;
  name: string;
  cohort_avg: number;
  fail_probability: number;
}

export interface Risk {
  student_id: string;
  score: number;
  raw_score: number;
  level: Level;
  level_label: string;
  factors: Factor[];
  raw: RawMetrics;
  overrides: string[];
  trend: Trend;
  pass_probability: CourseFail[];
}

export interface Course {
  code: string;
  name: string;
  teacher: string;
  credit: number;
  midterm: number;
  absent: number;
  hw_submitted: number;
  hw_assigned: number;
}

export interface Action {
  factor: string;
  title: string;
  detail: string;
  owner: string;
  deadline: string;
  priority: "high" | "medium";
}

export interface Intervention {
  id: number;
  title: string;
  status: string;
  note: string;
  created_at: string;
}

export interface StudentProfile {
  id: string;
  name: string;
  gender: string;
  class_name: string;
  major: string;
  grade: string;
  advisor: string;
  term: string;
  credits: { earned: number; plan_total: number };
  history: { gpa: number; failed_credits: number };
  engagement: { weekly_logins: number; video_rate: number; days_since_active: number };
}

export interface StudentDetail {
  student: StudentProfile;
  risk: Risk;
  courses: Course[];
  actions: Action[];
  interventions: Intervention[];
}

export interface RosterRow {
  id: string;
  name: string;
  class_name: string;
  gender: string;
  score: number;
  level: Level;
  level_label: string;
  delta: number;
  direction: "up" | "down" | "flat";
  top_factor: string;
  absent: number;
  missed_hw: number;
  mid_avg: number;
  advisor: string;
}

export interface ClassStat {
  total: number;
  red: number;
  yellow: number;
  avg_score: number;
}

export interface Overview {
  total: number;
  dist: Record<Level, number>;
  dist_pct: Record<Level, number>;
  by_class: Record<string, ClassStat>;
  top_factors: { label: string; points: number }[];
  rising_count: number;
  avg_score: number;
  updated_at: string;
}

export interface Citation {
  citation: string;
  title?: string;
  text: string;
  score?: number;
  school?: string;
}

export interface Letter {
  title: string;
  subject: string;
  body: string;
  citations?: Citation[];
}

export interface RoleMeta {
  key: Role;
  name: string;
  desc: string;
}

export interface Meta {
  roles: RoleMeta[];
  classes: string[];
  schools: string[];
  config: {
    red_line: number;
    yellow_line: number;
    weights: Record<string, number>;
    policy: {
      warn_failed_credits: number;
      downgrade_failed_credits: number;
      absence_warn_ratio: number;
      midterm_fail_trigger: number;
    };
    school?: string;
  };
  llm: { enabled: boolean; model: string; base_url: string };
  term: string;
  week: number;
  demo: { student: string; parent: string; counselor: string };
  student_count: number;
  updated_at: string;
}

export interface ChatTrace {
  tool: string;
  args: Record<string, unknown>;
  ms: number;
}

export interface ChatAnswer {
  reply: string;
  intent: string;
  citations: Citation[];
  trace: ChatTrace[];
  elapsed_ms: number;
  suggestions: string[];
}
