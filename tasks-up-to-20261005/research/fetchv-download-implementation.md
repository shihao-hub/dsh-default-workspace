# FetchV 下载实现原理调研（基于一手代码）

> 调研对象：**FetchV v3.2**（Chrome Web Store ID `nfmmmhanepmpifddlkkmihkalkoekpfd`，Edge Add-ons ID `dbepbhhcmhodojepbagfppgpieeplpik`）
> 调研日期：本机扩展目录快照 + fetchv.net 线上站点代码快照
> 调研方法：本机已安装的扩展源码逐文件阅读 + 从 fetchv.net 拉取其下载页的完整 JS 模块 + 对混淆代码做**可复现的反混淆**（见 [附录 A](#附录-a反混淆方法与可复现性)）

---

## 0. 本次实际拿到的一手证据等级

| 证据 | 等级 | 位置 |
| --- | --- | --- |
| 扩展本体全部 61 个文件（未加密、未混淆） | **完整代码** | `%LOCALAPPDATA%\Google\Chrome\User Data\Default\Extensions\nfmmmhanepmpifddlkkmihkalkoekpfd\3.2_0\` |
| 扩展 `_metadata` 完整性清单 | **完整** | 同目录 `_metadata\verified_contents.json`、`_metadata\computed_hashes.json` |
| fetchv.net 下载页的全部 JS 模块（含 worker、muxer、ffmpeg.wasm 胶水层） | **完整代码**（但被打包器混淆，已反混淆） | 见 [附录 A](#附录-a反混淆方法与可复现性) |
| `ffmpeg-core.v2.wasm` 二进制本体 | **完整**（已下载、已解压、已做字符串检索） | 562 601 B（zlib）→ 1 166 201 B（wasm），见 §8.2 |
| 官方网站功能自述、博客、FAQ | 官方文档 | [fetchv.net](https://fetchv.net/) 等 |
| 商店权限清单 | 官方，但仅作交叉验证 | manifest 本身就是权威来源，无需依赖商店页 |

**结论：这是一次「拿到了完整代码」的调研。** 扩展侧 100% 是明文可读源码；站点侧（真正干活的那一半）是 javascript-obfuscator 混淆过的产物，我用可复现脚本还原了字符串常量表（还原率：hls-loader `2899/3115`、rec-loader `1768/1907`、mp4-loader `814/1297`），**凡是「推断」的内容我都单独标注了**。

---

## 1. 结论摘要（整体架构）

1. **FetchV 在 MV3 下被拆成两半：扩展本体只负责「嗅探 + 记头 + 过滤 + 界面」，真正的下载/解密/转封装全部跑在 `fetchv.net` 的普通网页里。** 扩展侧 manifest 只有 `tabs / webRequest / storage / declarativeNetRequest / offscreen / scripting` 六个权限，没有 `downloads`，没有 `nativeMessaging`；点「下载」时它把任务对象塞进 `chrome.storage.local.queue`，然后 `chrome.tabs.create` 打开 `fetchv.net/m3u8downloader`（或 `videodownloader` / `bufferrecorder`），由该页面的 content script 通过 `BroadcastChannel` 把任务捞出来。这就是它能「在浏览器里跑 ffmpeg.wasm 和大文件流式落盘」而不被 MV3 Service Worker 生命周期掐死的原因。

2. **媒体 URL 靠 `chrome.webRequest` 主动嗅探，而不是扫 DOM 或读 `performance.getEntriesByType('resource')`。** 两个监听器：`onBeforeSendHeaders`（只为了把该请求的请求头存下来，供后续复放）和 `onResponseStarted`（真正的识别逻辑，读响应头 `Content-Type` / `Content-Length` / `Content-Range` / `Content-Disposition`）。过滤条件非常具体：请求类型必须是 `["media","xmlhttprequest","object","other"]`、`initiator` 必须是 http(s)、响应码必须 200–300、`Content-Type` 与 URL 后缀要做交叉映射表匹配、非 HLS 的还要过 `Content-Length` 大小阈值（默认下限 **500 KB**）。

3. **HLS 用打包进去的 hls.js，而且是「深度魔改」的用法**：`new Hls({autoStartLoad:false, pLoader: class extends DefaultConfig.loader {...}, fLoader: ...})`，并显式设置 `fragLoadingTimeOut = 0x61a8`（25 秒）与一个并发度变量 `threads`（同一段初始化里还写了 `0xc` = 12 和 `0x3` = 3 两个数值常量，语义未逐一验证）。hls.js 在 FetchV 里**既做预览播放，也做下载用的清单解析**（选最高码率、拿分片列表、判断是否加密），**分片下载与合并由 FetchV 自己的 `Fetcher` + Web Worker 完成，不是 hls.js 自带的加载器**——`singleThread` 开关会直接把并发度压成 `1`。

4. **AES-128 HLS 是扩展自己解密的**：`hls.js` 的 `decryptdataLoader` 拿到 key/IV 后，走 `HLSDecrypter.decryptAES(encrypted, iv, key)` → `postMessage` 给 `modules/decrypter-worker.js` 里的纯 JS AES-CBC 实现（`aesDecrypter.Decrypter`，即 hls.js 生态里的 `aes-decrypter`），明文再交回 loader。**Widevine / 任何 DRM 一律碰不了**：官方博客明确写「使用了数字版权保护的视频，FetchV 同样无法提供下载支持」；代码里唯一的 `requestMediaKeySystemAccess` 出现在**打包进来的 hls.js 库内部**（`js/hls-player.js`、`modules/hls.es.js` 各 5 处，是 hls.js 的 EME 路径），FetchV 自己的代码从未调用它，也**没有任何 `crypto.subtle` 调用**。

5. **DASH/分离音视频靠「双队列 + 时间轴裁剪」合并，不靠 ffmpeg**：`modules/web-worker.js` 维护 `fragments = {video:[], audio:[]}` 两个队列，`audioVideoCopy()` 按 `start/end` 时间戳把两个队列的尾巴裁到重叠区间；fMP4 走自研 `FMP4Muxer`，TS 走自研 `HLSMuxer`（`modules/hls-muxer.js`，39 KB，基于 ISO Box 手写）。真-ffmpeg（ffmpeg.wasm）只在探测到 codec 不一致时才作为兜底。

6. **落盘不是 `chrome.downloads`，而是「Blob + `<a download>`」和「StreamSaver（Service Worker 中间人）」两条路**：`modules/saveAs.js` 里 `e.size > 2147483648`（2 GiB）时用 `streamSaver.createWriteStream` + `readableStream.pipeTo(writable)` 由 Service Worker 边造边下，避免把 GB 级文件塞进内存；小文件才 `URL.createObjectURL` + 隐藏 `<a download>` + `revokeObjectURL`。

7. **请求头是「记录 → 复放」而不是「自己拼」**：嗅探阶段把 `referer/cookie/user-agent/accept/accept-language` 等原样存进 `chrome.storage.local`，只丢弃 `range/content-length/content-type/accept-encoding/accept` 这类会坏事的；下载阶段用 **`chrome.declarativeNetRequest` 的 session rules**（`modifyHeaders` + `condition: {domainType:"thirdParty", resourceTypes:["xmlhttprequest","media"], tabIds:[...], requestDomains|regexFilter}`）把 `origin` / `referer` 等头**改回**原创站点的值。跨域取内容还有一条兜底：`chrome.offscreen` 文档里 `fetch(url, {mode:"cors", credentials:"include", headers: 记录的请求头})`。防死循环的巧招是塞一个自定义头 `X-Original-Request-Id`，嗅探端见到它就跳过。

8. **没有任何 Native Messaging / 本地辅助进程。** 全部在浏览器进程内完成。桌面版是**另一个独立产品**（efetch.net，在站点上以广告位形式推广），扩展本体没有触达本地程序的通道。

---

## 2. manifest 关键字段

**证据文件**：[`manifest.json`](file:///C:/Users/29580/AppData/Local/Google/Chrome/User%20Data/Default/Extensions/nfmmmhanepmpifddlkkmihkalkoekpfd/3.2_0/manifest.json)（扩展本体，共 52 行，未混淆）

```json
{
  "manifest_version": 3,
  "minimum_chrome_version": "92",
  "version": "3.2",
  "background": { "service_worker": "service-worker.js" },
  "permissions": [ "tabs", "webRequest", "storage", "declarativeNetRequest", "offscreen", "scripting" ],
  "host_permissions": [ "https://*/*", "http://*/*" ],
  "content_scripts": [ {
      "js": [ "js/router.js" ],
      "matches": [ "*://fetchv.net/router.html*" ],
      "run_at": "document_end"
   }, {
      "js": [ "js/content.js" ],
      "matches": [ "*://fetchv.net/m3u8downloader*", "*://fetchv.net/*/m3u8downloader*",
                   "*://fetchv.net/videodownloader*", "*://fetchv.net/*/videodownloader*",
                   "*://fetchv.net/bufferrecorder*", "*://fetchv.net/*/bufferrecorder*" ],
      "run_at": "document_end"
   }, {
      "all_frames": true,
      "exclude_matches": [ "*://fetchv.net/*", "https://*.doubleclick.net/*", "https://www.google.com/recaptcha/*" ],
      "js": [ "js/injection.js" ],
      "matches": [ "<all_urls>" ],
      "run_at": "document_start"
   } ],
  "web_accessible_resources": [ {
      "matches": [ "<all_urls>" ],
      "resources": [ "js/hook.js", "js/mediabunny.js", "img/recording.svg" ]
   } ]
}
```

要点解读：

- **MV3**，`background.service_worker`，无 `background.scripts`。
- **没有** `downloads`、**没有** `nativeMessaging`、**没有** `cookies`、**没有** `web_accessible_resources` 里的 worker 文件。
- `host_permissions` 直接开到 `https://*/*` + `http://*/*`——这是 `webRequest` 嗅探全站的前提。
- 三段 content script 的分工极其清晰：
  1. `router.js` 只服务 `router.html`（见 §2.1，这是绕过 Chrome 对 `chrome-extension://` 页面限制的小技巧）；
  2. `content.js` 只跑在 fetchv.net 的三个下载页，负责**接收扩展传来的任务**并回传数据；
  3. `injection.js` 是**唯一注入所有站点的脚本**（`all_frames: true`，`document_start`），它做的是主世界注入和 blob/MSE 检测。
- `web_accessible_resources` 暴露 `js/hook.js`、`js/mediabunny.js`——**这正是「它要往页面主世界注入什么」的答案**（见 §2.2）。

### 2.1 `router.js` 的小机关

**证据文件**：`js/router.js`（291 字节，全文）

```js
const t = new URL(location.href), e = t.searchParams.get("path");
if (document.title = "Loading...", e) try {
  const t = document.getElementById("go");
  t.href = location.origin + e, t.click()
} catch (t) {
  const c = document.createElement("a");
  c.href = location.origin + e, c.target = "_self", document.body.append(c), c.click()
}
```

popup 在 `createTab()` 里对 **zh-CN 且非移动端**的用户走这条路径：

```js
if ("zh-CN" !== this.langCode || this.isMobile)
  chrome.tabs.create({ url: `${e.site}${i}/${o}`, index: this.tab.index + 1 }, (e => { window.close() }));
else {
  o = `${i}/${o}`;
  const t = `${e.site}/router.html?path=${encodeURIComponent(o)}`;
  chrome.tabs.create({ url: t, index: this.tab.index + 1 }, (e => { window.close() }))
}
```

即：中文用户点下载时先开 `fetchv.net/router.html?path=%2Fzh-cn%2Fm3u8downloader`，由 `router.js` 立刻跳转到真实页面。**（推断）** 这是为了让新标签页的 `document.referrer` / 打开链路更像「站内跳转」而非扩展直接打开，同时规避某些环境下扩展直接 `tabs.create` 到外部页面时的行为差异；我无法从代码证明动机，只能证明行为。

### 2.2 主世界注入了什么（`js/injection.js` + `js/hook.js`）

**证据文件**：`js/injection.js`（15 507 字节，`run_at: document_start`, `all_frames: true`）与 `js/hook.js`（1 262 字节，全文）

`injection.js` 做两件事：把 `hook.js` 以 `<script>` 插入 `document.documentElement`（真正的主世界执行），以及提供三个 RPC：`DETECT_BLOB_VIDEO`、`CHECK_TEXT_CONTENT`、`CHECK_VIDEO_SRC`。

```js
// js/injection.js
const t = document.createElement("script");
t.src = chrome.runtime.getURL("js/hook.js"),
document.documentElement.appendChild(t),
window.addEventListener("beforeunload", this.windowClose)
```

`hook.js` **只劫持两个东西：`window.MediaSource` 和 `HTMLMediaElement.prototype.currentTime`**，全文如下（已格式化）：

```js
// js/hook.js  —— 仅在「录制模式」下激活（靠 localStorage 里的 fv_recorder_tab 开关）
(() => {
  let e = !1,                              // e = 是否已收到 REC_STOP
      t = localStorage.getItem("fv_recorder_tab");
  if (!t) return;                          // 没开录制就直接不干活
  t = parseInt(t);
  const n = new BroadcastChannel(`channel-${t}`);
  function r(e, t) { return Math.floor(Math.random() * (t - e + 1)) + e }
  n.addEventListener("message", (t => { "REC_STOP" === t.data.cmd && (e = !0) }));

  const o = window.MediaSource;
  window.MediaSource = new Proxy(o, {
    construct(t, o) {
      const a = r(1e3, 2e8),               // 随机 mediaSourceId
            c = new t(...o);
      let u = !1;                          // u = 是否直播（duration === Infinity）
      return c.addEventListener("sourceended", (() => {
               e || setTimeout((() => { n.postMessage({ url: null, mid: a, live: u }) }), 5e3)
             })),
             c.addSourceBuffer = new Proxy(c.addSourceBuffer, {
               apply(t, o, i) {
                 const l = r(1e3, 2e8),    // 随机 sourceBufferId
                       s = i[0],           // mime/codecs 字符串
                       d = t.apply(o, i);
                 return d.appendBuffer = new Proxy(d.appendBuffer, {
                   apply(t, r, o) {
                     if (!e && o.length > 0) {
                       const e = o[0];
                       if (e.length > 0 || e.byteLength > 0) {
                         const t = new Blob([e]), r = URL.createObjectURL(t);
                         u = c.duration === 1 / 0,
                         n.postMessage({ url: r, mime: s, mid: a, bid: l, live: u }),
                         setTimeout((function () { URL.revokeObjectURL(r) }), 1e4)
                       }
                     }
                     return t.apply(r, o)
                   }
                 }), d
               }
             }), c
    }
  });

  // 让 currentTime 的写入“骗”播放器把缓冲区往前推
  const a = Object.getOwnPropertyDescriptor(HTMLMediaElement.prototype, "currentTime");
  let c, u = !1, i = !1;
  setTimeout((() => { i = !0 }), 1e4);
  Object.defineProperty(HTMLMediaElement.prototype, "currentTime", {
    get: function () { return a.get.call(this) },
    set: function (e) {
      i || (u ? null !== c && (e = 0) : (e = 0, u = !0, c = setTimeout((() => { c = null }), 1e3))),
      a.set.call(this, e)
    }
  })
})();
```

**这段代码是整份调研里最值得提问者细读的一页**，它精确回答了「怎么拿到 MSE 流」：

- 劫持 `MediaSource` 构造函数（`Proxy` + `construct`），拿到每个 `SourceBuffer` 的 **`mime` 字符串**（含 codecs，例如 `video/mp4; codecs="avc1.640028"`）与随机化的 `mid` / `bid`；
- 劫持 `SourceBuffer.prototype.appendBuffer`，**每一段被解码器吃进去的 fMP4 分片都被顺手 `Blob` 一次并 `createObjectURL` 发走**，10 秒后 `revokeObjectURL`（所以接收端必须马上取走，`content.js` 里的处理正是立刻 `fetch(blobURL).then(r => r.blob())` 再 `revokeObjectURL`）；
- 用 `duration === Infinity` 判定直播流；
- 劫持 `HTMLMediaElement.prototype.currentTime` 的 setter：**录制开始后 10 秒内**，把对 `currentTime` 的写入改成「第一次置 0 并吞掉后续写入 1 秒」——这是为了**骗取播放器持续请求新分片**（等价于「跳播加速缓冲」），官方文案的「可以通过倍速播放和跳跃式缓冲来加快录制速度」正对应这里加 `REC_SPEED_UP` 里的 `playbackRate` 改写：

```js
// js/injection.js
speedUp(e) {
  this.active && document.querySelectorAll('video[src^="blob:"]')
    .forEach((t => { isNaN(t.duration) || (t.playbackRate = e) }))
}
```

另外两个 RPC 是给嗅探器当判据用的：

```js
// js/injection.js —— 判断某个 XHR URL 是否就是 <video>/<source> 正在播的地址
"CHECK_VIDEO_SRC" === a && (() => {
  let t = !1;
  const o = document.querySelectorAll("video");
  if (o.length > 0) {
    const n = document.URL;
    for (const r of o) {
      let o = r.src;
      if (!o) { const e = r.querySelector("source"); e && (o = e.src) }
      if (o && (!o.startsWith("blob:") && (/^(http:\/\/|https:\/\/)/i.test(o) || (o = new URL(o, n).href), o === e)) { t = !0; break }
    }
  }
  return t && s(t), !0
})
```

```js
// js/injection.js —— “内容式捕获”：拉一段内容看它到底是不是 m3u8
checkTextContent(e, t, o, n) {
  return new Promise((r => {
    if (!this.config?.blob) return void r(!1);
    const i = new AbortController, s = i.signal, a = { method: o, signal: s, headers: {} };
    for (const e of t) a.headers[e.name] = e.value, "cookie" === e.name.toLowerCase() && (a.credentials = "include");
    a.headers["X-Original-Request-Id"] = n;      // ← 防嗅探回环的哨兵头
    const d = setTimeout((() => { i.abort() }), 1e4);
    let c = !1;
    fetch(e, a).then((e => { clearTimeout(d); if (!e.ok) throw new Error(`HTTP error! status: ${e.status}`); return e.text() }))
      .then((e => { c = e.trim().startsWith("#EXTM3U"), r(c) }))   // ← 判据就是 #EXTM3U
      .catch((e => { r(!1) }))
      .finally((() => { const e = Math.floor(Date.now() / 1e3); this.config.at = e, c && (this.config.hit = e);
                        localStorage.setItem(this.storageKey, JSON.stringify(this.config)) }))
  }))
}
```

「内容式捕获」的开关和生效范围由 `localStorage.fv_inject` 控制，且有 **7 天命中缓存 / 30 分钟未命中过期** 的节流：

```js
// js/injection.js
availability() {
  const { blob: e, at: t, hit: o } = this.config;
  if (!e) return !1;
  if (!t) return !0;
  const n = Math.floor(Date.now() / 1e3);
  return o ? (n - o > 604800 && (delete this.config.at, delete this.config.hit,
            localStorage.setItem(this.storageKey, JSON.stringify(this.config))), !0)
           : n - t < 1800
}
```

对应界面文案（`_locales/zh_CN/messages.json`）：

```json
"popup_inject_capture_tooltip": { "message": "某些特殊类型的m3u8清单可能无法被识别并捕获！开启此选项可以从文档内容中识别它们（如果存在）。请注意，如果此选项无效，请关闭它，以避免消耗更多资源！" }
```

---

## 3. 媒体 URL 是怎么被发现的

**证据文件**：`service-worker.js`（12 266 字节，混淆但可读）；分析逻辑集中在文件末尾的两个 `chrome.webRequest` 监听器。

### 3.1 监听器与过滤器

```js
// service-worker.js
chrome.webRequest.onBeforeSendHeaders.addListener((function (e) {
  if (!e.initiator) return;
  if (0 !== e.initiator.indexOf("http")) return;
  const t = e.requestHeaders;
  s[e.requestId] = t || {}                       // s = 请求头暂存表，按 requestId 索引
}), { urls: ["<all_urls>"], types: ["media", "xmlhttprequest", "object", "other"] },
   ["requestHeaders", "extraHeaders"]),
```

```js
// service-worker.js
chrome.webRequest.onResponseStarted.addListener((async function (c) {
  let { requestId: m, initiator: u, url: f, tabId: p, documentId: h, method: g,
        responseHeaders: v, statusCode: b } = c, O = [];
  if (s[m] && (O = s[m], delete s[m]), O.some((e => "x-original-request-id" === e.name.toLowerCase()))) return; // ← 哨兵头，跳过
  if (0 !== f.indexOf("http")) return;
  if (!u) return;
  if (0 !== u.indexOf("http")) return;
  const R = new URL(u).hostname;
  for (const e of a) if (R.endsWith(e)) return;   // a = ["youtube.com","globo.com"] 直接不处理
  if (0 === u.indexOf(OPTION.site)) return;       // fetchv.net 自身不算
  ...
}), { urls: ["<all_urls>"], types: ["media", "xmlhttprequest", "object", "other"] },
   ["responseHeaders"]),
```

注意这里**用的是 `onResponseStarted` 而不是 `onHeadersReceived`**：`onHeadersReceived` 允许你改写响应头，而 FetchV 只需要读（`["responseHeaders"]`），且要在拿到 `statusCode` 后再判。

### 3.2 过滤条件（逐条）

```js
// service-worker.js
if (b < 200 || b > 300) return;                       // ① 响应码必须 2xx
if (v.length < 1) return;                             // ② 必须拿得到响应头

if (-1 === p) {                                       // ③ tabId 未知时用“当前活动标签”反查
  if (!await new Promise((e => { chrome.tabs.query({ active: !0, lastFocusedWindow: !0 })
        .then((([t]) => { t && t.url.includes(u) ? (p = t.id, e(!0)) : e(!1) })) }))) return
}

const T = new URL(f).hostname;                        // ④ 域名黑名单
if (T) {
  if ((e => {                                          //    广告/统计 CDN，按二级域后缀匹配
      const t = ["doppiocdn","adtng","afcdn","sacdnssedge"], r = e.split(".");
      r.pop(); const o = r.length;
      if (o > 0) { const e = r[o - 1]; if (t.indexOf(e) > -1) return !0 }
      return !1
    })(T)) return;
  if (OPTION.domain.includes(T)) return                //    用户在 popup 里手动屏蔽的域（上限 30）
}

let w = 0, x = (e => {                                 // ⑤ 体积：优先 Content-Range，其次 Content-Length
  let r = t("Content-Range", e);
  return r ? (r = r.split(" "), 2 !== r.length ? null
      : (r = r[1].split("/"), 2 !== r.length ? null
      : (r[1] = parseInt(r[1]), r[1] ? { chunk: r[0], total: r[1] } : null))) : null
})(v);
w = x ? x.total : (e => {
  let r = t("Content-Length", e);
  return r ? (r = parseInt(r), r < 1 ? 0 : r) : 0
})(v);
```

**`Content-Range` 优先**这一条是关键——它是「识别 DASH/fMP4 分片」的入口（见 §5）。

### 3.3 类型判定：URL 后缀 × Content-Type 双向映射表

```js
// service-worker.js
let E = t("content-type", v);
if (E) { if (E.includes(";")) { const e = E.split(";"); for (let t of e) if (t = t.trim(), t) { E = t; break } } }
else {                                                // 没有 Content-Type 时用后缀兜底
  let { pathname: e } = new URL(f);
  if (e = e.toLowerCase(),
      "media" === c.type && (e.endsWith(".mp4") && (E = "video/mp4"), e.endsWith(".webm") && (E = "video/webm")),
      "xmlhttprequest" === c.type && e.endsWith(".m3u8") && (E = "application/vnd.apple.mpegurl"),
      !E) return
}

// 扩展名 ← Content-Type 映射
let n = { general: {
    "application/vnd.apple.mpegurl": ["m3u8","m3u"],
    "application/x-mpegurl":         ["m3u8","m3u"],
    "application/vnd.americandynamics.acc": ["acc"],
    "application/vnd.rn-realmedia-vbr":     ["rmvb"],
    "video/mp4":      ["mp4","m4s"],           // ← m4s：DASH 分片
    "video/3gpp":     ["3gp"],  "video/3gpp2": ["3gp2"],
    "video/x-flv":    ["flv"],  "video/quicktime": ["mov"],
    "video/x-msvideo":["avi"],  "video/x-ms-wmv": ["wmv"],
    "video/webm":     ["webm"], "video/ogg": ["ogg","ogv"],
    "video/x-f4v":    ["f4v"],  "video/x-matroska": ["mkv"],
    "video/iso.segment": ["m4s"],              // ← ISO BMFF 分片的正确 MIME
    "audio/mpeg": ["mp3"], "audio/wav": ["wav"], "audio/ogg": ["ogg"]
  }, stream: { "application/octet-stream": o, "binary/octet-stream": o } };
  // o = ["m3u8","m3u","mp4","webm","avi","ogg","flv","mkv","3gp","mp3"]
```

判定函数还处理两个特例：

```js
// service-worker.js
if (e.includes("master.txt") && 0 === t.indexOf("text/plain")) return "m3u8";
// ↑ 有些站点把 master playlist 命名成 master.txt 且用 text/plain 返回
```

**三个列表的原文（从压缩源码里直接截取，方便对照）**：

```js
// service-worker.js（原文，未改写）
a = ["youtube.com", "globo.com"],                    // initiator 黑名单：来自这些站的请求直接不处理
i = ["m3u8","m3u","mp4","3gp","flv","mov","avi",
     "wmv","webm","f4v","acc","mkv","mp3","wav","ogg"],   // 最终采纳的扩展名白名单（注意：没有 ts / m4s）
l = ["range","content-length","content-type",
     "accept-encoding","accept","accept-language"];  // 入账时要丢弃的请求头
```

   扩展名 `m4s` 能被采纳，靠的是 `n.general["video/iso.segment"] = ["m4s"]` 与 `n.general["video/mp4"] = ["mp4","m4s"]` 两条映射，最终返回 `"m4s"` 后**必须再过 `i.indexOf("m4s")` 这一关**——`i` 里恰好没有 `m4s`，所以**理论上 `m4s` 会在白名单处被挡掉，只能走「兜底 A」那条路**（`xmlhttprequest` + 有 `Content-Range` + `CHECK_VIDEO_SRC` 命中 → 被强制记成 `"mp4"`）。

**（推断，未验证）** 这说明映射表与白名单 `i` 来自不同时期的代码：`m4s` 的映射是后来加的，而白名单是旧版遗留。我没有做动态实验去确认 `m4s` 到底走哪条路。

### 3.4 三条兜底路径

```js
// service-worker.js
let y = /* ...按上表解析出的扩展名... */;
if (!y) {                                     // 兜底 A：XHR + 有 Content-Range → 问页面「是不是 video.src」
  if ("xmlhttprequest" !== c.type || !x) return;
  if (!await ((e, t) => new Promise((r => {
      const o = setTimeout((() => { r(!1) }), 2e3);
      chrome.tabs.sendMessage(t, { cmd: "CHECK_VIDEO_SRC", parameter: { url: e } }, (e => {
        if (chrome.runtime.lastError) return clearTimeout(o), void r(!1);
        clearTimeout(o), r("boolean" == typeof e && e)
      }))
    })))(f, p)) return;
  y = "mp4"
}
if (i.indexOf(y) < 0) return;                 // i = ["m3u8","m3u","mp4","3gp","flv","mov","avi","wmv","webm","f4v","acc","mkv","mp3","wav","ogg"]
                                              // ↑ 不在白名单的扩展名直接丢（.ts 不采！）

let C = y;
if ("m3u8" !== y && "m3u" !== y) {
  if (!w) return;                             // 兜底 B：非 HLS 必须有体积
  if (OPTION.size.min && w < OPTION.size.min) return;
  if (OPTION.size.max && w > OPTION.size.max) return
} else C = "hls";                             // HLS 不参与体积过滤
```

```js
// service-worker.js
// 兜底 C：XHR 返回 text/* 或 json/xml/js，且该 document 之前登记过 blob 视频
//        → 实际拉一次内容看是不是 #EXTM3U
"xmlhttprequest" === c.type && h && n.includes(h) && "GET" === g
  && (e => !!e.startsWith("text/") || !!["application/json","application/xml","application/javascript"].some((t => e === t)))(E)
  && (/google-analytics\.com|google\.com|googleadservices|doubleclick/.test(f) || await (
       (e, t, r, o, n, s) => new Promise((a => {
         chrome.tabs.sendMessage(o, { cmd: "CHECK_TEXT_CONTENT", parameter: { url: e, headers: t, method: r, requestId: s } },
           { documentId: n }, (e => { chrome.runtime.lastError ? a(!1) : a(e) }))
       })))(f, O, g, p, h, m)
  && (E = "application/vnd.apple.mpegurl");
```

### 3.5 入账：存哪些字段、丢哪些头

```js
// service-worker.js
I || (I = "no-filename");                      // 文件名：Content-Disposition → URL 末段 → no-filename
const S = {};
for (const e of O) l.includes(e.name.toLowerCase()) || (S[e.name] = e.value);
// l = ["range","content-length","content-type","accept-encoding","accept","accept-language"]
P[m] = { storageKey: _, requestId: m, url: f, method: "POST" === g ? "POST" : "GET",
         format: y, contentType: r(y, E), name: I, size: w, headers: S, type: C };
chrome.storage.local.set({ [_]: P }),
e && chrome.runtime.sendMessage({ cmd: "POPUP_APPEND_ITEMS", parameter: { tab: p, item: { [m]: P[m] } } }, ...),
d(P, p)                                        // d = 更新 action badge 数字
```

容量与去重：

```js
let P = o[_]; if (P || (P = {}, o[_] = P), Object.keys(P).length > 30) return;   // 每标签页最多 30 条
if (((e, t) => { for (let r in t) if (t[r].url === e) return !0; return !1 })(f, P)) return void d(P, p);  // URL 去重
```

**注意：`O` 是 `onBeforeSendHeaders` 存下来的「原始请求头」**，`S` 是它的子集。这套「原样记录 → 下载时复放」是 §8 的基础。

### 3.6 大小过滤器的默认值与语义

**证据文件**：`js/options.js`（270 字节，全文）

```js
const OPTION = { size: { min: 500, max: 0 }, domain: [], noAddDomainTip: !1, recMode: [],
  lang: ["nl","vi","es","pt","de","fr","it","no","fi","sv","da","el","tr","ru","hi","zh-cn","th","ko","ro","pl","zh-tw","ga","et","bg","cs","ms","sk","hu","id","fil","ja"],
  site: "https://fetchv.net" };
```

`min: 500` 的单位是 **KB**（popup 里 `i.value = s.size.min / 1024`、保存时 `e *= 1024`），即**默认只采集 ≥ 500 KB 的资源**，`0` 表示不限。popup 文案：

```json
"popup_option_size_tooltip": { "message": "大小低于下限或高于上限的资源不会被捕获，单位为KB，设置为0表示不限制。" }
"popup_option_tooltip":      { "message": "来自于以下域的资源不会被捕获" }
```

### 3.7 与 `performance.getEntriesByType('resource')` 的差别（针对提问者方案）

提问者的做法是**事后查询浏览器自己的资源时序表**，FetchV 的做法是**在请求/响应发生时由扩展拦截**。可验证的差异有三处：

1. `performance.getEntriesByType('resource')` 返回的条目**不包含 `Content-Type` / `Content-Length` / `Content-Range` / `Content-Disposition`**，FetchV 正是靠这四个头做类型判定与体积过滤（尤其 `Content-Range` 是它识别 DASH 分片的唯一入口）；Resource Timing 只有 `transferSize` / `encodedBodySize`，且跨域无 TAO 头时会被打成 0。
2. Resource Timing **看不到 blob / MSE 内部产生的分片请求**（那些请求走的是同一份 `MediaSource` 缓冲，本来就不是独立网络请求），所以提问者那条路天然拿不到 MSE 流；FetchV 靠 `hook.js` 劫持 `appendBuffer` 补齐这一块。
3. Resource Timing 是**事后**的，FetchV 是**事前/事中**的（`onBeforeSendHeaders` 能拿到请求头），这直接决定了它能不能「记下 Referer/Cookie 再复放」。

---

## 4. HLS（m3u8）怎么处理

### 4.1 清单解析：直接用打包进去的 hls.js，但换了加载器

**证据文件**：`js/hls-player.js`（506 251 字节，hls.js 官方发行版打包）；`service-worker.js`/`popup.js` 中的用法；fetchv.net 的 `hls-loader.js`（反混淆后）。

popup 的「播放预览」按钮直接实例化 hls.js：

```js
// popup.js
player(e, t, s) {
  const i = document.createElement("video");
  i.autoplay = !0, i.controls = !0, i.style.maxWidth = "100%", t.appendChild(i);
  const o = this.creatRules(e.headers);
  if ("hls" === e.type) {
    if (Hls.isSupported()) {
      const t = [], n = new Hls({ autoStartLoad: !1 });
      return n.on(Hls.Events.LEVEL_LOADED, (async (e, s) => {
               if (o) { /* 对 s.details.fragments 的每个分片域名补 DNR 规则 */ await this.setRules(o, t) }
               n.allAudioTracks.length || n.attachMedia(i)
             })),
             n.on(Hls.Events.AUDIO_TRACK_LOADED, (async (e, s) => { /* 同上，处理独立音轨 */ })),
             n.on(Hls.Events.DESTROYING, (() => { o && this.removeRules() })),
             n.on(Hls.Events.MANIFEST_PARSED, (async (e, a) => {
               /* ...对 a.levels 与 a.audioTracks 的域名补 DNR 规则... */
               n.startLoad();
               let r = 0, l = 0, c = 0;
               for (const e of n.levels) { const { bitrate: t, width: s, height: i } = e;
                 t && s && i && (t > c && (c = t, r = s, l = i)) }        // ← 选码率最高的档
               r && l ? s.innerText = `${r} x ${l}` : i.addEventListener("loadedmetadata", ...)
             })),
             o ? (t.push(this.getTopLevelDomain(e.url)), this.setRules(o, t).then((() => { n.loadSource(e.url) })))
               : n.loadSource(e.url),
             n
    }
  } else { /* 非 HLS 直接 i.src = e.url */ }
}
```

**要点**：`autoStartLoad: false` + 在 `LEVEL_LOADED` / `AUDIO_TRACK_LOADED` / `MANIFEST_PARSED` 三个时机里**动态往上加 `declarativeNetRequest` 头部改写规则**——因为分片 CDN 的域名事先不知道，只能等清单解析出来后再逐域补规则。`popup.js` 的 `setRules`：

```js
// popup.js
setRules(e, t) {
  const { ruleId: s } = this;
  return new Promise((i => {
    try {
      const o = { domainType: "thirdParty", resourceTypes: ["xmlhttprequest", "media"], tabIds: [-1] };
      if ("string" == typeof t) o.urlFilter = t;
      Array.isArray(t) && (this.isRequestDomainsSupport()
        ? o.requestDomains = t
        : o.regexFilter = `https?://(?:www\\.)?(${t.map((e => `(?:.*\\.)?${e.replace(/\./g, "\\.")}`)).join("|")})(?::\\d+)?(?:/[^s]*)?`);
      chrome.declarativeNetRequest.updateSessionRules({ removeRuleIds: [s],
        addRules: [{ id: s, priority: 1, action: { type: "modifyHeaders", requestHeaders: e }, condition: o }] },
        (function () { i(s) }))
    } catch (e) { i(0) }
  }))
}
```

```js
// popup.js —— 只把 origin / referer 两个头写回去
creatRules(e) {
  const t = []; e || (e = {});
  let s = !1;
  for (const i in e) { const o = i.toLowerCase();
    "origin" !== o && "referer" !== o || (s = !0), t.push({ header: i, operation: "set", value: e[i] }) }
  return s ? t : null                      // ← 没有 origin/referer 就不下规则
}
```

### 4.2 真正的下载：自建 `Fetcher` + 可调并发度 + 自研 muxer

**证据文件**：fetchv.net `/extensions/dist/hls-loader.js`（270 956 字节，反混淆后 448 行美化版）

反混淆后可见的标识符（脚本化提取，非人工猜测；**已逐个在反混淆产物中验证存在性**）：

```
$threads  $singleThread  option-threads  data-thread  threads  singleThread
"threads" + <当前值> + '-' + <总数>          ← 线程标识，会被塞进请求 Headers
errorFrags  error-frags-row  errorRetry  errorRetryCancel  errorNums  maxErrorNums
frags  fragments  frag  fragCount  fragLoaded  loadFragments  getFragsFromWorker
localFrags  localM3u8  progressive  masterSeek  previewURL  headerRange
bgFetcher  fFetcher  iFetcher  requests  requestId  FetchError  "InitSegment fetch error / "
decryptdataLoader  DECRYPTER_WORKER  ./modules/hls-decrypter.js  './modules/web-worker.js'
'./modules/hls-muxer.js'  './modules/fmp4-muxer.js'  './modules/ffmpeg/index.js'
'./modules/options.js'  './modules/saveAs.js'  FFMPEG timeout  MANIFEST_LOAD_ERROR
```

> 注：`freeThreads` / `lock` / `interval` / `intervalSize` / `Task canceled!` 这几个标识符**不在** hls-loader 里（我已逐个检索确认计数为 0），它们在站点侧的 `mp4-loader.js`（Range 分块下载器）中。所以它们**不能**用来论证 HLS 下载器的并发模型。

hls.js 的实例化（反混淆后可见 `new Hls({...})` 的参数键名，类名被混淆为 `_0x1779dc`）：

```js
// fetchv.net /extensions/dist/hls-loader.js（反混淆后）
const _0x4f1a8f = new _0x1779dc({
  autoStartLoad: !1,
  pLoader: class extends _0x1779dc['DefaultConfig']['loader'] { constructor(_0xe5c144) { ... } },
  ...                                  // fLoader 同样被覆写
});
```

初始化代码里明确写入了超时与并行度：

```js
// fetchv.net /extensions/dist/hls-loader.js（反混淆后）
// 在“新建任务”分支里一次性写入：
this["setChunksCompleted"] = _0x3a84ab,
this["`@{ ¬t"] = 0x0,
this["z4ö{D"]  = 0x0,
this["ôsá+ó"]  = 0xc,                 // 12  —— 语义未验证
this["l¡Á(¶ºÆi"] = 0x3,               // 3   —— 语义未验证
this['fragLoadingTimeOut'] = 0x61a8,  // 25000 ms = 25 s  ✅ 属性名可读，语义确定
this["di·pUg"] = { 'main': null, 'audio': null },     // ✅ 双轨结构
this["completed"] = 0x5,
...
```

**关于并发的可确证证据**（属性名可读，逻辑形态可读；这是我在反混淆产物里实际找到的上下文）：

```js
// fetchv.net /extensions/dist/hls-loader.js（反混淆后，逐段摘录）
_0xc7526[_0x5d8201(0xcd6,'dGHZ')](_0x12296a["âaW1àúÀJ"], _0x2272a2)
  && (_0x12296a['threads'] = _0x2272a2, ...)          // ← a) 把用户设定的线程数写回任务对象
...
let { threads: _0x328a39 } = _0x20c8d0, _0x49c10c = !0x1;
...
else this['singleThread'] && (_0x328a39 = 0x1);        // ← b) 单线程开关：并发度压成 1
if (... || _0x2fee4f["¶hèr\r"](this["ßdÁY\tõ="], _0x328a39)) return ...
...
const _0x4a3e32 = _0x328a39 < 0x2 || _0x49c10c || !_0x4c5832;   // ← c) 用 <2 判断“还要不要再开一路”
...
_0x52239b = "threads" + _0x23696a + '-' + _0x27ef84;   // ← d) 线程号拼进 Headers（形如 threads3-2）
const _0x17a162 = new Headers();
```

即：**`threads` 是一个用户可调的整数并发度，单线程模式下被强制为 1，其值参与调度判断并被拼进请求头做标识。** 分片下载的调度循环我**没有**逐行还原（见 §13）。

**分片下载路径**：既可以是 `fetch(url, {signal, method, headers})`（代码里可见 `(fetch,_0x34937a,{signal:_0x5dba94,method:_0xac05a,headers:_0x42ed11,mode:...})` 这种三参调用形态），也可以是 `bgFetcher`（走 offscreen 文档，见 §8.2）。`localM3u8` / `localFrags` / `getFragsFromWorker` 表明**清单与分片的数据结构会交给 worker 保存**（`modules/web-worker.js`），主线程只拿进度。

### 4.3 多分辨率选择

官方文档（[How to Download m3u8 Videos](https://fetchv.net/blog/how-to-download-m3u8-videos)）原文：

> The browser first loads an index (usually named master.m3u8) that contains URLs of different resolution m3u8 files. Then, based on your network condition, it loads an appropriate resolution m3u8 file. **All loaded m3u8 files will be captured with the extension, so you will see multiple m3u8 files in the list.**

> If the video type is m3u8 and multi-resolution is provided, **the program will choose the maximum resolution by default.** If you don't need a maximum clear video, you can choose other resolutions.

代码侧印证：`Options` 里有 `defaultResolution`（`modules/options.js`），hls-loader 有 `$defaultResolution` / `defaultResolutionSwitch` / `currentLevel` / `currentLevelId` / `levels` / `bitrate`。**注意：FetchV 不是自己解析 master playlist 选码率，而是把每个分辨率档当成一个独立的 m3u8 资源分别嗅探出来让用户选**（因为浏览器/播放器只会加载其中一个，用户点了哪个档就下哪个档）。这一点和提问者的思路差别很大。

---

## 5. DASH（mpd）/ 分离音视频怎么处理

### 5.1 结论：**不支持 `.mpd` 清单，但能处理 DASH 风格的 fMP4 分片与分离流**

逐项证据：

1. **全站 JS 里没有任何 `.mpd` / `SegmentTemplate` / `Representation` 的处理逻辑。** 我对扩展侧 10 个 JS 文件和站点侧 3 个 loader + 8 个 worker/muxer 做了脚本化检索，`.mpd` 只在被反混淆前的乱码里偶然出现（`mpd` 只是混淆标识符子串），**没有一处是真实业务代码**。
2. **扩展嗅探白名单里没有 `.ts`**：`i = ["m3u8","m3u","mp4","3gp","flv","mov","avi","wmv","webm","f4v","acc","mkv","mp3","wav","ogg"]`（`service-worker.js`，原文已核对）。也就是说它**不逐个采集 `.ts` 分片**，而是采集 m3u8 清单再自己去拉分片。
3. **`.m4s` / `video/iso.segment` 在 Content-Type 映射表里，但不在白名单 `i` 里**（详见 §3.3 末尾的分析）：它能被接受只能靠下图的「兜底 A」——即 `Content-Range` 分支：

```js
// service-worker.js
if (!y) {
  if ("xmlhttprequest" !== c.type || !x) return;    // x = 由 Content-Range 解析出的 {chunk, total}
  if (!await CHECK_VIDEO_SRC(f, p)) return;         // 问页面：这个 URL 是不是 <video> 正在播的
  y = "mp4"
}
```

即：**当一个带 `Content-Range` 的 XHR 的 URL 恰好等于页面里 `<video>` 的 src 时，就认定它是「渐进式 MP4 / 单文件 fMP4」，记为 `type: "mp4"`**。这就是 `videodownloader` 页面处理的对象。

4. **音视频分离的合并逻辑在 `modules/web-worker.js`**（全文 27 行，已完整读出）：

```js
// fetchv.net /extensions/dist/modules/web-worker.js
const fragments = { video: [], audio: [] },
  audioVideoCopy = () => {
    const e = [...fragments.video], o = [...fragments.audio];
    let s = e.length, t = o.length;
    if (s && t) {
      let n = e[s - 1], i = o[t - 1];
      // 视频尾巴超出音频范围的，砍掉
      for (; n.start > i.end && n && i;) e.splice(s - 1, 1), s = e.length, n = e[s - 1];
      // 音频尾巴超出视频范围的，砍掉
      for (; i.start > n.end && n && i;) o.splice(t - 1, 1), t = o.length, i = o[t - 1]
    }
    return { video: e, audio: o }
  };

onmessage = async function (e) {
  const { args: o, cmd: s } = e.data;
  if ("PUSH" !== s) if ("FLUSH" !== s) if ("DATA_BACK" !== s) {
    if ("CLEAR" === s) return fragments.video.length = 0, void (fragments.audio.length = 0);
    if ("SETTIMEOUT" === s) { /* 用 setTimeout 维持 worker 心跳 */ }
  } else { const { messageId: e } = o; postMessage({ type: "response", response: { result: fragments, messageId: e, cmd: s } }) }
  else {
    const { videoInfo: e, audioInfo: t, isFmp4: n, clear: i, messageId: d, live: a } = o;
    let r = null;
    try {
      const { video: o, audio: s } = fragments;
      o.sort(((e, o) => e.sn - o.sn)), s.sort(((e, o) => e.sn - o.sn));   // 按序号排序
      if (n) {                                                            // fMP4 分支
        let n = [];
        n = a && o.length && s.length ? audioVideoCopy()
          : i ? { video: [...o], audio: [...s] } : audioVideoCopy();
        i && (o.length = 0, s.length = 0);
        const d = n.video.reduce(((e, o) => e + o.duration), 0),      // 视频总时长
              u = n.audio.reduce(((e, o) => e + o.duration), 0),      // 音频总时长
              l = e.initSegment, g = t.initSegment,
              c = [...n.video, ...n.audio],
              { FMP4Muxer: p } = await import("./fmp4-muxer.js"), m = p(i);
        m.on("progress", (e => { postMessage({ type: "progress", response: { data: e } }) }));
        r = await m.convert(d, l, u, g, c)                                  // (视频时长, 视频init, 音频时长, 音频init, 分片)
      } else {                                                              // TS 分支
        const n = { audioCodec: null, videoCodec: null };
        let d = null, u = e.initSegment || null, l = t.initSegment || null, g = [];
        g = a && o.length && s.length ? audioVideoCopy() : i ? { video: [...o], audio: [...s] } : audioVideoCopy();
        i && (o.length = 0, s.length = 0);
        const c = g.video.reduce(((e, o) => e + o.duration), 0),
              p = g.audio.reduce(((e, o) => e + o.duration), 0);
        c && (n.totalduration = c), n.audioCodec = e.audioCodec, n.videoCodec = e.videoCodec;
        p && (d = { totalduration: p, audioCodec: t.audioCodec });
        const m = [...g.video, ...g.audio], { HLSMuxer: f } = await import("./hls-muxer.js"), v = f(i);
        v.on("progress", (e => { postMessage({ type: "progress", response: { data: e } }) }));
        r = await v.convert(n, u, d, l, m)
      }
    } catch (e) { console.error(e) }
    postMessage({ type: "response", response: { result: r, messageId: d, cmd: s } })
  } else { const { frag: e } = o; ("main" === e.type ? fragments.video : fragments[e.type]).push(e) }
  , postMessage({})
};
```

**这段就是回答「提问者的 DASH 音视频配对坑」的答案**：

- 分片带 `sn`（序号）、`start`、`end`、`duration`、`type`（`"main"` 视频 / `"audio"` 音频）；
- `PUSH` 进来后按 `type` 分流到 `fragments.video` / `fragments.audio` **两个队列**；
- `FLUSH` 时先按 `sn` 排序，再用 `audioVideoCopy()` **按时间戳把两条流的尾巴裁到互相重叠**，然后算各自 `duration` 总和；
- fMP4 走 `FMP4Muxer`，TS 走 `HLSMuxer`；
- 关键是它把**两条流各自的 `initSegment`（ftyp+moov）分开传**，muxer 负责把它们合成一个多 track 的 MP4。

### 5.2 合并成 MP4 靠什么：**不是 ffmpeg，是三个自研/第三方 JS muxer**

| 输入 | muxer | 证据 |
| --- | --- | --- |
| fMP4 / self-describing（`isFmp4 = true`） | `./modules/fmp4-muxer.js`（42 501 字节，导出 `FMP4Muxer`） | `web-worker.js`、`fmp4-muxer-worker.js` |
| MPEG-TS（`isFmp4 = false`） | `./modules/hls-muxer.js`（38 809 字节，导出 `HLSMuxer`） | `web-worker.js` |
| 需要重编码 / codec 不兼容 | `./modules/ffmpeg/index.js` → ffmpeg.wasm | `ffmpeg_index.js`、worker 里的 `FFMPEG` / `FFMPEG timeout` |

`hls-muxer.js` 本身也是 javascript-obfuscator 产物（`var _0xodR='fetchv.net.v3';`），反混淆后能看到的自有标识符包括：

```
movieTimescale  timescale  outputSamples  endDTS  vTrack  aTrack  samples
tfhd  trun  traf  moof  mdat  timescale  default_sample_duration  baseMediaDecodeTime
```

——这是一套**手写的 ISO BMFF 复用器**（从 TS 里解出 H.264/AAC 后再按 MP4 box 结构重新封），不是 mux.js，也不是 mp4box.js。另一条证据：目录里有一份 `modules/iso-boxer.js`（23 494 字节，`ISOBoxer` 类），这是 **MP4Box.js 里的 ISO Box 解析器**，被三个 muxer/worker 共同依赖（rec-loader 里 `ISOBoxer` 出现 14 次、hls-loader 4 次）。

---

## 6. 加密流怎么办

### 6.1 AES-128 HLS：**扩展自己 GET key 并自己解密**

**证据文件**：fetchv.net `/extensions/dist/modules/hls-decrypter.js`（798 字节，全文）与 `/extensions/dist/modules/decrypter-worker.js`（9 906 字节）

```js
// fetchv.net /extensions/dist/modules/hls-decrypter.js（全文）
export class HLSDecrypter {
  constructor(e) { this.lastId = 0, this.workerPath = e }
  async decryptAES(e, r, t) {
    if (this.destroyed) return void console.error("Decrypter already destroyed");
    this.encryptionWorker || this.setupEncryptionWorker();
    const s = this.lastId++;
    return new Promise(((o, n) => {
      this.encryptionWorkerCallbacks.set(s, ((e, r) => { o(e) })),
      this.encryptionWorker.postMessage({ encrypted: e, iv: r, key: t, id: s }, [e])   // e 被 transfer 走，零拷贝
    }))
  }
  destroy() { this.encryptionWorker && (this.encryptionWorker.terminate(), this.encryptionWorker = null), this.destroyed = !0 }
  setupEncryptionWorker() {
    this.encryptionWorker = new Worker(this.workerPath),
    this.encryptionWorker.addEventListener("message", (e => {
      const r = e.data;
      this.encryptionWorkerCallbacks.get(r.id)(r.decrypted), this.encryptionWorkerCallbacks.delete(r.id)
    })),
    this.encryptionWorkerCallbacks = new Map
  }
}
```

```js
// fetchv.net /extensions/dist/modules/decrypter-worker.js（头部，全文可读）
function decrypt(e) {
  const t = new Uint8Array(e.encrypted),
        n = function (e) {                                    // IV：4 个大端 uint32
          const t = new DataView(e), n = new Uint32Array(4);
          for (let e = 0; e < 4; e++) n[e] = t.getUint32(4 * e);
          return n
        }(e.iv),
        r = new Uint32Array(e.key);                           // key：4 个 uint32 = 16 字节 = AES-128
  new aesDecrypter.Decrypter(t, r, n, (function (t, n) {
    postMessage({ decrypted: n.buffer, id: e.id }, [n.buffer])
  }))
}
```

`decrypter-worker.js` 的剩余部分是 **hls.js 生态里 `aes-decrypter` 的 UMD 打包**（纯 JS，AES-CBC + PKCS7，代码里有标准的 AES S-box 生成循环与 `aesDecrypter` 全局导出）。

**这套流程说明**：

- key 来自 HLS 清单里的 `EXT-X-KEY:URI=...`，**由 hls.js 的 `decryptdataLoader` 负责 GET 回来**（hls-loader 反混淆后可见 `decryptdataLoader` 与 `HLSDecrypter` 同处一室）；
- FetchV 只是把 `(encrypted, iv, key)` 送进自己的 worker；
- IV 是标准的 128-bit；key 是 16 字节 → **只支持 AES-128，不支持 AES-256/SAMPLE-AES**（代码里 `new Uint32Array(e.key)` 是 4 个 uint32，写死 16 字节）；
- 解密在 `Worker` 里做，主线程不阻塞；`Blob` 数组用 transfer 列表零拷贝转移。

### 6.2 Widevine / DRM：**明确不支持；FetchV 自己的代码从不接触 DRM API**

三条独立证据：

1. **代码检索**：我对扩展侧与站点侧全部 JS 做了检索，**没有任何 `crypto.subtle` 调用**，也**没有 `encrypted` 事件监听**。唯一出现的 `requestMediaKeySystemAccess`（扩展侧 `js/hls-player.js` 5 处、站点侧 `modules/hls.es.js` 5 处）**都在 hls.js 库自己的源码里**（hls.js 的 EME 支持路径），不是 FetchV 的业务代码——两份文件都是 hls.js 的官方发行打包。

   **（推断，依据是 EME 工作原理）** 即使 hls.js 内建了 EME 路径，FetchV 也没有传 `emeEnabled` / `drmSystems` / `licenseXhrSetup` 这类配置，且 Widevine 解开后的明文只在 CDM 内部，不会进入 JS 堆，所以 FetchV 拿不到它。我**没有**在真实 Widevine 站点上跑过 FetchV 来实测（见 §13.5）。
2. **官方文档**（[Why FetchV Not Support Youtube](https://fetchv.net/blog/not-support-youtube)）原文：

   > YouTube uses digital rights management technology to protect its video content. **FetchV is also unable to provide downloading support for other videos that use digital rights protection.**
   > FetchV is only suitable for downloading online videos that use common web video playback technologies. ... **FetchV cannot download online videos that do not use these playback technologies or are encrypted.**

3. **代码里的硬性禁用**：

```js
// service-worker.js 与 popup.js 都有一份
const a = ["youtube.com", "globo.com"];
// service-worker.js：命中就 return（不嗅探）
for (const e of a) if (R.endsWith(e)) return;
// popup.js：命中就直接显示“不支持”面板
this.disableDetailUrl = "/blog/not-support-youtube";
const s = ["youtube.com","globo.com"];
if (0 === this.tab.url.indexOf("http")) {
  const e = new URL(this.tab.url).hostname;
  for (const t of s) if (e.endsWith(t)) return this.$loading.remove(), this.$disable.classList.remove("d-none"), void (this.disable = !0)
}
```

```json
"popup_disable": { "message": "对不起，我们无法为你下载此页面的视频。" }
```

**遇到 DRM 时的实际行为**：扩展不会报错，也不会尝试绕过——`youtube.com` 直接进禁用名单；其他 Widevine 站点上，受保护的分片不会产生可嗅探的明文媒体请求（浏览器在 CDM 内部解密），因此**列表里干脆什么都不出现**，用户只能看到空列表提示（`popup_no_resource` / `popup_no_resource_lead`）。

---

## 7. 下载落盘走哪条路

### 7.1 答案：`Blob` + `<a download>`（小文件）/ StreamSaver Service Worker 流（> 2 GiB）

**证据文件**：fetchv.net `/extensions/dist/modules/saveAs.js`（894 字节，全文）

```js
// fetchv.net /extensions/dist/modules/saveAs.js（全文，仅格式化）
import { streamSaver } from "./streamSaver/index.js";

const baseURL = import.meta.url;
if (baseURL) { const e = new URL("streamSaver/mitm.html", baseURL).href; e && (streamSaver.mitm = e) }

const directSave = (e, t) => {                        // 小文件路径
  const r = URL.createObjectURL(e), a = document.createElement("a");
  return a.setAttribute("href", r), a.setAttribute("download", t),
         document.body.appendChild(a), a.click(),
         new Promise((e => { setTimeout((() => { URL.revokeObjectURL(r), a.remove(), e() }), 3e3) }))
};

const streamSave = (e, t) => new Promise((r => {      // 大文件路径
  try {
    const a = streamSaver.createWriteStream(t, { size: e.size }), m = e.stream();
    if ("pipeTo" in m && "undefined" != typeof WritableStream)
      return m.pipeTo(a).then((() => { r() })).catch((e => { r() }));
    m.cancel(), directSave(e, t).then((() => { r() }))
  } catch (a) { directSave(e, t).then((() => { r() })) }
}));

export const saveAs = (e, t) => new Promise((r => {
  streamSaver.mitm && e.size > 2147483648                  // ← 阈值 2 GiB = 2147483648 字节
    ? streamSave(e, t).then((() => { r() }))
    : directSave(e, t).then((() => { r() }))
}));
```

**不是** `chrome.downloads.download`（manifest 没有 `downloads` 权限，代码里也没有任何调用），**不是** File System Access API（全站检索 `showSaveFilePicker` / `createWritable` / `showDirectoryPicker` 全部 0 命中），**不是** Native Messaging。

### 7.2 StreamSaver 是怎么把流变成磁盘文件的

**证据文件**：`/extensions/dist/modules/streamSaver/index.js`（3 955 字节）、`mitm.html`（5 544 字节）、`sw.js`（1 754 字节）

`mitm.html` 的头部注释就是最好的说明（原文）：

> `mitm.html` is the lite "man in the middle". This is only meant to signal the opener's messageChannel to the service worker - when that is done this mitm can be closed but it's better to keep it alive since this also stops the sw from restarting. **The service worker is capable of intercepting all request and fork their own "fake" response** - wish we are going to craft when the worker then receives a stream then the worker will tell the opener to open up a link that will start the download

机制链条：页面（`fetchv.net`）→ `streamSaver.createWriteStream` → 隐 iframe 加载 `streamSaver/mitm.html` → 注册同源 `sw.js` → `MessageChannel` 把 `ReadableStream` 转移给 SW → SW 伪造一个 HTTP 响应，把流当 body 挂在一个假 URL 上 → 页面用 `<a href=假URL>` 触发浏览器原生下载（而浏览器原生下载是**边收边写盘**的）。`mitm.html` 里还有个 `keepAlive` 的心跳防止 SW 被回收：

```html
let keepAlive = () => {
  keepAlive = () => {}
  var ping = location.href.substr(0, location.href.lastIndexOf('/')) + '/ping'
  var interval = setInterval(() => { if (sw) { sw.postMessage('ping') } else { fetch(ping).then(res => res.text(!res.ok && clearInterval(interval))) } }, 10000)
}
```

### 7.3 扩展 ↔ 页面之间怎么交接任务

**证据文件**：`popup.js` `createTab()`、`service-worker.js`、`js/content.js`（1 993 字节，全文）

```js
// popup.js
createTab(e, t = !1, s = null) {
  e.initiator = this.tab.url,
  e.title = this.tab.title.trim() || this.tab.url,
  chrome.storage.local.set({ queue: e }, (() => {          // ← 任务写进 storage.queue
    const { options: e, langDir: i } = this;
    let o = "bufferrecorder";
    if (!t) { if (!s) return; o = "hls" === s ? "m3u8downloader" : "videodownloader" }
    if ("zh-CN" !== this.langCode || this.isMobile)
      chrome.tabs.create({ url: `${e.site}${i}/${o}`, index: this.tab.index + 1 }, (e => { window.close() }));
    else { o = `${i}/${o}`;
      const t = `${e.site}/router.html?path=${encodeURIComponent(o)}`;
      chrome.tabs.create({ url: t, index: this.tab.index + 1 }, (e => { window.close() })) }
  }))
}
```

页面侧（`js/content.js`）在 `document_end` 取走 queue，并建立一条 `BroadcastChannel('channel-' + tabId)` 作为双向数据通道：

```js
// js/content.js（关键部分，格式化）
let t = null;
chrome.storage.local.get(["queue"], (async ({ queue: a }) => {
  if (a) {
    const { currentTabId: s, tabsCount: o } = await new Promise((e => {
      chrome.runtime.sendMessage({ cmd: "GET_TAB_ID", parameter: {} }, (t => { e(t) }))
    }));
    a.tabId = s, a.tabsCount = o, a.version = Number(e),
    t = new BroadcastChannel(`channel-${s}`),
    t.addEventListener("message", (e => {
      const { id: a, cmd: s, data: o, response: n } = e.data;
      if ("GET_ALL_STORAGE" !== s)
        "BG_FETCH" !== s
          ? chrome.runtime.sendMessage({ cmd: s, parameter: o }, (e => { n && t.postMessage({ id: a, data: e }) }))
          : chrome.runtime.sendMessage({ cmd: s, parameter: o }, (e => {
              e.ok && e.blobURL
                ? fetch(e.blobURL).then((e => { if (e.ok) return e.blob(); ... }))
                    .then((e => { t.postMessage({ id: a, data: { ok: !0, content: e } }) }))
                    .catch((e => { t.postMessage({ id: a, data: { ok: !1, statusText: e.name } }) }))
                    .finally((() => { URL.revokeObjectURL(e.blobURL) }))
                : t.postMessage({ id: a, data: e })
            }));
      else { const { storageKey: e } = o; chrome.storage.local.get([e], (s => { ... })) }
    })),
    ...
    chrome.storage.local.remove(["queue"])
  }
  ...
}))
```

**这就是它为什么必须开新标签页**：MV3 的 Service Worker 只有 30 秒不活动就被杀，且不能创建 `WritableStream` 交给 Service Worker 做流式下载；`<a download>` 与 StreamSaver 都必须在**页面**里执行。

---

## 8. 合并/转封装在哪做

### 8.1 全景表

| 场景 | 在哪里做 | 用什么 | 证据 |
| --- | --- | --- | --- |
| HLS（TS 分片）→ MP4 | fetchv.net 页面的 Web Worker | 自研 `HLSMuxer`（`modules/hls-muxer.js`，38 809 B）+ `ISOBoxer` | `web-worker.js`、`hls-muxer.js` |
| HLS（fMP4 分片）→ MP4 | 同上 | 自研 `FMP4Muxer`（`modules/fmp4-muxer.js`，42 501 B） | `web-worker.js`、`fmp4-muxer-worker.js` |
| 渐进式 MP4 的 Range 拼接 | 同上 | 纯 JS 拼接（`Interval` / `intervalSize` / `bytesCovert` / `contentLength`） | `mp4-loader.js` 反混淆标识符 |
| MP4 分离音视频（DASH 式）合并 | Worker `mp4-worker.js` | **Mediabunny** `Input`/`Output`/`Conversion`/`Mp4OutputFormat{fastStart:"fragmented", minimumFragmentDuration:10}` + `FMP4Muxer` | `modules/mp4-worker.js`（2 185 B，全文） |
| MSE 录制（直播/难搞的视频） | 页面主线程（mediabunny 编码） | **Mediabunny** `Output` + `MediaStreamVideoTrackSource` / `MediaStreamAudioTrackSource` + WebCodecs | `js/injection.js`、`js/mediabunny.js`（127 625 B） |
| codec 不兼容时的兜底 | `modules/ffmpeg/index.js` | **ffmpeg.wasm** | `ffmpeg_index.js`、worker 里的 `FFMPEG` / `FFMPEG timeout` |

### 8.2 ffmpeg.wasm 的用法与「有没有多线程」

**证据文件**：`/extensions/dist/modules/ffmpeg/index.js`（1 809 字节，全文）

```js
// fetchv.net /extensions/dist/modules/ffmpeg/index.js（全文，格式化）
export const ffmpeg = (() => {
  const e = import.meta.url;
  let a = null;
  const t = new URL("ffmpeg-core.v2.wasm", e).pathname,     // ← 独立 .wasm 文件
        n = new URL("version.v2.json", e).pathname,
        r = new URL("ffmpeg-core.v2.js", e).pathname;       // ← 独立 core js
  const o = async e => {                                     // 带 28 秒超时的 fetch
    try {
      const a = new AbortController, t = a.signal, n = setTimeout((() => { a.abort() }), 28e3),
            r = await fetch(e, { signal: t });
      clearTimeout(n); if (!r.ok) throw new Error("Fetch Error" + r.status); return r
    } catch (e) { return null }
  };
  const l = async () => {                                    // 下载 wasm 并用 pako 解压
    const e = await o(t);
    if (e) {
      const a = new Uint8Array(await e.arrayBuffer()),
            { pako: t } = await import("./pako.js"), n = t.inflate(a);
      return new Blob([n], { type: "application/wasm" })
    }
    return null
  };
  const s = async () => { /* 下载 ffmpeg-core.v2.js 原始文本 */ };
  const i = () => new Promise((async e => {
    const { db: t } = await import("./dexie.js");            // ← IndexedDB 缓存
    a = t;
    const r = {}, i = [];
    if (t) {
      const e = [{ fileName: "wasm", urlName: "wasmURL", loader: l },
                 { fileName: "core", urlName: "coreURL", loader: s }];
      for (const a of e) {
        const { fileName: e, urlName: n, loader: o } = a;
        let l = await t.get({ fileName: e });                // 缓存命中 → 直接 URL.createObjectURL
        if (l) if (l.data) i.push({ fileBlob: l });
          else { const e = await o(); e ? (l.data = e, l.version = 0, i.push({ fileBlob: l, newBlob: e })) : l = null }
        else { const a = await o(); a && (l = { fileName: e, data: a, version: 0 }, i.push({ fileBlob: l, newBlob: a })) }
        l ? (l.loader = o, r[n] = URL.createObjectURL(l.data)) : r[n] = null
      }
      i.length > 0 && (async e => {                          // 版本号变了就重新下载
        if (!a) return;
        const t = await o(n);
        if (t) { const n = await t.json();
          for (const t of e) { let { fileBlob: e, newBlob: r } = t;
            parseInt(e.version) !== parseInt(n.version) && (e.version = n.version,
              r || (r = await e.loader()), r && (e.data = r, delete e.loader, a.put(e))) } }
      })(i)
    }
    e(r)
  }));
  return new Promise((e => {
    import("./ffmpeg.js").then((async ({ FFmpegWASM: a }) => {
      try {
        const { FFmpeg: t } = a, n = new t, { wasmURL: r, coreURL: o } = await i();
        if (!r || !o) return void e(null);
        await n.load({ coreURL: o, wasmURL: r }), e(n)
      } catch (a) { e(null) }
    }))
  }))
})();
```

**多线程问题的答案：确定是单线程（ST）。** 四条独立且可复现的硬证据：

1. **我从 `https://fetchv.net/extensions/dist/modules/ffmpeg/ffmpeg-core.v2.wasm` 实测下载了这个文件**：
   - 服务器响应：`Content-Type: application/wasm`、`Content-Length: 562601`、**没有 `Content-Encoding`**、`Last-Modified: Tue, 20 Aug 2024 11:33:34 GMT`、`Server: cloudflare`；
   - 落盘后前 4 字节是 `78 9C D4 BD` —— **zlib 流头**，证实「服务端不做 Content-Encoding，客户端用 pako 解压」这一设计（对应 `index.js` 里的 `pako.inflate(a)`）；
   - 用 `zlib.inflateSync` 解压后：**1 166 201 字节（≈1.11 MiB）**，魔数 `00 61 73 6D`（`\0asm`，标准 wasm）。
2. **在解压后的 wasm 里检索**：`SharedArrayBuffer` × 0、`Atomics` × 0、`worker` × 0；只有 3 处 `pthread` 命中，且全部来自同一段**编译命令行字符串**：

```
-I/opt/include -O3 -msimd128' --disable-pthreads --disable-w32threads --disable-os2thre...
```

   —— 即这个 wasm 是**显式用 `--disable-pthreads` 编译**的，并开启了 `-msimd128`（SIMD 是有的，多线程没有）。
3. **`ffmpeg-core.v2.js`（87 071 字节）里** `pthread` × 0、`SharedArrayBuffer` × 0、`new Worker` × 0、`Atomics` × 0（只有 1 处 `importScripts`，是 Emscripten 的普通胶水）。
4. **没有 COOP/COEP**：`curl -D -` 抓 `https://fetchv.net/m3u8downloader` 的响应头，**没有 `Cross-Origin-Opener-Policy`、没有 `Cross-Origin-Embedder-Policy`** —— 没有这两个头，浏览器就不会暴露 `SharedArrayBuffer`，MT 版 ffmpeg.wasm 根本无法工作。加载时也只传 `{ coreURL, wasmURL }` 而**没有 `workerURL`**（`@ffmpeg/ffmpeg` 的 MT 版必须指定它；`ffmpeg.js` 打包里虽留有 `workerURL` 的解析代码，但那个路径不会被走到——我探测 `/extensions/dist/modules/ffmpeg/814.ffmpeg.js` 与 `/extensions/dist/modules/ffmpeg/ffmpeg-worker.js` 均返回 404）。

**wasm 是远程拉取 + 本地缓存**，不打包进扩展：文件名 `ffmpeg-core.v2.wasm`，用 **pako 解压**，并用 **Dexie（IndexedDB）** 缓存，`version.v2.json` 当前内容为：

```json
{"version": 2}
```

`Last-Modified: 2024-08-20` 这个时间戳也是个旁证：**这个 ffmpeg.wasm 构件从 2024 年 8 月起就没更新过**，而站点博客最后一篇是 2024-02-02。

- 站点侧的 `ffmpeg.js`（3 856 字节）是 `@ffmpeg/ffmpeg` 的 ESM 打包，导出 `FFmpegWASM`，消息协议枚举与上游一致：

```js
// fetchv.net /extensions/dist/modules/ffmpeg/ffmpeg.js
function (e) { e.LOAD="LOAD", e.EXEC="EXEC", e.WRITE_FILE="WRITE_FILE", e.READ_FILE="READ_FILE",
  e.DELETE_FILE="DELETE_FILE", e.RENAME="RENAME", e.CREATE_DIR="CREATE_DIR", e.LIST_DIR="LIST_DIR",
  e.DELETE_DIR="DELETE_DIR", e.ERROR="ERROR", e.DOWNLOAD="DOWNLOAD", e.PROGRESS="PROGRESS",
  e.LOG="LOG", e.MOUNT="MOUNT", e.UNMOUNT="UNMOUNT" }
```

调用方式在 `rec-loader` 里可见（反混淆后的字面量）：写临时文件 → `exec(['-i', in, '-c', 'copy', ...])` → 读回 → `deleteFile`，即**纯 remux（`-c copy`）不做重编码**，并且有 50 秒超时（`FFMPEG timeout` / `setTimeout(..., 0xc350)`）。

### 8.3 Mediabunny 是什么

**证据文件**：`js/mediabunny.js`（127 625 字节，扩展侧）与 `/extensions/dist/modules/mediabunny.js`（397 355 字节，站点侧）

- 版权头：`Copyright (c) 2025-present, Vanilagy and contributors` + MPL-2.0 —— 即开源库 [mediabunny](https://github.com/Vanilagy/mediabunny)。
- 扩展侧那份文件尾部的 sourcemap 内嵌路径证明它是 ESM 打包：

```
mediabunny/dist/modules/src/writer.js:
mediabunny/dist/modules/src/target.js:
mediabunny/dist/modules/src/isobmff/isobmff-misc.js:
mediabunny/dist/modules/src/isobmff/isobmff-reader.js:
mediabunny/dist/modules/src/isobmff/isobmff-muxer.js:
mediabunny/dist/modules/src/custom-coder.js:
mediabunny/dist/modules/src/packet.js:
mediabunny/dist/modules/src/pcm.js:
mediabunny/dist/modules/src/sample.js:
mediabunny/dist/modules/src/output-format.js:
mediabunny/dist/modules/src/encode.js:
mediabunny/dist/modules/src/media-source.js:
mediabunny/dist/modules/src/output.js:
mediabunny/dist/modules/src/index.js:
```

- 我对扩展侧那份做了能力探测（脚本化计数）：`Mp4OutputFormat` × 1、`fastStart` × 10、`fragmented` × 5、`NullTarget` × 1；**`WebAssembly` / `wasm` / `SharedArrayBuffer` × 0**（`SharedArrayBuffer` 仅在 2 处出现，是类型守卫，不是用它做多线程）；**`crypto.subtle` / `decrypt` / `AES` / `cenc` 全部 × 0**——**Mediabunny 在这里只做封装/解封装，不做解密**（这再次印证 §6.1：AES 解密是另一条独立链路）。
- 站点侧 `modules/mp4-worker.js` 里的用法（全文可读）：

```js
// fetchv.net /extensions/dist/modules/mp4-worker.js
import { Input, Output, ALL_FORMATS, BlobSource, NullTarget, Mp4OutputFormat, Conversion } from "./mediabunny.js";
import { ISOBoxer } from "./iso-boxer.js";

const media2MP4 = async t => {
  let e, n; const o = []; let a = null;
  const i = new Input({ formats: ALL_FORMATS, source: new BlobSource(t) }),
        s = await i.computeDuration(),
        [r] = await i.getTracks(), u = r.type,
        c = new Output({ target: new NullTarget,
          format: new Mp4OutputFormat({ fastStart: "fragmented", minimumFragmentDuration: 10,
            onFtyp: t => { e = t },
            onMoov: t => { const n = new Uint8Array(e.length + t.length); n.set(e, 0); n.set(t, e.length); a = n.buffer },
            onMoof: t => { n = t },
            onMdat: t => { const e = new Uint8Array(n.length + t.length); e.set(n, 0); e.set(t, n.length);
              const a = new Blob([e], { type: "application/octet-stream" }); o.push({ type: u, data: a }) } }) });
  const l = await Conversion.init({ input: i, output: c });
  await l.execute();
  return { duration: s, initSegment: a, chunks: o, type: u }
};

onmessage = async function (t) {
  const { args: e, cmd: n } = t.data;
  if ("GET_INFO" !== n)
    if ("MERGER_MEDIA_TRACK" !== n);
    else { /* media1 + media2 各自 media2MP4，再 FMP4Muxer.convert(vDur,vInit,aDur,aInit,[...vChunks,...aChunks]) */ }
  else { /* 用 ISOBoxer 解析 moov/mvhd/trak/mdia/mdhd/hdlr，读出 duration 与 WxH，供预览与列表显示 */ }
};
```

**`MERGER_MEDIA_TRACK` 这个命令名与它的实现，就是 FetchV 处理「DASH 式音视频分离 MP4」的完整答案**：两次 `media2MP4` 把两个独立文件各自demux 成 `{duration, initSegment, chunks}`，再交给 `FMP4Muxer.convert` 合成单文件。

### 8.4 MSE 录制模式（bufferrecorder）到底怎么录

这条链路在扩展侧是**完全明文**的，可以逐行读。

**证据文件**：`js/injection.js` 的 `class t`（约 60 行有效代码）

```js
// js/injection.js —— MseRecorder（命名来自类内字段语义，原文类名是混淆的短名 t）
async createRecorder() {
  const { video: e } = this;
  if (e) {
    try {
      this.stream || (this.stream = e.captureStream());          // ① 抓 <video> 的 MediaStream
      const { Output: t, NullTarget: o, Mp4OutputFormat: n,
              MediaStreamAudioTrackSource: r, MediaStreamVideoTrackSource: i,
              getFirstEncodableVideoCodec: s, getFirstEncodableAudioCodec: a,
              QUALITY_MEDIUM: d } = this.mediabunny,               // ② 动态 import 进来的 mediabunny
            [c] = this.stream.getVideoTracks(), [l] = this.stream.getAudioTracks();

      let h, u, m = 0, p = 0;
      const f = new t({
        target: new o,                                             // ③ NullTarget：不要文件，只要回调
        format: new n({
          fastStart: "fragmented", minimumFragmentDuration: 3,
          onFtyp: e => { h = e },
          onMoov: e => {                                           // ④ 头出来立刻发走
            const t = new Uint8Array(h.length + e.length); t.set(h, 0); t.set(e, h.length);
            const o = new Blob([t], { type: "application/octet-stream" }), n = URL.createObjectURL(o),
                  { onended: r, recorderTabId: i } = this, s = this.getVideoQuality();
            chrome.runtime.sendMessage({ cmd: "REC_ON_DATA",
              parameter: { recorderTab: i, data: { url: n, type: "header", onended: r, quality: s } } })
          },
          onMoof: (e, t, o) => { p = o - m, m = o, u = e },         // ⑤ 记住每个 moof 的时间戳与时长
          onMdat: e => {                                           // ⑥ 每个 moof+mdat 凑成一个分片发走
            const t = new Uint8Array(u.length + e.length); t.set(u, 0); t.set(e, u.length);
            const o = new Blob([t], { type: "application/octet-stream" }), n = URL.createObjectURL(o),
                  { onended: r, recorderTabId: i } = this, s = this.getVideoQuality();
            if (chrome.runtime.sendMessage({ cmd: "REC_ON_DATA",
                  parameter: { recorderTab: i, data: { url: n, type: "segment", onended: r,
                    lastMoofTimestamp: m, lastMoofDuration: p, quality: s } } }),
                this.outputChunksCount++, !this.onended && this.endDuration) {
              const { currentTime: e } = this.video;
              (Math.abs(e - this.endDuration) <= p || e >= this.endDuration) && this.stop()   // ⑦ 到点自动停
            }
          }
        })
      });
      this.output = f;
      let g = null, v = null;
      if (l) {                                                     // ⑧ 音频轨：AAC 优先 128 kbps
        const e = 128e3, t = await a(["aac", "opus", "mp3", "vorbis"], { bitrate: e });
        t && (g = new r(l, { codec: t, bitrate: e }), g.errorPromise.catch((e => { this.error(e.message) })))
      }
      if (c) {                                                     // ⑨ 视频轨：avc 优先，码率按分辨率估算
        const { width: e, height: t, frameRate: o } = c.getSettings(),
              n = this.getVideoBitrate(e, t, o) || d, r = { width: e, height: t };
        Number.isFinite(n) && (r.bitrate = n);
        const a = await s(["avc", "vp8", "hevc", "vp9", "av1"], r);
        a && (v = new i(c, { codec: a, bitrate: n }), v.errorPromise.catch((e => { this.error(e.message) })))
      }
      if (!v) return void this.error("No available video tracks found");
      f.addVideoTrack(v), g && f.addAudioTrack(g), f.start()
    } catch (e) { this.error(e.message) }
    e.addEventListener("ended", this.videoEndListener)
  }
}
```

**录制模式（MSE Buffer Mode）的真实机制是：不是「劫持 appendBuffer 再 remux」，而是「`video.captureStream()` + WebCodecs 重编码 + mediabunny 现封 fMP4」。** 它把 `<video>` 元素的解码后画面重新编码成 H.264/AAC 的 fMP4 分片，`onMoov` 发出 `type:"header"`、每个 `onMdat` 发出 `type:"segment"`，通过 `REC_ON_DATA` → Service Worker → `BroadcastChannel` → recorder 标签页 → `web-worker.js` 的 `fragments` 队列 → `FMP4Muxer` 合并。

**为什么文案说「可以倍速播放加快录制」**：因为录制速度被播放速度限制（必须真的解码出帧），所以 FetchV 用两个手段加速：
1. `REC_SPEED_UP` → `injection.js` 的 `speedUp(e)` → 把所有 `video[src^="blob:"]` 的 `playbackRate` 调高；
2. `hook.js` 里对 `currentTime` setter 的劫持 + `start()` 里 `n.currentTime = 起始秒` 后 `setTimeout(() => n.play(), 1000)`，即**跳播**。

对应官方文案（`_locales/zh_CN/messages.json`）：

```json
"popup_record_mode_mse":         { "message": "MSE(缓冲模式)" }
"popup_record_mode_mse_tooltip": { "message": "录制播放器的缓冲，优点是能通过倍速播放和跳跃式缓冲来加快录制速度，缺点是兼容性较差，可能无法正常处理特殊结构的媒体流。" }
"popup_record_mode_msr":         { "message": "MSR(录屏模式)" }
"popup_record_mode_msr_tooltip": { "message": "录制播放器的画面和声音，兼容性比MSE方式好，缺点是不能通过倍速播放和跳跃式缓冲来加快录制速度，建议直播和MSE无法录制的视频使用此方式。" }
```

**另一条路（MSR / 录屏模式）走的是浏览器原生 `MediaRecorder`**：

```js
// js/injection.js
getRecorderMimeType() {
  return MediaRecorder.isTypeSupported("video/webm;codecs=vp8") ? "video/webm;codecs=vp8,opus"
       : MediaRecorder.isTypeSupported("video/webm;codecs=vp9") ? "video/webm;codecs=vp9,opus"
       : "video/webm"
}
```

**值得注意的取舍**：MSR 用 `MediaRecorder`（VP8/VP9 → WebM，有画质损失），MSE 模式用 WebCodecs + mediabunny（H.264/AAC → fMP4，画质接近无损但依赖浏览器支持）。**hook.js 只服务 MSE 模式**（它只在 `fv_recorder_tab` 存在时激活，而这是 MSE 录制路径设的），MSR 模式与 `hook.js` 无关。

---

## 9. 请求头怎么补

### 9.1 三条互补的机制

| 场景 | 机制 | 代码位置 |
| --- | --- | --- |
| HLS 分片带防盗链（需要 Referer/Origin） | `declarativeNetRequest` session rule，`modifyHeaders` 只对 `origin` / `referer` 做 `set` | `popup.js` `creatRules()` / `setRules()` |
| 下载页自己发的请求带回放的头 | 把嗅探到的原始请求头（去掉 `range`/`content-length`/`content-type` 等）作为 `options.headers` 交给 `Fetcher` | `service-worker.js` 入账逻辑 + 站点 `Fetcher` |
| 跨域且 CORS 不允许（要带 Cookie） | `chrome.offscreen` 文档里 `fetch(url, { mode:"cors", credentials:"include", headers })` | `js/offscreen.js`（618 字节，全文） |

**`js/offscreen.js` 全文（这是它能带 Cookie 跨域取数据的关键）：**

```js
// js/offscreen.js（全文，仅格式化）
chrome.runtime.onMessage.addListener((function (e, t, o) {
  const { cmd: r, parameter: n } = e;
  if ("OFFSCREEN_FETCH_DATA" === r) {
    let { url: e, headers: t, method: r } = n,
        s = new AbortController,
        a = setTimeout((() => { s.abort(), s = null }), 2e4);      // 20 秒超时
    const u = { signal: s.signal, method: r, mode: "cors", credentials: "include", headers: t };
    return fetch(e, u)
      .then((e => { if (e.ok) return e.blob(); o({ ok: !1, statusText: `Fetch Error-${e.status}` }) }))
      .then((function (e) { o({ ok: !0, blobURL: URL.createObjectURL(e) }) }))
      .catch((function (e) {
        "AbortError" === e.name ? o({ ok: !1, statusText: "Request Timeout" }) : o({ ok: !1, statusText: e.messsage })
      }))                                                          // ↑ 上游原样保留了拼接错误 messsage
      .finally((() => { clearTimeout(a), a = null })), !0
  }
}));
```

对应 Service Worker 侧的转发：

```js
// service-worker.js
if ("BG_FETCH" === a) {
  let { url: e, headers: t, method: o } = c;
  return i().then((() => {                                         // i() = 确保 offscreen 文档存在
    r ? chrome.runtime.sendMessage({ cmd: "OFFSCREEN_FETCH_DATA", parameter: { url: e, headers: t, method: o } },
          (e => { !chrome.runtime.lastError && e || (e = { ok: !1, statusText: "Background Fetch Error" }), s(e) }))
      : s({ ok: !1, statusText: "Offscreen Error" })
  })), !0
}
```

```js
// service-worker.js —— offscreen 文档的创建
const i = async () => {
  if (!r) if ("offscreen" in chrome) {
    const e = "offscreen.html";
    if (r = await a(e), r) return;
    try {
      await chrome.offscreen.createDocument({ url: e, reasons: [chrome.offscreen.Reason.BLOBS],
        justification: "Convert blob data to blob URL" }), r = !0
    } catch (e) { r = !1 }
  } else r = !1
};
```

**权限选择的依据**：`chrome.cookies` **没有**被申请（manifest 里没有），为什么还能带 Cookie？——因为 `credentials: "include"` + 同源/带 `SameSite=None` 的 Cookie 会由浏览器自动带上，而**请求头里的 `Cookie` 是 `onBeforeSendHeaders` 记录的**（`extraHeaders` 选项让它能看见 `Cookie`）。`js/injection.js` 里的 `checkTextContent` 也做了同样处理：

```js
for (const e of t) a.headers[e.name] = e.value, "cookie" === e.name.toLowerCase() && (a.credentials = "include");
```

### 9.2 防死循环：`X-Original-Request-Id`

自己发出去的请求会被自己的 `webRequest` 监听器再看到一次。FetchV 的解法是给请求打哨兵头，嗅探端识别到就跳过：

```js
// js/injection.js —— 发请求时打标
a.headers["X-Original-Request-Id"] = n;

// service-worker.js —— 嗅探端认标
if (O.some((e => "x-original-request-id" === e.name.toLowerCase()))) return;
```

**这是一个很实用的小技巧，提问者可以直接借用。**

### 9.3 站点侧：防盗链补齐的边界

`creatRules()` 只处理 `origin` 和 `referer` **两个头**，且**只有请求头里真的存在这两个头时**才下规则（`return s ? t : null`）。**User-Agent 不做改写**——站点侧 `Fetcher` 是直接用浏览器自己的 UA 发请求，天然一致。

---

## 10. 有没有 Native Messaging / 本地辅助进程

**没有。** 三条证据：

1. `manifest.json` 的 `permissions` 里**没有 `nativeMessaging`**，`host_permissions` 只有 `http/https`，没有 `chrome-extension://` 之外的特权通道。
2. 扩展侧全部 10 个 JS 文件检索 `nativeMessaging`、`connectNative`、`sendNativeMessage` —— **0 命中**。
3. 站点侧全部 JS 检索同样的关键词 —— **0 命中**。

**但有一个容易混淆的点**：fetchv.net 的首页/下载页上挂着**同一个开发者的另一个产品**的广告位，指向 `https://efetch.net/cn`，文案是：

```
EFetch 视频下载器 —— FetchV桌面版本，更稳健的下载方式，更好地管理下载文件。  立即体验
```

`/static/downloader.js` 里的实现（含 unicode 转义原文）：

```js
// fetchv.net /static/downloader.js
function customAds() {
    const lang = navigator.language.toLowerCase();
    const isSimplifiedChinese = lang === 'zh-cn' || lang.startsWith('zh-cn-');
    const userAgent = navigator.userAgent;
    const isWindows = userAgent.includes('Win32') || userAgent.includes('Windows');
    if (!isSimplifiedChinese || !isWindows) return;
    ...
    backupad.innerHTML = `<div class="px-5 py-3 border text-start position-relative bg-white">
        ...
        <span class="fs-3 fw-bold">EFetch 视频下载器</span>
        <p class="lead">—— FetchV桌面版本，更稳健的下载方式，更好地管理下载文件。</p>
        ...
        <a class="btn btn-lg btn-primary stretched-link px-5 py-3" href="https://efetch.net/cn" target="_blank">立即体验</a>
        ...`;
}
```

所以「FetchV 有桌面版」是真的，但**它是独立产品，与浏览器扩展之间没有任何代码级通道（没有 Native Messaging、没有本地端口、没有自定义协议）**。扩展不会调用它，也不会把 URL 交给它。

---

## 11. 架构演进痕迹

坦白说：**`manifest.json` 没有 `version_history`，扩展目录里没有 changelog，fetchv.net 的博客从 2024 年起就没更新过，我没有拿到权威的版本变更记录。** 因此本节只列**能从代码里看出的事实**，以及**明确标注为推断的演进方向**。

### 11.1 能确证的事实（代码里同时存在两代做法的痕迹）

| 痕迹 | 证据 | 说明 |
| --- | --- | --- |
| 旧的「后缀名单」式嗅探被保留为新逻辑的兜底 | `service-worker.js` 里 `o = ["m3u8","m3u","mp4","webm","avi","ogg","flv","mkv","3gp","mp3"]` 这一串既被塞进 `stream` 映射表当 `application/octet-stream` 的候选扩展名，又作为 `y = o.includes(r) ? r : null` 的最后兜底 | 典型的「先按后缀猜，后来改成按 Content-Type 判，但旧名单留下当 fallback」 |
| `MV3` 迁移把重活搬到了站点 | manifest 是 MV3 + `service_worker`；同时站点上存在 `/extensions/dist/` 这一整套模块（3 个 loader + 9 个 module + worker + ffmpeg） | **推断**：MV2 时代这些很可能在扩展的 background page 里，MV3 强制 service worker 后搬到了站点页面。依据是目录名 `extensions/dist`（「扩展的产物」）与 manifest 里为 fetchv.net 三个页面专门配的 content script |
| 同一种媒体类型有多个并行实现 | 站点侧同时存在 `mp4-worker.js`（用 Mediabunny）与 `fmp4-muxer.js`（自研）、`hls-muxer.js`（自研） | Mediabunny 的版权头是 `2025-present`，**推断**是较新的引入；自研 muxer 是更早的实现，因兼容性/性能原因被保留 |
| 三套录制路径并存 | `bufferrecorder` 页面同时有 `MseController` / `MsrController` 两个 controller 类，`MODULE_PATH` 里同时挂着 `MP4MERGER_WORKER` 与 `MSR_WORKER` | `popup_record_mode_*` 文案里说 MSE「兼容性较差」，MSR 是「建议直播和MSE无法录制的视频使用此方式」——**推断 MSR 是对 MSE 失败场景的补丁**，不是替代 |
| `options.js` 的 `threads` 默认值 | `modules/options.js`：`items = { threads: 2, preview: false, autoSave: false, clearCache: true, filenameType: "title", tabProgress: true, defaultResolution: null, segmentThreshold: 0 }` | 用户可调线程数，默认 2；而 hls-loader 里初始化会写 `3` |
| `minimum_chrome_version: 92` | manifest | 与「用 `declarativeNetRequest` 的 `requestDomains`」这个 Chrome 101+ 特性配套的是**运行时特性探测**，不是直接抬版本号：`isRequestDomainsSupport()` 里 `return parseInt(...) >= 101` |

```js
// popup.js —— 运行时探测 requestDomains 支持，不支持就用 regexFilter 退化
isRequestDomainsSupport() {
  try {
    const e = navigator.userAgent.match(/Chrome\/(\d+)/);
    if (e && e[1]) { return parseInt(e[1], 10) >= 101 }
    return !1
  } catch (e) { return !1 }
}
```

### 11.2 站点侧的产品线分裂

`/static/downloader.js` 里同一份代码同时指向 Chrome 和 Edge 两个商店 ID，且 `/extensions/dist/` 下的模块被三条不同的 loader（`hls-loader` / `mp4-loader` / `rec-loader`）共享——**推断**这是「一个构建产物，多商店 + 多页面复用」。

---

## 12. 与「CDP 嗅探 + ffmpeg」方案的对比

提问者现有方案：**启动真 Chrome → CDP 连接 → 页面内 `performance.getEntriesByType('resource')` 嗅探 `douyinvod.com` 流地址 → `urllib` 下载 → 本机 `ffmpeg` 合并音视频**。

### 12.1 逐条对比

| 维度 | 提问者（CDP + ffmpeg） | FetchV | 谁更好 / 可借鉴点 |
| --- | --- | --- | --- |
| **媒体发现时机** | 下载器**启动并连上 CDP 之后**才开始收集；页面在此之前发出的请求（包括 `master.m3u8`）**永久丢失** | content script 在 `document_start`（页面任何脚本执行前）注入；`webRequest` 从扩展安装起就常驻监听 | **FetchV 完胜**。这也是官方文档那句「有些视频如果不播放可能无法被捕获」的反面——它至少能拿到刷新后的全部请求。提问者若无法改时序，**至少要保证「先连 CDP + 开嗅探，再导航/刷新」**，否则首个 m3u8 必然漏 |
| **发现的判据** | 只有 URL 字符串（`resource` 表项里没有响应头） | `Content-Type` + `Content-Length` / `Content-Range` + `Content-Disposition` + URL 后缀的**交叉映射**，还有三层兜底（`CHECK_VIDEO_SRC` / `CHECK_TEXT_CONTENT` / `#EXTM3U` 内容嗅探） | **FetchV 完胜**。`Content-Range` 这一个头就是它识别分片的钥匙；提问者拿不到头，只能猜 URL 模式 |
| **blob / MSE 流** | **完全拿不到**（`blob:` URL 不在 Resource Timing 里，且无网络请求可供 urllib 下载） | `hook.js` 劫持 `MediaSource` + `SourceBuffer.appendBuffer`，逐分片 blob 化后经 `BroadcastChannel` 逃出页面；`injection.js` 再用 `video.captureStream()` + WebCodecs 重编码兜底 | **FetchV 完胜**，这是它的核心壁垒。提问者若遇到「页面用 MSE 但服务端没有可直接下载的 mp4」的视频，现有方案无解——**但注意**：抖音是标准 DASH，服务端有可直接下载的分片，所以这一条对抖音**不是必需** |
| **DASH 音视频配对** | 提问者刚踩的坑：只拿到 video 流 | 双队列 `{video:[], audio:[]}` + `sn` 排序 + `audioVideoCopy()` **按 `start/end` 时间戳裁掉超出重叠区间的尾巴**，再分别算 `duration` 交给 muxer | **这是最值得直接抄的一条**。提问者用 ffmpeg 合并时同样需要「两条流时长对齐」，`-shortest` 能糊过去但会在尾部产生静音/黑帧；FetchV 的裁剪逻辑更干净 |
| **请求头 / 防盗链** | 手拼 `Referer` + `User-Agent` | ① 嗅探时用 `onBeforeSendHeaders` + `extraHeaders` **记录真实请求头**；② 下载时原样复放（只剔除 `range/content-length/content-type/accept-encoding/accept/language`）；③ 跨域 CDN 用 **`declarativeNetRequest` session rule** 把 `Origin`/`Referer` 改回去；④ 兜底用 offscreen 文档 `credentials:"include"` | **FetchV 更稳**。提问者手拼的问题在于：抖音的 `Referer`/`Cookie`/`UA` 三者往往要**原封不动**，手拼容易漏（尤其 `Cookie` 里的 `ttwid`/`msToken`）。**可借鉴**：用 CDP 的 `Network.requestWillBeSentExtraInfo` / `Network.requestWillBeSent` 事件把真实请求头整份记下来再复放，比手拼可靠 |
| **分片并发** | 串行（`urllib` 顺序下载）或自己写线程池 | 自建调度：`threads` 是用户可调的整数并发度，`singleThread` 开关会把并发度压成 `1`；官方宣传「比浏览器默认下载速度数倍甚至数十倍」 | **FetchV 更好**，但对抖音不是瓶颈（分片通常几十到几百个）。**可借鉴**：并发数要可调 + 要有单分片超时（FetchV 是 25 s）+ 失败分片单独重试列表（`errorFrags` / `error-frags-row` / `errorRetry`） |
| **内存占用** | 直接落盘，内存占用极低（可能只在合并阶段吃盘 I/O） | 两条路：小文件全内存 Blob；**> 2 GiB 走 StreamSaver，由 Service Worker 边收边写盘**（`size > 2147483648` 阈值） | **提问者更优**。浏览器内做 mux 必须把数据搬进 JS 堆，FetchV 用 StreamSaver 只是缓解了「最后写盘那一下」。提问者用本机 ffmpeg 合并是**磁盘到磁盘**，内存几乎零压力 |
| **合并 / 转封装** | 本机 ffmpeg（原生、多线程、格式通吃） | 三套并行实现：自研 `HLSMuxer`（TS→MP4）、自研 `FMP4Muxer`、Mediabunny；**兜底才是 ffmpeg.wasm（单线程）** | **提问者在本机 ffmpeg 这一条上完胜**。ffmpeg.wasm ST 版既慢又吃内存，FetchV 自己也只在 codec 不兼容时才用（代码里 `FFMPEG timeout` 50 秒超时、失败就返回 null）。提问者不该放弃本机 ffmpeg |
| **AES-128 加密流** | 需要自己解析 `EXT-X-KEY`、自己 GET key、自己解密（ffmpeg 也能吃 `-c copy` + key，但要正确传参） | hls.js 的 `decryptdataLoader` 拿 key/IV → 自己的 Worker 用纯 JS AES-CBC 解密（`Uint32Array(key)` 写死 16 字节） | **打平**。提问者可以直接用 `ffmpeg -allowed_extensions ALL -i playlist.m3u8 -c copy` 让 ffmpeg 自己处理，更省事 |
| **DRM** | 碰不了 | 碰不了，且明确写了不支持 | 打平 |
| **落盘路径** | Python 写文件 | Blob + `<a download>` / StreamSaver SW | 提问者更直接 |
| **适用边界** | **特定站点批量下载**：可以用站点的私有 API 拿到更干净的数据（例如抖音的 `aweme/v1/web/aweme/detail` 接口直接给无水印地址），不必走嗅探 | **通用网页视频**：任何能用 m3u8/HTML5 `<video>` 播放的页面，零站点适配 | 两者是不同物种。**提问者不该全面倒向 FetchV 的架构**——抖音有官方 API 可走，比嗅探稳得多 |
| **工程质量可借鉴处** | — | ① 哨兵头 `X-Original-Request-Id` 防回环；② `Content-Range` 优先于 `Content-Length` 算体积；③ 每标签页最多 30 条 + URL 去重；④ 域级屏蔽（`OPTION.domain`，上限 30）；⑤ 大小上下限过滤（默认 ≥ 500 KB）；⑥ 清单/域名屏蔽存在 `chrome.storage.sync`，任务队列存在 `chrome.storage.local`；⑦ tab 关闭/刷新时清理 `storage${tabId}` 与残留 DNR 规则 | 都是低成本高收益的细节 |

### 12.2 给提问者的 3–5 条最值得借鉴的做法

1. **「先记头，再复放」而不是「手拼头」。** 用 CDP 的 `Network.requestWillBeSentExtraInfo`（它带 `Cookie` 和真实 `Referer`）把请求头整份存下来，下载分片时原样带上，只剔除 `range` / `content-length` / `accept-encoding` / `accept` / `accept-language`。FetchV 的剔除清单可以直接抄（见 §3.5 的 `l` 数组）。这比手拼 `Referer`+`UA` 稳，尤其是 Cookie 里带签名的场景。

2. **DASH 双流合并时按时间轴裁剪，而不是只靠 `-shortest`。** 把 video / audio 两条流各自解析出 `(start, end, duration, sn)`，按序号排序后**互相裁掉超出重叠区间的尾部**，再喂给 ffmpeg。FetchV 的 `audioVideoCopy()` 只有 8 行，可以直接移植成 Python。这能从根上避免「音视频时长差几十毫秒导致尾部黑帧/静音」。

3. **给自发的请求打哨兵头，嗅探端见到就跳过。** FetchV 的 `X-Original-Request-Id` 是个两行成本的工程习惯。提问者如果之后加了「自己再发一次请求去探测」的逻辑，同样需要一个防回环标记（否则自己的请求会被自己的嗅探器收进列表）。

4. **失败分片要有独立的重试列表和单分片超时，而不是整体重跑。** FetchV 有 `errorFrags` / `error-frags-row` / `errorRetry` / `errorRetryCancel` 一整套 UI，以及 `fragLoadingTimeOut = 25000`。抖音分片数量多，个别分片 403/超时是常态，整体重跑代价太高。

5. **不要把「本机 ffmpeg」换成「浏览器内 wasm」。** FetchV 之所以用 JS muxer + ffmpeg.wasm，是因为它**没有任何本地进程**（manifest 里连 `nativeMessaging` 都没申请）。提问者本来就有本机 ffmpeg，这是**结构性优势**，应当保留；需要补的是「请求头复放」和「双流时间轴对齐」这两块，而不是搬家到浏览器里。

---

## 13. 未能验证的部分

诚实清单，按重要性排序：

1. **站点侧混淆代码的控制流语义（最大的缺口）。** 三份 loader（`hls-loader.js` 270 956 B、`mp4-loader.js` 114 319 B、`rec-loader.js` 170 289 B）与两份 muxer（`hls-muxer.js` 38 809 B、`fmp4-muxer.js` 42 501 B）是 `javascript-obfuscator` 的**控制流平坦化 + 字符串数组 + 死代码注入**产物。我恢复了字符串常量表（hls-loader `2899/3115`、rec-loader `1768/1907`、mp4-loader `814/1297`、hls-muxer `282/409`、fmp4-muxer `370/488`），但**控制流没有还原**，所以：
   - **分片下载的调度循环没还原**：`threads` 是并发度（已确证，见 §4.2），但它是「滚动窗口」「固定分块」还是「按空闲槽位补位」——**未验证**。我在 hls-loader 里找不到 `freeThreads` / `lock` / `interval` 这类标识符（它们属于 `mp4-loader`），所以之前想用它们证明 HLS 并发模型是不成立的，已在 §4.2 更正。
   - `0xc`（12）与 `0x3`（3）这两个数值常量的语义——**未知**。它们和 `fragLoadingTimeOut` 写在同一个初始化分支里，但我没有找到读取它们的消费点。
   - 分片下载究竟走 `fetch` 直连还是 `bgFetcher`（offscreen 文档）——**两种情况代码里都有调用点，我没有确定选择条件**。
   - `hls-muxer.js`（TS→MP4）与 `fmp4-muxer.js` 的内部算法——只确证了它们是**自研的 ISO BMFF 复用器**（可见 `movieTimescale` / `outputSamples` / `endDTS` / `tfhd` / `trun` / `traf` / `moof` / `mdat` / `baseMediaDecodeTime` 等自有与标准标识符），**没有逐行验证其正确性或与 ffmpeg 的差异**。
2. **`ffmpeg-core.v2.wasm` 的 ffmpeg 版本号没能确定。** 我解压了 wasm（562 601 B zlib → 1 166 201 B），检索 `ffmpeg version` 为 0 命中，`libavcodec` 命中 11 处但都是符号名而非版本串。所以**我能证明它是 `--disable-pthreads -msimd128` 的单线程构建，但说不出它对应 ffmpeg 的哪个版本**（`Last-Modified: 2024-08-20` 只能给出上界）。
3. **站点侧 `ffmpeg-core.js`（114 673 B）与 `ffmpeg-core.v2.js`（87 071 B）两份 core 的关系没查。** `index.js` 只引用 `ffmpeg-core.v2.js` + `ffmpeg-core.v2.wasm`；旧的那份 `ffmpeg-core.js` 是谁在用，**未验证**（可能是历史遗留文件）。
4. **版本演进史。** 我没有拿到任何权威的版本变更日志：`manifest.json` 无 `version_history`；fetchv.net 的 `/blog` 只有 4 篇文章（最新 2024-02-02）；`/sitemap.xml`、`/sitemap_index.xml` 均 404；`/faq`、`/download` 返回的是同一个 5 447 字节的 404 页面。**§11 里除「事实」小节的代码证据外，所有演进方向的描述都是推断。**
5. **Chrome Web Store / Edge Add-ons 详情页原文。** 本环境的 DNS 把 `chromewebstore.google.com`、`microsoftedge.microsoft.com` 解析到非公网地址，`web_fetch` 拒绝访问；`web_search` 能返回商店 URL 但拿不到页面正文。**权限清单我改用本地 `manifest.json` 作为权威来源**（这比商店页更可靠），但商店页的「版本历史」「用户数」「更新说明」我**没有拿到**。
6. **真实 Widevine 站点上的实测行为。** §6.2 里「FetchV 不做 DRM」的结论由三条代码事实支撑（无 `crypto.subtle`、无 `encrypted` 监听、`requestMediaKeySystemAccess` 只在 hls.js 库内），但**「受保护分片不会产生可嗅探的明文请求」这一步是基于 EME 工作原理的推断**，我没有在真实 Widevine 站点上跑过 FetchV 观察它到底显示什么。
7. **`_locales/en/messages.json` 之外的语言包是否有一致的功能描述。** 我只精读了 `zh_CN` 与抽查了 `en`；其他 40 个语言包未逐一比对。
8. **`hls.es.js`（407 280 字节）与 `js/hls-player.js`（506 251 字节）的具体版本号。** 两者都是 hls.js 的发行版打包（`hls-player.js` 里 `hls.js` 标识符命中 5 次，`Hls.version` 与 `version:"x.y.z"` 正则均 0 命中），所以我**无法给出确切版本号**。
9. **扩展文件的哈希完整性未实算。** 目录里有 `_metadata/verified_contents.json`（Chrome 商店签名的 tree-hash 清单）与 `_metadata/computed_hashes.json`（本地分块哈希，block_size 4096），我只做了结构确认，**没有实现 Chrome 的 tree-hash 算法去逐文件比对**。所以我读到的文件「应当」与商店签名版本一致，但这一点未经计算验证。
10. **用户数据/隐私面。** 站点页里有 Google AdSense（`ca-pub-1805776847890085`）与 GA4（`G-HRM4KE0V0H`，见页面 `<script>` 标签），意味着打开下载页会向 Google 发请求；我没有审阅 `/privacy` 页面内容，也不对开发者的数据处理做任何结论。

---

## 附录 A：反混淆方法与可复现性

因为站点侧代码是混淆的，我把反混淆过程也当作一手证据记录下来，脚本与中间产物都留在磁盘上。

**临时目录**：`C:\Users\29580\Documents\deepseek-harness\default-workspace\research\.fetchv-tmp\`

**步骤**：

1. **确认本地扩展**（无需下载 CRX）：读取 `%LOCALAPPDATA%\Google\Chrome\User Data\Default\Extensions\nfmmmhanepmpifddlkkmihkalkoekpfd\3.2_0`（61 个文件，约 1.48 MB，**未混淆**），整目录复制到 `.fetchv-tmp\src\`。
2. **拉取站点侧代码**：`https://fetchv.net/{m3u8downloader,videodownloader,bufferrecorder}` 三个页面各有独立的 loader；再加 `/extensions/dist/modules/**` 下 20 个模块。清单如下（均为 HTTP 200）：

```
/extensions/dist/hls-loader.js            270956
/extensions/dist/mp4-loader.js            114319
/extensions/dist/rec-loader.js            170289
/extensions/dist/modules/options.js          592
/extensions/dist/modules/saveAs.js           894
/extensions/dist/modules/iso-boxer.js      23494
/extensions/dist/modules/hls.es.js        407280
/extensions/dist/modules/hls-muxer.js      38809
/extensions/dist/modules/fmp4-muxer.js     42501
/extensions/dist/modules/fmp4-muxer-worker.js  306
/extensions/dist/modules/mp4-worker.js      2185
/extensions/dist/modules/msr-worker.js      3053
/extensions/dist/modules/web-worker.js      2171
/extensions/dist/modules/hls-decrypter.js    798
/extensions/dist/modules/decrypter-worker.js 9906
/extensions/dist/modules/mediabunny.js    397355
/extensions/dist/modules/ffmpeg/index.js    1809
/extensions/dist/modules/ffmpeg/ffmpeg.js   3856
/extensions/dist/modules/ffmpeg/ffmpeg-core.js        114673
/extensions/dist/modules/ffmpeg/ffmpeg-core.v2.js      87071
/extensions/dist/modules/ffmpeg/version.v2.json           14
/extensions/dist/modules/streamSaver/index.js  3955
/extensions/dist/modules/streamSaver/mitm.html 5544
/extensions/dist/modules/streamSaver/sw.js     1754
```

3. **实测下载并检查 ffmpeg.wasm 二进制**（这是判定它是否多线程的决定性证据）：

```powershell
curl.exe -sS -L -D - -o ffmpeg-core.v2.wasm https://fetchv.net/extensions/dist/modules/ffmpeg/ffmpeg-core.v2.wasm
# → 200, Content-Type: application/wasm, Content-Length: 562601, 无 Content-Encoding
node -e "const b=require('fs').readFileSync('ffmpeg-core.v2.wasm'); console.log(b.slice(0,4)); console.log(require('zlib').inflateSync(b).length)"
# → <Buffer 78 9c d4 bd>  (zlib 流头)
# → 1166201              (解压后 1 166 201 字节，魔数 00 61 73 6d)
```

   然后在解压后的 wasm 里检索 `SharedArrayBuffer` / `Atomics` / `worker`（均 0 命中）与 `pthread`（3 命中，全部来自编译命令行 `--disable-pthreads`）。

4. **还原混淆字符串表**：javascript-obfuscator 的字符串数组是「`(function(){return[...]}())` 内层 IIFE + 外层旋转 IIFE + 自防御式 RC4 解码器」三段式。做法是：
   - 用括号平衡扫描取出内层数组表达式（它可能是 `[...].concat(...)` 深层嵌套，16 层）；
   - 把**整个外层数组函数**（含旋转 IIFE）导出成独立 Node 脚本执行，拿到**旋转后的最终数组**（关键坑：直接用内层数组会得到乱码，必须跑完旋转）；
   - 导出解码器函数，对**每个调用点用它自己的 salt**（第二个参数，每个调用点不同，全文件有 50 种）解码；
   - 解码器在文件里被别名为 138–279 个不同的局部变量名，需要一个不动点迭代才能把别名全部收集齐；
   - 最后把所有 `别名(0xNNN,'salt')` 替换成字符串字面量。

   还原率（已还原字符串数 / 字符串数组长度）：hls-loader `2899/3115`、mp4-loader `814/1297`、rec-loader `1768/1907`、hls-muxer `282/409`、fmp4-muxer `370/488`。**没还原的是控制流（javascript-obfuscator 的控制流平坦化），不是字符串本身**——所以引用的字符串常量都可信，但由它们构成的执行顺序需要人工推断，这也是 §13.1 那些「未验证」项的来源。

5. **结构化阅读**：对 `service-worker.js`、`injection.js`、`popup.js` 做了「字符串安全的分号换行」美化（不改变语义，只在字符串字面量之外断行），得到 94 / 115 / 179 行可逐行引用的版本。

**复现脚本**（均在 `.fetchv-tmp\` 下）：

```
deob5.js          最终版反混淆器（数组还原 + 别名收集 + 全量重写）
strings.js        从 JS 中提取可读字符串字面量（支持正则过滤）
paths.js          枚举字符串表中形如路径/模块名的条目
```

**证据留存**：`.fetchv-tmp\src\`（扩展本体副本）、`.fetchv-tmp\site\`（fetchv.net 页面 + JS + 模块原文）、`.fetchv-tmp\site\js\*.deob.js`（反混淆产物）、`.fetchv-tmp\site\js\*.strings.json`（字符串表）、`.fetchv-tmp\beauty-*.js`（美化后的可读版本）。

**完整性校验**：扩展目录里的 `_metadata/verified_contents.json` 是 Chrome 商店签名过的文件树哈希（payload 为 base64 的 JSON，含每个文件的 `root_hash`），`_metadata/computed_hashes.json` 是本地计算的分块哈希（block_size 4096）。我只做了**存在性与结构确认**，**没有逐文件比对哈希**（比对需要实现 Chrome 的 tree-hash 算法，本次未做）。这意味着：**我读到的文件与商店签名的版本应当一致，但这一点我没有通过计算验证。**

---

## 参考来源

**扩展本体（本地已安装，一手代码）**
- 扩展根目录：`C:\Users\29580\AppData\Local\Google\Chrome\User Data\Default\Extensions\nfmmmhanepmpifddlkkmihkalkoekpfd\3.2_0\`
  - [`manifest.json`](file:///C:/Users/29580/AppData/Local/Google/Chrome/User%20Data/Default/Extensions/nfmmmhanepmpifddlkkmihkalkoekpfd/3.2_0/manifest.json)
  - [`service-worker.js`](file:///C:/Users/29580/AppData/Local/Google/Chrome/User%20Data/Default/Extensions/nfmmmhanepmpifddlkkmihkalkoekpfd/3.2_0/service-worker.js)
  - [`js/injection.js`](file:///C:/Users/29580/AppData/Local/Google/Chrome/User%20Data/Default/Extensions/nfmmmhanepmpifddlkkmihkalkoekpfd/3.2_0/js/injection.js) · [`js/hook.js`](file:///C:/Users/29580/AppData/Local/Google/Chrome/User%20Data/Default/Extensions/nfmmmhanepmpifddlkkmihkalkoekpfd/3.2_0/js/hook.js) · [`js/offscreen.js`](file:///C:/Users/29580/AppData/Local/Google/Chrome/User%20Data/Default/Extensions/nfmmmhanepmpifddlkkmihkalkoekpfd/3.2_0/js/offscreen.js) · [`js/content.js`](file:///C:/Users/29580/AppData/Local/Google/Chrome/User%20Data/Default/Extensions/nfmmmhanepmpifddlkkmihkalkoekpfd/3.2_0/js/content.js) · [`js/router.js`](file:///C:/Users/29580/AppData/Local/Google/Chrome/User%20Data/Default/Extensions/nfmmmhanepmpifddlkkmihkalkoekpfd/3.2_0/js/router.js) · [`js/options.js`](file:///C:/Users/29580/AppData/Local/Google/Chrome/User%20Data/Default/Extensions/nfmmmhanepmpifddlkkmihkalkoekpfd/3.2_0/js/options.js) · [`js/popup.js`](file:///C:/Users/29580/AppData/Local/Google/Chrome/User%20Data/Default/Extensions/nfmmmhanepmpifddlkkmihkalkoekpfd/3.2_0/js/popup.js) · [`js/hls-player.js`](file:///C:/Users/29580/AppData/Local/Google/Chrome/User%20Data/Default/Extensions/nfmmmhanepmpifddlkkmihkalkoekpfd/3.2_0/js/hls-player.js) · [`js/mediabunny.js`](file:///C:/Users/29580/AppData/Local/Google/Chrome/User%20Data/Default/Extensions/nfmmmhanepmpifddlkkmihkalkoekpfd/3.2_0/js/mediabunny.js)
  - [`_locales/zh_CN/messages.json`](file:///C:/Users/29580/AppData/Local/Google/Chrome/User%20Data/Default/Extensions/nfmmmhanepmpifddlkkmihkalkoekpfd/3.2_0/_locales/zh_CN/messages.json) · [`_metadata/verified_contents.json`](file:///C:/Users/29580/AppData/Local/Google/Chrome/User%20Data/Default/Extensions/nfmmmhanepmpifddlkkmihkalkoekpfd/3.2_0/_metadata/verified_contents.json)

**fetchv.net 站点代码（一手代码，已反混淆）**
- 下载页：[`/m3u8downloader`](https://fetchv.net/m3u8downloader) · [`/videodownloader`](https://fetchv.net/videodownloader) · [`/bufferrecorder`](https://fetchv.net/bufferrecorder)
- 三个 loader：[hls-loader.js](https://fetchv.net/extensions/dist/hls-loader.js) · [mp4-loader.js](https://fetchv.net/extensions/dist/mp4-loader.js) · [rec-loader.js](https://fetchv.net/extensions/dist/rec-loader.js)
- 关键模块：[web-worker.js](https://fetchv.net/extensions/dist/modules/web-worker.js) · [hls-decrypter.js](https://fetchv.net/extensions/dist/modules/hls-decrypter.js) · [decrypter-worker.js](https://fetchv.net/extensions/dist/modules/decrypter-worker.js) · [hls-muxer.js](https://fetchv.net/extensions/dist/modules/hls-muxer.js) · [fmp4-muxer.js](https://fetchv.net/extensions/dist/modules/fmp4-muxer.js) · [mp4-worker.js](https://fetchv.net/extensions/dist/modules/mp4-worker.js) · [msr-worker.js](https://fetchv.net/extensions/dist/modules/msr-worker.js) · [saveAs.js](https://fetchv.net/extensions/dist/modules/saveAs.js) · [options.js](https://fetchv.net/extensions/dist/modules/options.js) · [ffmpeg/index.js](https://fetchv.net/extensions/dist/modules/ffmpeg/index.js) · [ffmpeg/ffmpeg.js](https://fetchv.net/extensions/dist/modules/ffmpeg/ffmpeg.js) · [streamSaver/mitm.html](https://fetchv.net/extensions/dist/modules/streamSaver/mitm.html)
- 页面辅助脚本：[`/static/downloader.js`](https://fetchv.net/static/downloader.js)
- ffmpeg.wasm 二进制（已下载实测）：[ffmpeg-core.v2.wasm](https://fetchv.net/extensions/dist/modules/ffmpeg/ffmpeg-core.v2.wasm) · [ffmpeg-core.v2.js](https://fetchv.net/extensions/dist/modules/ffmpeg/ffmpeg-core.v2.js) · [version.v2.json](https://fetchv.net/extensions/dist/modules/ffmpeg/version.v2.json)

**官方网站文档**
- [FetchV 首页（功能自述与使用说明）](https://fetchv.net/)
- [How to Download m3u8 Videos](https://fetchv.net/blog/how-to-download-m3u8-videos)
- [What to Do When FetchV Download Fails（录制模式说明）](https://fetchv.net/blog/what-to-do-when-downloads-fails)
- [Why FetchV Not Support Youtube（DRM 立场）](https://fetchv.net/blog/not-support-youtube)

**商店页面（仅作 ID 与命名交叉验证；详情页正文未取得，原因见 §13 第 5 条）**
- [Chrome Web Store: FetchV - Video Downloader for m3u8 & hls](https://chromewebstore.google.com/detail/fetchv-video-downloader-f/nfmmmhanepmpifddlkkmihkalkoekpfd)
- [Edge Add-ons: FetchV - m3u8/hls Video Downloader](https://microsoftedge.microsoft.com/addons/detail/dbepbhhcmhodojepbagfppgpieeplpik)

**第三方依赖（版本信息来自代码内的版权头，非本次实测）**
- [mediabunny（Vanilagy，MPL-2.0）](https://github.com/Vanilagy/mediabunny) —— 版权头 `Copyright (c) 2025-present, Vanilagy and contributors`
- [StreamSaver.js](https://github.com/jimmywarting/StreamSaver.js) —— `mitm.html` 头部注释与 API 形态可确认
- aes-decrypter（hls.js 生态）—— `decrypter-worker.js` 内嵌的 UMD 打包
- MP4Box.js 的 ISOBoxer —— `modules/iso-boxer.js`
- ffmpeg.wasm —— `modules/ffmpeg/ffmpeg.js` 的消息协议枚举与 `@ffmpeg/ffmpeg` 上游一致
