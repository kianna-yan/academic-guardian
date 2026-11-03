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
          <!-- 树形 SVG：60x80 viewBox，按 level 切换形态 -->
          <svg viewBox="0 0 60 80" class="tree-svg" aria-hidden="true">
            <!-- 树干 -->
            <rect x="27" y="48" width="6" height="22" rx="2" :fill="t.level === 'red' ? '#7c5a3a' : '#6b4423'" />
            <!-- 树冠：green 茂盛圆冠 / yellow 黄色椭圆 + 落叶 / red 枯枝 + 红果 -->
            <template v-if="t.level === 'green'">
              <circle cx="30" cy="34" r="18" fill="#16a34a" />
              <circle cx="22" cy="28" r="9" fill="#22c55e" />
              <circle cx="38" cy="26" r="8" fill="#22c55e" />
              <circle cx="30" cy="22" r="7" fill="#4ade80" />
            </template>
            <template v-else-if="t.level === 'yellow'">
              <ellipse cx="30" cy="34" rx="17" ry="15" fill="#d97706" />
              <ellipse cx="22" cy="29" rx="8" ry="7" fill="#f59e0b" />
              <ellipse cx="38" cy="28" rx="7" ry="6" fill="#fbbf24" />
              <!-- 几片落叶飘下来 -->
              <ellipse cx="14" cy="56" rx="3" ry="2" fill="#fbbf24" opacity="0.7" transform="rotate(-20 14 56)" />
              <ellipse cx="48" cy="60" rx="3" ry="2" fill="#f59e0b" opacity="0.6" transform="rotate(25 48 60)" />
            </template>
            <template v-else>
              <!-- 枯枝：稀疏枝条 -->
              <path d="M30 50 L18 32 M30 50 L42 30 M30 50 L30 24 M22 38 L14 28 M38 38 L46 28" 
                    stroke="#5a3d20" stroke-width="2" fill="none" stroke-linecap="round" />
              <!-- 红色警示果 -->
              <circle cx="18" cy="32" r="3" fill="#dc2626" />
              <circle cx="42" cy="30" r="3" fill="#dc2626" />
              <circle cx="30" cy="24" r="3.5" fill="#ef4444" />
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
.stat-pill.green i { background: #16a34a; }
.stat-pill.yellow i { background: #d97706; }
.stat-pill.red i { background: #dc2626; }
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
  outline: 2px solid var(--brand, #b45309);
  outline-offset: 2px;
}
.tree-svg {
  width: 60px;
  height: 80px;
  display: block;
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
  color: #047857;
  background: #ecfdf5;
}
.tree-score.yellow {
  color: #b45309;
  background: #fffbeb;
}
.tree-score.red {
  color: #b91c1c;
  background: #fef2f2;
}

@media (max-width: 760px) {
  .forest-grid {
    grid-template-columns: repeat(auto-fill, minmax(64px, 1fr));
  }
  .tree-svg {
    width: 50px;
    height: 66px;
  }
}
</style>
