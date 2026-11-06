<script setup lang="ts">
import { computed } from "vue";
import type { RosterRow } from "@/types";

/**
 * 辅导员端「智慧森林」：每个学生一棵树，每个班一片森林。
 * 树的形态按本学期风险等级分三态：
 * - green（正常）：茂盛绿冠，长势好
 * - yellow（关注）：黄叶，部分开始落
 * - red（预警）：枯枝 + 红色警示果，需要尽快干预
 *
 * 不替代风险名单——名单按分数排序，森林按班级分组；
 * 名单回答“谁最该找”，森林回答“这个班整体长成什么样”。
 */
const props = defineProps<{ rows: RosterRow[] }>();
const emit = defineEmits<{ (e: "select", sid: string): void }>();

/**
 * 点一棵树：把该学生的 sid 抛给父组件，由父组件打开学生详情抽屉。
 * 抽屉里会显示风险因素、成绩走势、考勤作业明细——森林回答“整体长成什么样”，
 * 点进去回答“这棵树怎么了、该怎么办”。
 */
function pick(sid: string) {
  emit("select", sid);
}

type Classed = { class_name: string; trees: RosterRow[] };

const forests = computed<Classed[]>(() => {
  const map = new Map<string, RosterRow[]>();
  for (const r of props.rows) {
    const key = r.class_name || "未分班";
    if (!map.has(key)) map.set(key, []);
    map.get(key)!.push(r);
  }
  // 班内按风险等级降序排（红 → 黄 → 绿），让需要关注的学生排在前排
  const order = { red: 0, yellow: 1, green: 2 };
  return [...map.entries()].map(([class_name, trees]) => ({
    class_name,
    trees: trees.sort((a, b) => order[a.level] - order[b.level]),
  }));
});

// 每个班的统计：让辅导员一眼看到这个班的整体健康度
function classStat(trees: RosterRow[]) {
  const red = trees.filter((t) => t.level === "red").length;
  const yellow = trees.filter((t) => t.level === "yellow").length;
  const green = trees.filter((t) => t.level === "green").length;
  const total = trees.length;
  const health = total ? Math.round((green / total) * 100) : 0;
  return { red, yellow, green, total, health };
}

const LEVEL_LABEL = { red: "红色预警", yellow: "黄色关注", green: "状态正常" } as const;
</script>

<template>
  <div class="forest-wrap">
    <p class="forest-intro muted">
      每个学生一棵树，按本学期风险分形态：茂盛绿树为状态正常，黄叶为黄色关注，枯枝带红果为红色预警。
      班级整体长势就是这一片森林的颜色分布。
    </p>

    <div v-if="!forests.length" class="forest-empty">还没有学生数据，先在「风险名单」加载名单。</div>

    <div v-for="f in forests" :key="f.class_name" class="forest-card">
      <div class="forest-head">
        <h3>{{ f.class_name }}</h3>
        <div class="forest-stat">
          <span class="stat-pill green"><i></i>{{ classStat(f.trees).green }}</span>
          <span class="stat-pill yellow"><i></i>{{ classStat(f.trees).yellow }}</span>
          <span class="stat-pill red"><i></i>{{ classStat(f.trees).red }}</span>
          <span class="stat-health">
            健康度 <b>{{ classStat(f.trees).health }}%</b>
          </span>
        </div>
      </div>

      <div class="forest-grid">
        <button
          v-for="t in f.trees"
          :key="t.id"
          type="button"
          class="tree"
          :class="t.level"
          :title="`${t.name} · ${LEVEL_LABEL[t.level]} · 风险分 ${t.score} · ${t.top_factor}（点击查看详情）`"
          @click="pick(String(t.id))"
        >
          <!-- 树形 SVG：64x84 viewBox，按 level 切换形态。
               统一结构 = 地面阴影 + 锥度树干（带侧面高光）+ 树冠/枯枝。 -->
          <svg viewBox="0 0 64 84" class="tree-svg" aria-hidden="true">
            <!-- 地面阴影：让树像"长在地上"而不是飘着 -->
            <ellipse cx="32" cy="79" rx="15" ry="3.2" fill="#4a3a22" opacity="0.1" />

            <!-- 树干：底部宽、往上收，右侧一道高光做出圆柱感 -->
            <path
              d="M29.2 78 C29.6 68 30.2 58 30.4 50 L33.6 50 C33.8 58 34.4 68 34.8 78 Z"
              :fill="t.level === 'red' ? '#7c5a3a' : '#8a5a2b'"
            />
            <path
              d="M30.7 78 C31 68 31.4 58 31.6 50 L32.4 50 C32.4 58 32.2 68 32 78 Z"
              :fill="t.level === 'red' ? '#96714c' : '#a97038'"
              opacity="0.75"
            />

            <!-- green：茂盛圆冠，三层叠加 + 高光 + 小果实 -->
            <template v-if="t.level === 'green'">
              <circle cx="32" cy="33" r="19" fill="#15803d" />
              <circle cx="22" cy="30" r="11.5" fill="#17604f" />
              <circle cx="42" cy="29" r="10.5" fill="#17604f" />
              <circle cx="32" cy="21" r="12" fill="#22c55e" />
              <circle cx="25" cy="25" r="7" fill="#4ade80" opacity="0.9" />
              <circle cx="39" cy="35" r="6" fill="#4ade80" opacity="0.45" />
              <circle cx="23" cy="37" r="2.6" fill="#f59e0b" />
              <circle cx="22.2" cy="36.2" r="1" fill="#fde68a" opacity="0.85" />
              <circle cx="40" cy="25" r="2.4" fill="#f97316" />
              <circle cx="39.3" cy="24.3" r="0.9" fill="#fed7aa" opacity="0.85" />
              <circle cx="35" cy="42" r="2.2" fill="#fbbf24" />
            </template>

            <!-- yellow：黄叶树，冠形略散 + 飘落叶片 -->
            <template v-else-if="t.level === 'yellow'">
              <circle cx="32" cy="34" r="18.5" fill="#c2740a" />
              <circle cx="23" cy="30" r="11" fill="#a9681f" />
              <circle cx="41" cy="29" r="10" fill="#e8890c" />
              <circle cx="32" cy="22" r="11.5" fill="#f59e0b" />
              <circle cx="26" cy="26" r="6.5" fill="#fbbf24" opacity="0.9" />
              <circle cx="39" cy="37" r="5" fill="#fcd34d" opacity="0.5" />
              <path d="M18 57 q3.5 -3 7 0 q-3.5 3.5 -7 0" fill="#f59e0b" opacity="0.85" />
              <path d="M47 63 q3 -2.5 6 0 q-3 3 -6 0" fill="#fbbf24" opacity="0.7" />
              <path d="M27 68 q2.5 -2 5 0 q-2.5 2.5 -5 0" fill="#f59e0b" opacity="0.5" />
            </template>

            <!-- red：枯枝分叉 + 红果，枝头略暗表示失水 -->
            <template v-else>
              <path d="M32 50 L32 30" stroke="#6b4a2a" stroke-width="3.2" stroke-linecap="round" />
              <path d="M32 41 L20 28" stroke="#6b4a2a" stroke-width="2.6" stroke-linecap="round" />
              <path d="M32 39 L44 26" stroke="#6b4a2a" stroke-width="2.6" stroke-linecap="round" />
              <path d="M32 31 L26 18" stroke="#7a5632" stroke-width="2.2" stroke-linecap="round" />
              <path d="M32 31 L39 17" stroke="#7a5632" stroke-width="2.2" stroke-linecap="round" />
              <path d="M20 28 L14 21" stroke="#7a5632" stroke-width="1.7" stroke-linecap="round" />
              <path d="M44 26 L50 20" stroke="#7a5632" stroke-width="1.7" stroke-linecap="round" />
              <circle cx="20" cy="28" r="3.4" fill="#b3261e" />
              <circle cx="19.2" cy="27" r="1.3" fill="#fca5a5" opacity="0.85" />
              <circle cx="44" cy="26" r="3.2" fill="#b3261e" />
              <circle cx="43.3" cy="25" r="1.2" fill="#fca5a5" opacity="0.85" />
              <circle cx="32" cy="31" r="3.6" fill="#ef4444" />
              <circle cx="31.2" cy="30" r="1.4" fill="#fecaca" opacity="0.9" />
              <circle cx="26" cy="18" r="2.4" fill="#ef4444" opacity="0.9" />
              <path d="M23 63 q3 -2.5 6 0 q-3 3 -6 0" fill="#16564a" opacity="0.5" />
            </template>
          </svg>
          <div class="tree-meta">
            <b>{{ t.name }}</b>
            <span class="tree-score" :class="t.level">{{ t.score }}</span>
          </div>
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.forest-wrap {
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.forest-intro {
  margin: 0 0 4px;
  font-size: 12.5px;
  line-height: 1.7;
}
.forest-empty {
  padding: 40px 0;
  text-align: center;
  color: var(--muted);
  font-size: 13px;
}

.forest-card {
  background: linear-gradient(180deg, #f4f9ee 0%, #fbf7ef 60%);
  border: 1px solid var(--line);
  border-radius: 14px;
  padding: 16px 18px 18px;
}
.forest-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 12px;
}
.forest-head h3 {
  margin: 0;
  font-size: 15px;
  color: var(--text);
}
.forest-stat {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}
.stat-pill {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 9px;
  border-radius: 999px;
  font-size: 11.5px;
  border: 1px solid var(--line);
  background: #fff;
  color: var(--text-2);
}
.stat-pill i {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex: none;
}
.stat-pill.green i { background: #17604f; }
.stat-pill.yellow i { background: #a9681f; }
.stat-pill.red i { background: #b3261e; }
.stat-health {
  font-size: 11.5px;
  color: var(--muted);
}
.stat-health b {
  color: var(--text);
  font-size: 13px;
  font-variant-numeric: tabular-nums;
}

.forest-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(78px, 1fr));
  gap: 10px 6px;
}
.tree {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 6px 4px 8px;
  border: 0;
  border-radius: 10px;
  background: rgba(255, 255, 255, 0.55);
  transition: background 0.14s, transform 0.14s, box-shadow 0.14s;
  cursor: pointer;
  font: inherit;
  color: inherit;
  text-align: center;
}
.tree:hover {
  background: #fff;
  transform: translateY(-2px);
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.08);
}
.tree:focus-visible {
  outline: 2px solid var(--brand, #16564a);
  outline-offset: 2px;
}
.tree-svg {
  width: 64px;
  height: 84px;
  display: block;
  transition: transform 0.18s ease;
}
.tree:hover .tree-svg {
  transform: scale(1.06);
}
.tree-meta {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1px;
  line-height: 1.3;
}
.tree-meta b {
  font-size: 12px;
  color: var(--text);
  font-weight: 500;
}
.tree-score {
  font-size: 10.5px;
  font-variant-numeric: tabular-nums;
  padding: 0 6px;
  border-radius: 8px;
  font-weight: 600;
}
.tree-score.green {
  color: #17604f;
  background: #e2efe9;
}
.tree-score.yellow {
  color: #16564a;
  background: #f9efdf;
}
.tree-score.red {
  color: #9c231c;
  background: #f9e8e5;
}

@media (max-width: 760px) {
  .forest-grid {
    grid-template-columns: repeat(auto-fill, minmax(64px, 1fr));
  }
  .tree-svg {
    width: 54px;
    height: 71px;
  }
}
</style>
