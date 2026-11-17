/**
 * 浏览器端的多模态采集：压图、抽帧、录音。
 *
 * 三条都放在前端做，是为了让后端零依赖——
 * 服务器上不保证有 ffmpeg / opencv，也不该为了看一眼视频装这些东西。
 * 浏览器里有 canvas 和 MediaRecorder，够用了。
 */

/** text 不是采集出来的，而是「上传文档」解析出的正文，走同一个附件通道 */
export type MediaKind = "image" | "video" | "audio" | "text";

export interface PickedMedia {
  id: string;
  kind: MediaKind;
  name: string;
  mime: string;
  /** 图片 / 音频的 dataURL */
  data?: string;
  /**
   * 语音专供识别的一份 16kHz WAV。
   * data 那份是 webm/opus，用来在气泡里原音回放；glm-asr 不收 webm，
   * 所以另存一份 WAV 交给后端转写。
   */
  asr?: string;
  /** 视频抽出来的帧（dataURL 数组） */
  frames?: string[];
  duration?: number;
  /** 浏览器实时转写的文字，后端 ASR 不可用时兜底 */
  transcript?: string;
  /** 气泡里显示的小图 */
  thumb?: string;
  size: number;
  /** kind=text 时抽出来的字数（上传文档用，气泡里显示「约 1200 字」） */
  chars?: number;
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

/**
 * PCM → 16kHz 单声道 16bit WAV 的 dataURL。
 *
 * 为什么要多此一举：浏览器 MediaRecorder 只会录 webm/opus 或 mp4/aac，
 * 而智谱 glm-asr 明确不收 webm（返回 1214「不支持当前文件格式」）。
 * 也就是说「录音给后端识别」这条路，只要送的是浏览器原生的 webm，
 * 就算 key 和语音资源包都齐了也永远转不出来。所以另外采一路 PCM，
 * 自己封一层 WAV 头专供识别；webm 那份留给气泡里按播放。
 */
function downsample(buf: Float32Array, from: number, to: number): Float32Array {
  if (to >= from || !buf.length) return buf;
  const ratio = from / to;
  const out = new Float32Array(Math.max(1, Math.floor(buf.length / ratio)));
  for (let i = 0; i < out.length; i += 1) {
    const start = Math.floor(i * ratio);
    const end = Math.min(buf.length, Math.floor((i + 1) * ratio));
    let sum = 0;
    for (let j = start; j < end; j += 1) sum += buf[j];
    out[i] = sum / Math.max(1, end - start);
  }
  return out;
}

function encodeWav(chunks: Float32Array[], rate: number, target = 16000): string {
  let total = 0;
  for (const c of chunks) total += c.length;
  const all = new Float32Array(total);
  let off = 0;
  for (const c of chunks) {
    all.set(c, off);
    off += c.length;
  }
  const pcm = downsample(all, rate, target);
  const bytes = new Uint8Array(44 + pcm.length * 2);
  const view = new DataView(bytes.buffer);
  const tag = (o: number, s: string) => {
    for (let i = 0; i < s.length; i += 1) view.setUint8(o + i, s.charCodeAt(i));
  };
  tag(0, "RIFF");
  view.setUint32(4, 36 + pcm.length * 2, true);
  tag(8, "WAVE");
  tag(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);          // PCM
  view.setUint16(22, 1, true);          // 单声道
  view.setUint32(24, target, true);
  view.setUint32(28, target * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  tag(36, "data");
  view.setUint32(40, pcm.length * 2, true);
  let p = 44;
  for (let i = 0; i < pcm.length; i += 1) {
    const s = Math.max(-1, Math.min(1, pcm[i]));
    view.setInt16(p, s < 0 ? s * 0x8000 : s * 0x7fff, true);
    p += 2;
  }
  // 分块拼二进制串，一次 apply 三万多个参数会爆栈
  let bin = "";
  const STEP = 0x4000;
  for (let i = 0; i < bytes.length; i += STEP) {
    bin += String.fromCharCode(...bytes.subarray(i, i + STEP));
  }
  return "data:audio/wav;base64," + btoa(bin);
}

export interface Recorder {
  stop: () => Promise<PickedMedia>;
  cancel: () => void;
  /** 浏览器实时转写出来的文字（可能为空） */
  transcript: () => string;
  /** 有没有可用的浏览器转写 */
  canTranscribe: boolean;
  /** 浏览器转写的失败原因（network / not-allowed / no-speech…），成功则为空 */
  reason: () => string;
}

interface SpeechRecognitionLike {
  lang: string;
  continuous: boolean;
  interimResults: boolean;
  maxAlternatives: number;
  start: () => void;
  stop: () => void;
  abort: () => void;
  onresult: ((ev: any) => void) | null;
  onerror: ((ev: any) => void) | null;
  onend: (() => void) | null;
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
 *
 * 三个容易踩的坑（都修在这一个函数里）：
 * 1. Chrome 静音一两秒就会自己 end，一次录音里听到的其实是「第一句」——
 *    后面说了什么全丢。所以 onend 里接着 start()，只要还在录就不停。
 * 2. interimResults=false 时最后一句的 final 结果常常在 stop() 之后才回调，
 *    说完立刻松手就会少最后几个字。这里 interim 也收，并在 stop() 时等 final。
 * 3. 失败要能说出原因（network = 连不上浏览器语音服务），不能再静默返回空字符串，
 *    否则上层只能猜「是不是用户没说话」。
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

  // 第二路：采 PCM 备用（转 WAV 给后端识别）。取不到也不影响录音本身，
  // 比如某些浏览器对 AudioContext 的采样率有要求——失败就静默跳过。
  const pcm: Float32Array[] = [];
  let audioCtx: AudioContext | null = null;
  let pcmRate = 16000;
  try {
    const AC = (window.AudioContext || (window as any).webkitAudioContext) as typeof AudioContext;
    audioCtx = new AC();
    pcmRate = audioCtx.sampleRate || 48000;
    const source = audioCtx.createMediaStreamSource(stream);
    const node = audioCtx.createScriptProcessor(4096, 1, 1);
    node.onaudioprocess = (e) => {
      pcm.push(new Float32Array(e.inputBuffer.getChannelData(0)));
    };
    // 必须接到 destination 才会跑；中间串一个 0 增益，否则麦克风原音会
    // 从扬声器放出来，一边说话一边啸叫
    const mute = audioCtx.createGain();
    mute.gain.value = 0;
    source.connect(node);
    node.connect(mute);
    mute.connect(audioCtx.destination);
  } catch {
    audioCtx = null;
  }

  // 实时转写（Chrome/Edge 有，Firefox 没有，取不到就安静跳过）
  let said = "";        // 已经定稿的句子
  let interim = "";     // 正在说的半句，先说给它听，来不及定稿也算数
  let srError = "";
  let wantSpeech = true;   // 还在录：允许 onend 之后自动重启
  let speechEnded = false; // 已经正式 stop 过，别再重启
  let sr: SpeechRecognitionLike | null = null;
  const Ctor = speechCtor();
  if (Ctor) {
    try {
      const inst = new Ctor();
      inst.lang = "zh-CN";
      inst.continuous = true;
      inst.interimResults = true;
      inst.maxAlternatives = 1;
      inst.onresult = (ev: any) => {
        let done = "";
        let live = "";
        for (let i = ev.resultIndex; i < ev.results.length; i += 1) {
          const alt = ev.results[i];
          const txt = alt?.[0]?.transcript || "";
          if (alt.isFinal) done += txt;
          else live += txt;
        }
        if (done) said += done;
        interim = live;
      };
      inst.onerror = (ev: any) => {
        const code = String(ev?.error || "error");
        // no-speech 只是这一小段没人说话，不算失败
        if (code !== "no-speech") srError = code;
      };
      inst.onend = () => {
        if (speechEnded || !wantSpeech) return;
        // 网络/权限类错误重开也没用，只会刷一串报错
        if (srError === "network" || srError === "not-allowed" || srError === "service-not-allowed") {
          return;
        }
        try {
          inst.start();
        } catch {
          /* 已经在跑了 */
        }
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
      void audioCtx?.close();
    } catch {
      /* 已经关了 */
    }
    audioCtx = null;
  };

  const saidText = () => (said + interim).trim();

  // 识别用的 WAV：PCM 那一路没采到就返回空，后端会退回用 webm 撞一次
  const wavData = (): string | undefined => {
    try {
      return pcm.length ? encodeWav(pcm, pcmRate) : undefined;
    } catch {
      return undefined;
    }
  };

  return {
    canTranscribe: !!sr,
    transcript: saidText,
    reason: () => srError,
    cancel: () => {
      wantSpeech = false;
      speechEnded = true;
      try {
        recorder.stop();
      } catch {
        /* 没在录 */
      }
      try {
        sr?.abort?.();
      } catch {
        /* 已经停了 */
      }
      close();
    },
    stop: () =>
      new Promise<PickedMedia>((resolve, reject) => {
        wantSpeech = false;
        speechEnded = true;
        const finish = () => {
          const asr = wavData();
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
              asr,
              duration: Math.max(1, Math.round((Date.now() - startedAt) / 100) / 10),
              transcript: saidText(),
              size: blob.size,
            });
          };
          reader.onerror = () => reject(new Error("录音读取失败"));
          reader.readAsDataURL(blob);
        };
        const afterSpeech = () => {
          recorder.onstop = finish;
          try {
            recorder.stop();
          } catch {
            finish();
          }
        };
        if (!sr) {
          afterSpeech();
          return;
        }
        // 等最后一句定稿，最多 700ms；不等的话「说完就松手」总丢最后几个字
        const timer = window.setTimeout(afterSpeech, 700);
        sr.onend = () => {
          window.clearTimeout(timer);
          afterSpeech();
        };
        try {
          sr.stop();
        } catch {
          window.clearTimeout(timer);
          afterSpeech();
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
