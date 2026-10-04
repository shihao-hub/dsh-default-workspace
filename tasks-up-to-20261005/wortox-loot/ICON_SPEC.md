# 掉落物手绘 SVG 图标规范

用于「小恶魔（沃托克斯）· 月族偷窃掉落一览」图鉴页面。总体气质：**铅笔淡彩手绘本**，不是扁平 UI 图标、不是 emoji、不是 3D 拟物。

## 硬性规则

1. `<svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" data-icon="唯一英文名">`
   - 禁止 `width` / `height` 属性（由外层 CSS 控制尺寸）。
   - 每个图标必须有唯一的 `data-icon`（小写英文 + 连字符）。
2. **禁用**：`<defs>`、渐变、滤镜、阴影、`<text>`、位图、外部引用、`stroke-dasharray` 花边。
3. 色彩只能用下面这 9 个十六进制值，不得自创：
   - `#B8873F` 墨线棕（主要轮廓色）
   - `#7A5C2E` 深墨棕（轮廓加重、细节线）
   - `#E3B341` 蜜黄 ｜ `#C0862B` 木褐 ｜ `#8FA35A` 叶绿
   - `#4E8C6A` 深松绿 ｜ `#B5503F` 砖红 ｜ `#4A7BA7` 靛蓝 ｜ `#8A6BA8` 紫藤
4. 轮廓统一 `stroke="#B8873F" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"`；
   内部细节线用 `stroke="#7A5C2E" stroke-width="1.2"` 或 `1.5`，同样要 round cap/join。
5. 填充：形状用对应色相，`fill-opacity` 取 0.75–0.95，**不要纯平涂到 1.0**。
   高光/亮面用 `#E3B341` 的低透明度小形状叠一层即可。
6. 每个图标 **2–6 个形状元素**，最多 8 个。宁可简，不要细密。
7. **手绘感靠坐标微抖**：对称图形的左右两侧不要完全镜像；直线改成略带弧度的 `C` / `Q` 曲线；
   椭圆用两段 `C` 拼，收笔不要完全闭合（留 1–2 单位缺口）。
   抖动幅度控制在 1–1.6 单位，别夸张成涂鸦。
8. 构图：主体占 48×48 画布的约 30×34，四边各留 6–9 留白，视觉重心略偏下。
9. **单个图标自洽即可**，不需要跟其它图标对齐网格——但风格必须一致（同样的线宽、同样的抖动手感）。
10. 只输出 SVG 代码，不要 `<html>`，不要注释，不要额外解释性文字。

## 样板（照这个手感画）

```html
<!-- 尖刺：锥形 + 中线 -->
<svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" data-icon="stinger">
  <path d="M24.6 7.5C27 14 28.6 20.6 29.4 27.2c.5 3.9 3.1 6.8 7.2 8.4-4.3 3.2-8.6 4.6-13 4.3-3.8-.2-6.6-1.6-8.7-3.9 4.4-1.7 6.9-4.6 7.6-8.7.9-6.6 2.2-13.2 2.1-19.8z" fill="#C0862B" fill-opacity=".82" stroke="#B8873F" stroke-width="2" stroke-linejoin="round"/>
  <path d="M25.3 12.4c.8 6.4 1.9 12.8 3 19" fill="none" stroke="#7A5C2E" stroke-width="1.2" stroke-linecap="round"/>
</svg>

<!-- 松果：鳞片用叠着的小圆弧暗示 -->
<svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" data-icon="pinecone">
  <path d="M24.3 8.2c4.6 2.4 7.5 6.6 8.7 11.6 1.4 6 1.1 12.4-1.6 17.4-1.9 3.6-5.2 4.9-8.4 3.9-3.9-1.2-6.6-4.6-7.8-9.1-1.6-6.2-1.2-12.6 1.4-17.7 1.7-3.2 4.2-5.2 7.7-6.1z" fill="#C0862B" fill-opacity=".85" stroke="#B8873F" stroke-width="2" stroke-linejoin="round"/>
  <path d="M17.1 22.6c4.3 1.8 9.4 1.9 13.9.2M16.6 29.4c4.8 1.9 10.3 1.9 15.1-.2M19.4 36c3.4 1.4 7.3 1.4 10.6 0" fill="none" stroke="#7A5C2E" stroke-width="1.2" stroke-linecap="round"/>
</svg>

<!-- 绿宝石：切面宝石，左侧亮面 + 顶部一点高光 -->
<svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" data-icon="gem-green">
  <path d="M24 7.6 38.4 19.4 24 40.6 9.7 19.3z" fill="#4E8C6A" fill-opacity=".88" stroke="#B8873F" stroke-width="2" stroke-linejoin="round"/>
  <path d="M9.9 19.6h28.2M24.4 8.2l5.8 11.3-6.1 20.5" fill="none" stroke="#7A5C2E" stroke-width="1.2" stroke-linecap="round"/>
  <path d="M17.4 13.2l3.2 5.5-4.1 8.3" fill="none" stroke="#E3B341" stroke-width="1.3" stroke-linecap="round" opacity=".75"/>
</svg>

<!-- 玻璃刀：刀身透明感靠留白 + 侧边高光线 -->
<svg viewBox="0 0 48 48" xmlns="http://www.w3.org/2000/svg" data-icon="glass-blade">
  <path d="M25.2 6.4c5.9 3.4 9.4 8.2 10.6 14.4-1.9 1.1-3.3 2.6-4.3 4.6-3.6-1.6-6.8-4.2-9.5-7.8-2.7-3.6-3.5-7.3-2.3-11.1z" fill="#4A7BA7" fill-opacity=".55" stroke="#B8873F" stroke-width="2" stroke-linejoin="round"/>
  <path d="M20.4 21.5c-1.3 4.1-1.8 8.2-1.5 12.4.2 3.6-1.2 6.2-4.3 7.9-1-3.6-1-7.3-.2-11 1.4-3.9 3.4-7 6-9.3z" fill="#B8873F" fill-opacity=".85" stroke="#B8873F" stroke-width="2" stroke-linejoin="round"/>
  <path d="M28.6 11.1c2.4 2.2 4.1 4.8 5 7.6" fill="none" stroke="#E3B341" stroke-width="1.3" stroke-linecap="round"/>
</svg>
```

## 自检清单

- [ ] 缩到 24×24 还能认出是什么
- [ ] 没有 `<defs>` / 渐变 / 文字
- [ ] 颜色全部来自那 9 个值
- [ ] 形状有轻微不对称、不完全闭合
- [ ] `data-icon` 唯一
