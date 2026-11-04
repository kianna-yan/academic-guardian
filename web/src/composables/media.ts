/**
 * 浏览器端的多模态采集：压图、抽帧、录音。
 *
 * 三条都放在前端做，是为了让后端零依赖——
 * 服务器上不保证有 ffmpeg / opencv，也不该为了看一眼视频装这些东西。
 * 浏览器里有 canvas 和 MediaRecorder，够用了。
 */

export type MediaKind = "image" | "video" | "audio";

export interface PickedMedia {
  id: string;
  kind: MediaKind;
  name: string;
  mime: string;
  /** 图片 / 音频的 dataURL */
  data?: string;
  /** 视频抽出来的帧（dataURL 数组） */
  frames?: string[];
  duration?: number;
  /** 浏览器实时转写的文字，后端 ASR 不可用时兜底 */
  transcript?: string;
  /** 气泡里显示的小图 */
  thumb?: string;
  size: number;
}

let seq = 0;
function uid(): string {
  seq += 1;
  return `m${Date.now().toString(36)}${seq}`;
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => resolve(img);
    img.onerror = () => reject(new Error("图片解码失败"));
    img.src = src;
  });
}

function drawToDataURL(
  img: HTMLImageElement | HTMLVideoElement,
  maxEdge: number,
  quality: number,
): { full: string; thumb: string } {
  const sw = (img as HTMLImageElement).naturalWidth || (img as HTMLVideoElement).videoWidth;
  const sh = (img as HTMLImageElement).naturalHeight || (img as HTMLVideoElement).videoHeight;
  const scale = Math.min(1, maxEdge / Math.max(sw || 1, sh || 1));
  const w = Math.max(1, Math.round(sw * scale));
  const h = Math.max(1, Math.round(sh * scale));

  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("浏览器不支持 canvas");
  ctx.drawImage(img as CanvasImageSource, 0, 0, w, h);

  const tScale = Math.min(1, 260 / Math.max(w, h));
  const tc = document.createElement("canvas");
  tc.width = Math.max(1, Math.round(w * tScale));
  tc.height = Math.max(1, Math.round(h * tScale));
  tc.getContext("2d")?.drawImage(canvas, 0, 0, tc.width, tc.height);

  return {
    full: canvas.toDataURL("image/jpeg", quality),
    thumb: tc.toDataURL("image/jpeg", 0.7),
  };
}

/** 图片：长边压到 1280、JPEG 0.82，一眼能看清又不至于把请求体撑爆 */
export async function pickImage(file: File): Promise<PickedMedia> {
  const url = URL.createObjectURL(file);
  try {
    const img = await loadImage(url);
    const { full, thumb } = drawToDataURL(img, 1280, 0.82);
    return {
      id: uid(),
      kind: "image",
      name: file.name || "截图.jpg",
      mime: "image/jpeg",
      data: full,
      thumb,
      size: Math.round((full.length * 3) / 4),
    };
  } finally {
    URL.revokeObjectURL(url);
  }
}

/**
 * 视频：等 metadata 出来，按 10% / 35% / 60% / 85% 四个时间点各截一帧。
 * 用比例而不是固定秒数，30 秒的课录和 3 分钟的都取得到中段。
 */
export async function pickVideo(file: File, count = 4): Promise<PickedMedia> {
  const url = URL.createObjectURL(file);
  const video = document.createElement("video");
  video.muted = true;
  video.playsInline = true;
  video.preload = "auto";
  video.src = url;

  const cleanup = () => URL.revokeObjectURL(url);

  try {
    await new Promise<void>((resolve, reject) => {
      const timer = window.setTimeout(() => reject(new Error("视频加载超时")), 12000);
      video.onloadedmetadata = () => {
        window.clearTimeout(timer);
        resolve();
      };
      video.onerror = () => {
        window.clearTimeout(timer);
        reject(new Error("这个视频格式浏览器读不了，试试 MP4"));
      };
    });

    const duration = Number.isFinite(video.duration) ? video.duration : 0;
    const frames: string[] = [];
    let thumb = "";
    const spots = Array.from({ length: count }, (_, i) => (0.1 + (0.75 * i) / Math.max(1, count - 1)));
    for (const ratio of spots) {
      const at = Math.max(0, Math.min(duration - 0.05, duration * ratio));
      await new Promise<void>((resolve) => {
        const done = () => {
          video.removeEventListener("seeked", done);
          resolve();
        };
        video.addEventListener("seeked", done);
        video.currentTime = at;
        // 极短视频 seek 不触发 seeked，兜一下
        window.setTimeout(done, 1200);
      });
      try {
        const shot = drawToDataURL(video, 960, 0.76);
        frames.push(shot.full);
        if (!thumb) thumb = shot.thumb;
      } catch {
        /* 单帧失败不影响整体 */
      }
    }
    if (!frames.length) throw new Error("没能从这个视频里取到画面");

    return {
      id: uid(),
      kind: "video",
      name: file.name || "视频.mp4",
      mime: "video/mp4",
      frames,
      duration,
      thumb,
      size: file.size,
    };
  } finally {
    cleanup();
  }
}

/* ------------------------------------------------------------------ 录音 */

export interface Recorder {
  stop: () => Promise<PickedMedia>;
  cancel: () => void;
  /** 浏览器实时转写出来的文字（可能为空） */
  transcript: () => string;
  /** 有没有可用的浏览器转写 */
  canTranscribe: boolean;
}

interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  start: () => void;
  stop: () => void;
  onresult: ((ev: any) => void) | null;
  onerror: ((ev: any) => void) | null;
}

interface SpeechCtor {
  new (): SpeechRecognitionLike;
}

function speechCtor(): SpeechCtor | null {
  const w = window as unknown as { SpeechRecognition?: SpeechCtor; webkitSpeechRecognition?: SpeechCtor };
  return w.SpeechRecognition || w.webkitSpeechRecognition || null;
}

export const canRecord = (): boolean =>
  typeof navigator !== "undefined" &&
  !!navigator.mediaDevices?.getUserMedia &&
  typeof MediaRecorder !== "undefined";

/**
 * 开麦录音。
 *
 * 同时挂一路浏览器自带的语音识别做实时转写：智谱 glm-asr 要单独的语音
 * 资源包，额度用尽时后端转不出来，这时候浏览器那份文字就是兜底，
 * 用户说完立刻能在输入框看到自己讲了什么，而不是干等一个「没听清」。
 */
export async function startRecording(): Promise<Recorder> {
  if (!canRecord()) throw new Error("这个浏览器不支持录音，换 Chrome 或 Edge 试试");
  const stream = await navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true },
  });

  const prefer = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg"];
  const mime = prefer.find((m) => MediaRecorder.isTypeSupported(m)) || "";
  const recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
  const chunks: BlobPart[] = [];
  recorder.ondataavailable = (e) => {
    if (e.data && e.data.size) chunks.push(e.data);
  };
  recorder.start(250);
  const startedAt = Date.now();

  // 实时转写（Chrome/Edge 有，Firefox 没有，取不到就安静跳过）
  let said = "";
  let sr: SpeechRecognitionLike | null = null;
  const Ctor = speechCtor();
  if (Ctor) {
    try {
      const inst = new Ctor();
      inst.lang = "zh-CN";
      inst.continuous = true;
      inst.interimResults = false;
      inst.onresult = (ev: any) => {
        let text = "";
        for (let i = ev.resultIndex; i < ev.results.length; i += 1) {
          if (ev.results[i].isFinal) text += ev.results[i][0].transcript;
        }
        if (text) said = (said + text).trim();
      };
      inst.onerror = () => {
        /* 浏览器转写不通就安静放弃，后端会接手 */
      };
      inst.start();
      sr = inst;
    } catch {
      sr = null;
    }
  }

  const close = () => {
    stream.getTracks().forEach((t) => t.stop());
    try {
      sr?.stop();
    } catch {
      /* 已经停了 */
    }
  };

  return {
    canTranscribe: !!sr,
    transcript: () => said,
    cancel: () => {
      try {
        recorder.stop();
      } catch {
        /* 没在录 */
      }
      close();
    },
    stop: () =>
      new Promise<PickedMedia>((resolve, reject) => {
        const finish = () => {
          close();
          const blob = new Blob(chunks, { type: mime || "audio/webm" });
          if (!blob.size) {
            reject(new Error("这段录音是空的，再说一次试试"));
            return;
          }
          const reader = new FileReader();
          reader.onload = () => {
            const data = String(reader.result || "");
            resolve({
              id: uid(),
              kind: "audio",
              name: `语音 ${new Date().toLocaleTimeString("zh-CN", { hour12: false })}.${mime.includes("mp4") ? "m4a" : "webm"}`,
              mime: mime || "audio/webm",
              data,
              duration: Math.max(1, Math.round((Date.now() - startedAt) / 100) / 10),
              transcript: said,
              size: blob.size,
            });
          };
          reader.onerror = () => reject(new Error("录音读取失败"));
          reader.readAsDataURL(blob);
        };
        recorder.onstop = finish;
        try {
          recorder.stop();
        } catch {
          finish();
        }
      }),
  };
}

export function humanSize(bytes: number): string {
  if (!bytes) return "";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
}
