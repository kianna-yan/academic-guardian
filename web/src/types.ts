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

export interface TeacherProfile {
  name: string;
  title?: string;
  dept?: string;
  office?: string;
  email?: string;
  phone?: string;
  office_hour?: string;
  note?: string;
}

/** 一节课的考勤：学生端要能指着某一天问"这天为什么算我旷课" */
export interface AttendanceRecord {
  date: string;
  weekday: string;
  week: number;
  period: string;
  status: "present" | "late" | "absent";
  note: string;
}

export interface HomeworkRecord {
  id: string;
  title: string;
  brief: string;
  assigned: string;
  due: string;
  status: "submitted" | "late" | "missing";
  submitted_at: string;
}

export interface Course {
  code: string;
  name: string;
  teacher: string;
  credit: number;
  kind?: string;
  period?: string;
  midterm: number;
  absent: number;
  late?: number;
  sessions_held?: number;
  hw_submitted: number;
  hw_assigned: number;
  attendance?: AttendanceRecord[];
  homework?: HomeworkRecord[];
  teacher_profile?: TeacherProfile;
}

/** 教务新导入、本学期学生还没选上的课 */
export interface ExtraCourse {
  code: string;
  name: string;
  credit: number;
  kind: string;
  teacher: string;
  period: string;
  status: string;
  teacher_profile?: TeacherProfile;
}

export interface CurriculumCourse {
  code: string;
  name: string;
  credit: number;
  kind: string;
  teacher: string;
  period: string;
  teacher_profile?: TeacherProfile;
}

export interface CurriculumPayload {
  courses: CurriculumCourse[];
  teachers: TeacherProfile[];
  updated_at: string;
  persistent: boolean;
}

export interface CurriculumImportResult {
  ok: boolean;
  total: number;
  ok_count: number;
  updated: number;
  added: number;
  failed: { line: number; text: string; reason: string }[];
  persistent: boolean;
  updated_at: string;
}

export interface Action {
  factor: string;
  title: string;
  detail: string;
  owner: string;
  deadline: string;
  priority: "high" | "medium" | "low";
  /** 动作类型标签：补课优先 / 改作息 / 先定性质 …… */
  tag?: string;
  /** 拆到"今天就能做"的具体步骤 */
  steps?: string[];
  /** 这个因子在风险分里贡献了多少 */
  points?: number;
}

/** 一名学生的个性化干预方案：先定性质，再给证据和动作 */
export interface AdvicePlan {
  pattern: string;
  pattern_label: string;
  diagnosis: string;
  evidence: string[];
  headline: string;
  one_liner: string;
  /** 归因动作：说明性质、以及从哪一步开始 */
  root?: Action | null;
  first_steps: string[];
  actions: Action[];
  support: { kind: string; text: string; contact: string }[];
  watch: { when: string; what: string };
  counselor_tip: string;
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

/** 一个学期的成绩点：前四个学期是总评，最后一个是本学期期中（口径不同，图上单独标） */
export interface TermScore {
  term: string;
  label: string;
  status: "final" | "ongoing";
  avg: number;
  gpa: number | null;
  rank: number | null;
  rank_total: number | null;
  credits: number;
  failed: number | null;
  cohort_avg: number | null;
  cohort_gpa: number | null;
  note: string;
}

/** 本学期的一次测评（随堂测或期中） */
export interface AssessPoint {
  label: string;
  short: string;
  date: string;
  week: number;
  kind: "quiz" | "exam";
  score: number;
}

export interface CourseTrend {
  code: string;
  name: string;
  teacher: string;
  credit: number;
  midterm: number;
  cohort_avg: number | null;
  points: AssessPoint[];
  first: number;
  last: number;
  delta: number;
  best: number;
  worst: number;
  trend: "up" | "down" | "flat";
  trend_label: string;
}

export interface GradeTrend {
  terms: TermScore[];
  courses: CourseTrend[];
  slope: {
    per_term: number;
    total: number;
    direction: "up" | "down" | "flat";
    label: string;
    up_streak: number;
    down_streak: number;
    first_label: string;
    last_final_label: string;
  };
  now: {
    avg: number;
    cohort_avg: number | null;
    gap: number;
    rank: number | null;
    rank_total: number | null;
    status: "final" | "ongoing";
    note: string;
  };
  rank: { from: number | null; to: number | null; delta: number; total: number | null };
  summary: string;
  watch: string;
  worst_code: string;
}

export interface StudentDetail {
  student: StudentProfile;
  risk: Risk;
  courses: Course[];
  extra_courses?: ExtraCourse[];
  actions: Action[];
  advice?: AdvicePlan;
  grade_trend?: GradeTrend;
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
  /** 成因分型：基础薄弱 / 投入不足 / 状态异常 …… */
  pattern: string;
  pattern_label: string;
  /** 名单上一句话建议 */
  advice: string;
  advice_tag: string;
  /** 五学期均分序列，名单上画迷你走势线用 */
  trend_points: number[];
  /** 班级名次变化：正数 = 名次后退（变差） */
  trend_rank_delta: number;
  /** 当前班级名次（本学期期中口径） */
  trend_rank: number | null;
  trend_rank_total: number | null;
  trend_direction: "up" | "down" | "flat";
  trend_label: string;
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

/** 登录后的身份：四个端各自独立，学生/家长绑定学号，教职工绑定工号 */
export interface AuthProfile {
  role: Role;
  account: string;
  sid: string | null;
  name: string;
  class_name: string;
  advisor: string;
  must_change: boolean;
}

export interface LoginResult {
  ok: boolean;
  token: string;
  profile: AuthProfile;
  initial_password: string;
}

export interface AccountRow {
  sid: string;
  name: string;
  class_name: string;
  is_default: boolean;
  created_at: string;
}

export interface ImportResult {
  ok: boolean;
  created: number;
  reset: number;
  failed: { line: number; sid: string; reason: string }[];
  failed_count: number;
  accounts: AccountRow[];
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
  /** 思考链：这轮在说谁、为什么走这条路 */
  thoughts?: string[];
  elapsed_ms: number;
  suggestions: string[];
}

/** 智能体主动简报：各端进页面时它先开口 */
export interface AgentBriefing {
  greeting: string;
  points: { label: string; text: string; tone: string }[];
  asks: string[];
}

/* ------------------------------------------------------------------
 * 消息中心：四端通知 / 待办 / 学生异议
 * ---------------------------------------------------------------- */
export type NoticeKind = "absent" | "homework" | "risk" | "appeal_new" | "appeal_reply";

export interface NoticeItem {
  id: string;
  kind: NoticeKind;
  title: string;
  text: string;
  ts: string;
  read: boolean;
  meta: Record<string, string>;
}

export interface TodoItem {
  id: string;
  kind: string;
  title: string;
  detail: string;
  ts: string;
  done: boolean;
  meta: Record<string, string>;
}

export interface AppealItem {
  id: string;
  sid: string;
  name: string;
  class_name: string;
  advisor: string;
  kind: "attendance" | "homework";
  record_id: string;
  course: string;
  reason: string;
  ts: string;
  status: "pending" | "accepted" | "rejected";
  reply: string;
}

export interface NoticePayload {
  unread: NoticeItem[];
  todos: TodoItem[];
  counts: { unread: number; todo: number; appeals_pending?: number };
  appeals?: AppealItem[];
}
