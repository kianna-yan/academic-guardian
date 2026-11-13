export type Level = "red" | "yellow" | "green";
export type Role = "student" | "counselor" | "admin" | "parent" | "teacher";

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

/** 门户首屏左侧栏：三个数字 + 三条焦点 */
export interface PortalSummary {
  stats: { label: string; value: number }[];
  focus: { tag: string; title: string; meta: string }[];
  focus_title: string;
  model: string;
  /** 意图路由用的快模型（glm-4.5-air），作答模型是 model（glm-5.3-flash） */
  model_route?: string;
  /** 后端是否真的配了 key；没配时徽标写「规则兜底」，别和黄条自相矛盾 */
  model_online?: boolean;
}

export interface Citation {
  citation: string;
  title?: string;
  text: string;
  score?: number;
  school?: string;
  /** 相关度百分比，如 "78%"，检索打分的归一化结果 */
  score_pct?: string;
  /** 命中原因：标题命中 / 语义相近 / 同义扩展命中 */
  why?: string;
  kind?: string;
  doc?: string;
  snippet?: string;
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
  llm: { enabled: boolean; model: string; base_url: string; route_model?: string };
  term: string;
  week: number;
  demo: { student: string; parent: string; counselor: string; teacher?: string };
  student_count: number;
  updated_at: string;
}

export interface ChatTrace {
  tool: string;
  args: Record<string, unknown>;
  ms: number;
  /** 人话标签：多媒体/记忆类步骤自带，前端优先用它 */
  label?: string;
  detail?: string;
  /** 检索明细：改写后的查询、走哪条通道、每条命中多少分 */
  retrieval?: {
    query: string;
    rewritten?: string;
    added_terms?: string[];
    channel?: string;
    candidates?: number;
    ms?: number;
    hits?: { rank: number; path: string; school?: string; score?: string; why?: string }[];
  };
  /** 学生本人档案的检索结果：每轮回答前实时重查，字段与来源逐条列出 */
  profile?: {
    who: string;
    sid: string;
    /** 本人 / 孩子 / 该生 */
    scope: string;
    query?: string;
    /** 这一问实际点到的字段名 */
    fields?: string[];
    items?: { key: string; label: string; value: string; source: string; hit?: boolean }[];
    brief?: string;
    as_of?: string;
    ms?: number;
  };
  evidence?: {
    source?: string;
    table?: string;
    rows?: number;
    unit?: string;
    ts?: string;
    ms?: number;
    detail?: string;
  };
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

/** 输入框「+ → Skill」里的一项。ext 为空表示这类技能不产出文件（图表解读）。 */
/** 技能的二级项：文书的类型、家长的类型 */
export interface SkillSub {
  key: string;
  name: string;
  desc: string;
}

export interface SkillMeta {
  key: string;
  name: string;
  icon: string;
  desc: string;
  ext: string | null;
  hint: string;
  /** file=出文件 / image=开图片选择 / draft=按模板起草 / roleplay=进入演练 */
  kind: "file" | "image" | "draft" | "roleplay";
  /** 合规提示，例如「只起草，不代提交」 */
  note?: string;
  subs?: SkillSub[];
}

/** 上传文档解析结果：正文已经抽成纯文本，前端当 text 附件随提问发出 */
export interface UploadedDoc {
  ok: boolean;
  name: string;
  chars: number;
  text: string;
  note?: string;
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

/* ------------------------------------------------------------------
 * 家长端 ↔ 辅导员端 双向消息
 * ---------------------------------------------------------------- */
export interface MessageMedia {
  kind: "image" | "audio" | "text";
  name?: string;
  mime?: string;
  /** 图片 / 语音的 dataURL */
  data?: string;
  duration?: number;
  transcript?: string;
}

export interface MessageItem {
  id: string;
  thread_id: string;
  sid: string;
  from_role: "parent" | "counselor";
  from_name: string;
  to_role: "parent" | "counselor";
  to_name: string;
  text: string;
  ts: string;
  read: boolean;
  /** 照片 / 语音：家长拍张作业照片或按住说一段话 */
  media?: MessageMedia[];
}

export interface MessageThread {
  thread_id: string;
  sid: string;
  peer_name: string;       // 对方显示名
  peer_role: "parent" | "counselor";
  peer_phone?: string;     // 对方联系方式：家长端=辅导员电话，导员端=对应家长电话
  last_text: string;
  last_ts: string;
  unread: number;
  messages: MessageItem[];
  // 导员端列表用：学生风险信息（按风险排序展示，没消息的学生也能看到）
  student_name?: string;
  student_class?: string;
  level?: "red" | "yellow" | "green";
  score?: number;
  top_factor?: string;
}

/* ------------------------------------------------------------------
 * 教师端：任课老师视角的课堂学情
 * ---------------------------------------------------------------- */
export interface TeacherCourseBrief {
  code: string;
  name: string;
  credit?: number;
  kind?: string;
  period?: string;
  teacher?: string;
}

export interface TeacherStudentRow {
  id: string;
  name: string;
  class_name: string;
  score: number;
  level: Level;
  level_label: string;
  top_factor: string;
  courses: {
    code: string;
    name: string;
    midterm?: number | null;
    absent: number;
    late?: number;
    sessions_held?: number;
    hw_submitted: number;
    hw_assigned: number;
    cohort_avg?: number | null;
    attendance?: AttendanceRecord[];
    homework?: HomeworkRecord[];
  }[];
}

export interface TeacherView {
  teacher: string;
  courses: TeacherCourseBrief[];
  students: TeacherStudentRow[];
}

/* ------------------------------------------------------------------
 * 教师上传资源（历年真题 / 网课）
 * ---------------------------------------------------------------- */
export interface TeacherResource {
  id: string;
  kind: "exam" | "tutorial";
  filename: string;
  size: number;
  course?: string;
  class_name?: string;
  note?: string;
  teacher: string;
  created_at: string;
  /** 外链型网课（如中国大学 MOOC 课程页）：有值时点「去观看」直接跳转，没有文件本体 */
  url?: string;
  /** 是否已进 AI 知识库（上传时自动解析入库） */
  kb?: {
    ok: boolean;
    note?: string;
    doc?: string;
    chars?: number;
    sections?: number;
  };
}

/* ------------------------------------------------------------------
 * 教师端课堂学情：以「我教的这门课」为单位统计（/api/teacher/classroom）
 * ---------------------------------------------------------------- */
export interface ScoreBand {
  label: string;
  count: number;
  pct: number;
}

export interface ClassRoomRow {
  class_name: string;
  students: number;
  mid_avg: number;
  /** 与本课均分之差，负数=落后 */
  gap: number;
  hw_rate: number;
  absent_rate: number;
  absent: number;
  late: number;
  low: number;
}

export interface WeekAttend {
  week: number;
  absent: number;
  late: number;
  present: number;
  total: number;
}

export interface HwItem {
  id: string;
  title: string;
  due: string;
  assigned: string;
  submitted: number;
  late: number;
  missing: number;
  total: number;
  rate: number;
  ontime_rate: number;
}

export interface ClassCourse {
  code: string;
  name: string;
  credit?: number;
  kind?: string;
  period?: string;
  students: number;
  mid_avg: number;
  /** 全校同一门课的均分（与 mid_avg 同群体，仅供对照留档） */
  cohort_avg: number | null;
  /** 年级六门课学分加权总均分 */
  grade_avg: number;
  /** 本课均分 − 年级总均分：正数=这门课给分偏松/学生学得好 */
  gap_grade: number;
  median: number;
  highest: number;
  lowest: number;
  std: number;
  pass_rate: number;
  dist: ScoreBand[];
  risk: { red: number; yellow: number; green: number };
  attend: { sessions: number; absent: number; late: number; rate: number; weekly: WeekAttend[] };
  hw: { assigned: number; submitted: number; rate: number; items: HwItem[] };
  classes: ClassRoomRow[];
}

export interface ClassroomStudent {
  id: string;
  name: string;
  class_name: string;
  score: number;
  level: Level;
  level_label: string;
  top_factor: string;
  code: string;
  course: string;
  midterm: number | null;
  cohort_avg: number | null;
  /** 与课堂均分之差 */
  gap: number;
  absent: number;
  late: number;
  sessions_held: number;
  hw_submitted: number;
  hw_assigned: number;
  hw_missing: number;
  /** 课堂内期中排名 */
  rank: number;
  rank_total: number;
  /** 最长连续旷课次数 */
  absent_streak: number;
  attendance: AttendanceRecord[];
  homework: HomeworkRecord[];
}

export interface ClassroomTodo {
  id: string;
  kind: "homework" | "attendance" | "grade" | "risk";
  tone: "red" | "amber" | "ok";
  title: string;
  detail: string;
  names: string[];
  sids: string[];
  action: string;
}

export interface TeacherClassroom {
  teacher: TeacherProfile & { employee_id?: string };
  term: string;
  week: number;
  courses: ClassCourse[];
  students: ClassroomStudent[];
  todos: ClassroomTodo[];
  summary: string;
}

/* ------------------------------------------------------------------
 * 课表 / 课后自评 / 学习轨迹
 * 三块共用「一节课」这个单位：课表是它摆在哪，自评是它的状态，
 * 轨迹是把这些状态按时间连起来看走向。
 * ---------------------------------------------------------------- */
export type Understand = "full" | "fuzzy" | "lost";

export interface LessonSlot {
  course: string;
  name: string;
  teacher: string;
  kind: string;
  credit: number;
  room: string;
  date: string;
  week: number;
  weekday: number;
  weekday_label: string;
  period: string;
  index: number;
  /** 已经上过（含今天）＝可以记录 */
  held: boolean;
  today: boolean;
  recorded: boolean;
  state: Understand | "";
  state_label: string;
  break_label: string;
  point: string;
  plan_label: string;
  note: string;
  checkin_id: string;
}

export interface TimetablePayload {
  week: number;
  weeks: { min: number; max: number; current: number };
  today: string;
  term: string;
  days: { key: number; label: string; date: string; today: boolean }[];
  periods: string[];
  cells: Record<string, LessonSlot[]>;
  slots: LessonSlot[];
  today_sessions: LessonSlot[];
  stats: { total: number; held: number; checked: number; pending: number };
  courses: { code: string; name: string; teacher: string; room: string; kind: string; credit: number }[];
}

export interface CheckinRecord {
  id: string;
  course: string;
  course_name: string;
  teacher?: string;
  room?: string;
  date: string;
  week: number;
  weekday?: string;
  period: string;
  state: Understand;
  state_label: string;
  break_label: string;
  minute_from: number;
  point: string;
  plan: string;
  plan_label: string;
  note: string;
  updated_at: string;
}

export interface CheckinList {
  rows: CheckinRecord[];
  persistent: boolean;
  states: Record<Understand, { label: string; short: string; level: number }>;
  break_options: { key: string; label: string }[];
  plans: Record<string, string>;
  points: Record<string, string[]>;
}

export interface TrackPoint {
  index: number;
  date: string;
  week: number;
  weekday: string;
  period: string;
  state: Understand | "";
  recorded: boolean;
  minute_from: number;
  break_label: string;
  point: string;
  plan: string;
  plan_label: string;
  note: string;
  id: string;
  updated_at: string;
}

export interface TrackBreak {
  start_index: number;
  end_index: number;
  count: number;
  start_week: number;
  start_date: string;
  end_date: string;
  point: string;
  minute_from: number;
  open: boolean;
  /** 接上的那一节在 points 里的位置（没有就是 null） */
  recovered_index?: number | null;
  recovered_week?: number | null;
  recovered_date?: string;
  state_after?: string;
}

export interface TrackCourse {
  code: string;
  name: string;
  teacher: string;
  teacher_profile: TeacherProfile;
  period: string;
  room: string;
  kind: string;
  credit: number;
  points: TrackPoint[];
  segments: { state: Understand | "none"; from: number; to: number; count: number; dates: string[] }[];
  breaks: TrackBreak[];
  open_breaks: number;
  fixed_breaks: number;
  held: number;
  recorded: number;
  full: number;
  fuzzy: number;
  lost: number;
  status: "break" | "watch" | "ok" | "empty";
  line: string;
  latest: TrackPoint | null;
}

export interface TrackPayload {
  courses: TrackCourse[];
  timeline: CheckinRecord[];
  due: {
    course: string;
    course_name: string;
    teacher: string;
    room: string;
    date: string;
    week: number;
    weekday: string;
    period: string;
    today: boolean;
  }[];
  advice: {
    kind: string;
    course: string;
    course_name: string;
    title: string;
    text: string;
    who: string;
    office_hour: string;
    email: string;
  }[];
  stats: {
    held: number;
    recorded: number;
    coverage: number;
    open_breaks: number;
    fixed_breaks: number;
    due: number;
    week: number;
    week_due: number;
    week_done: number;
    streak: number;
    courses: number;
    today: string;
  };
  meta: { week: number; term: string; persistent: boolean };
}

/* ------------------------------------------------------------------ */
/* 成绩分配试算：每门课一套考核构成，学生自己调每一项能拿多少分        */
/* ------------------------------------------------------------------ */
export interface SimComponent {
  key: string;
  label: string;
  short: string;
  weight: number;
  base: number;
  basis: string;
}

export interface SimCourse {
  code: string;
  name: string;
  teacher: string;
  credit: number;
  kind: string;
  scheme: string;
  scheme_label: string;
  components: SimComponent[];
  base_total: number;
  base_level: string;
  base_level_label: string;
  needed_final: number;
  fail_probability: number;
  cohort_avg: number | null;
}

export interface SimPlan {
  scores: Record<string, number>;
  weights: Record<string, number>;
}

export interface SimPayload {
  student: { id: string; name: string; class_name: string; term: string };
  pass_line: number;
  final_guard: number;
  courses: SimCourse[];
  /** 五套考核权重方案：A/B/C/D/E，每门课按性质各取一套 */
  schemes: Record<
    string,
    { label: string; components: { key: string; short: string; weight: number }[] }
  >;
  base: {
    avg: number;
    gpa: number;
    credits: number;
    failing: number;
    failing_codes: string[];
    level: string;
  };
  saved: { plans: Record<string, SimPlan>; saved_at: string | null };
  persistent: boolean;
}

/* ------------------------------------------------------------------ */
/* 智慧树：一颗果实一门课                                              */
/* ------------------------------------------------------------------ */

/** 水肥账：一个口径的"该做多少 / 做了多少 / 做得怎么样" */
export interface FruitLedger {
  /** 该做的量（作业=已截止次数；到课=已上节数） */
  due: number;
  /** 实际完成的量（迟到按 0.5 / 0.6 折算前的条数） */
  done: number;
  /** 真实完成率 0–1（标签上显示的那个百分比） */
  rate: number;
  /** 有效投入：含质量系数折算，用于生长 */
  eff: number;
}

export interface TreeFruit {
  code: string;
  name: string;
  credit: number;
  score: number;
  fail: number;
  status: "great" | "ok" | "watch" | "risk";
  /** 树上第几个挂点；不传则按数组顺序 */
  slot?: number;
  /**
   * 肥料成熟度 0.45–1.0。
   * = 0.45 + 0.55 × 有效施肥 ÷ 已截止作业数
   * 分母用真实次数、不做平滑：作业留得少的课交齐了就该熟，否则"留得少"反而成了它长不大的理由。
   */
  maturity: number;
  /** 肥：作业账。null = 该课没有作业，改按到课与随堂折算 */
  hw: FruitLedger | null;
  /** 水：到课账（果实小标签里的"根"，也决定树干） */
  attend: FruitLedger;
  /** 果柄上的叶片数 = 学分 */
  leaves: number;
}
