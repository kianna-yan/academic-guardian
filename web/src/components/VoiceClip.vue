<script setup lang="ts">
/**
 * 语音条：家校沟通与各端口「问 AI」共用同一种形状。
 *
 * 结构照微信/家校沟通那一版——左边一枚浮起的白圆（里面是声波），
 * 中间是浏览器的原生播放控件（播放键、时间、进度、音量都是它能随手拖的东西，
 * 自己画一套反而不如原生的好用），右边一句「3.2″」。
 *
 * 声波朝哪边，取决于这条是谁说的：
 * - 对方发的（气泡在左）：声音从对面传来，弧口朝右——朝我这边扩散；
 * - 自己发的（气泡在右）：声音从我这儿出去，弧口朝左——朝对面扩散。
 * 也就是喇叭口永远指着「听的人」，跟微信一致。翻错了看着就拧巴。
 */
import VoiceWave from "@/components/VoiceWave.vue";

withDefaults(
  defineProps<{
    src?: string;
    /** 没有音源时（老会话只存了名字）退回成一行文字，不摆一个按不动的播放键 */
    name?: string;
    duration?: number | string;
    /** 喇叭口朝哪边：对方发的传 right，自己发的传 left */
    out?: "left" | "right";
  }>(),
  { src: "", name: "", duration: "", out: "left" },
);
</script>

<template>
  <div class="voice-clip">
    <span class="vc-ico" aria-hidden="true"><VoiceWave :size="20" :flip="out === 'left'" /></span>
    <audio v-if="src" :src="src" controls preload="metadata"></audio>
    <span v-else class="vc-name">{{ name || "语音" }}</span>
    <span v-if="duration" class="vc-sec">{{ duration }}″</span>
  </div>
</template>

<style scoped>
.voice-clip {
  display: inline-flex;
  align-items: center;
  gap: 9px;
  padding: 5px 13px 5px 6px;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: #fff;
  max-width: 100%;
}
/* 白圆浮在胶囊上：不描边、只用一层很浅的投影压出边界 */
.vc-ico {
  flex: 0 0 auto;
  width: 30px;
  height: 30px;
  display: grid;
  place-items: center;
  border-radius: 50%;
  background: #fff;
  color: var(--moss);
  box-shadow: 0 1px 3px rgba(60, 50, 30, 0.16);
}
.voice-clip audio {
  height: 30px;
  width: 216px;
  max-width: 52vw;
}
.vc-name {
  font-size: 12px;
  color: var(--muted);
  padding: 0 2px;
}
.vc-sec {
  flex: 0 0 auto;
  font-size: 11px;
  color: var(--muted);
}
</style>
