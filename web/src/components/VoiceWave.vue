<script setup lang="ts">
/**
 * 语音声波图标（微信那条「((·」）。
 *
 * 原来三处各画一只 🎤 emoji：对话气泡、家校沟通的播放条、待发附件的小格子。
 * emoji 会跟着系统字体变样（Windows 是彩色三维话筒、macOS 是另一个样），
 * 和这套纸感界面始终不搭，也会在深绿气泡上糊成一片。抽成一个组件，
 * 三处共用一条 2.2px 描线，颜色吃 currentColor——放在深色气泡上自动变白，
 * 放在白底播放条上自动变墨绿。
 *
 * flip：转 180°，让圆点贴住气泡外缘、弧口朝外。语音条里的声波永远是这个姿态，
 * 因为「喇叭朝外」才符合人对声音方向的直觉——弧口朝着自己这边就是在往外放。
 */
withDefaults(defineProps<{ size?: number; flip?: boolean }>(), { size: 30, flip: false });
</script>

<template>
  <svg
    :width="size"
    :height="size"
    viewBox="0 0 24 24"
    aria-hidden="true"
    :style="flip ? { transform: 'rotate(180deg)' } : undefined"
  >
    <circle cx="5.6" cy="12" r="2.1" fill="currentColor" />
    <path d="M10.3 6.7a7.4 7.4 0 0 1 0 10.6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" />
    <path d="M14.7 3.7a11.6 11.6 0 0 1 0 16.6" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" />
  </svg>
</template>
