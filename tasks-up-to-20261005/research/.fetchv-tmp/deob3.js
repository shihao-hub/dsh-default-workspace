// Full deobfuscation of a fetchv.net loader bundle.
//   argv[2] = input .js   argv[3] = output prefix (optional)
// Produces <prefix>.strings.json (decoded string table) and <prefix>.deob.js
// (every decoder call replaced by its literal string).
const fs = require('fs');
const vm = require('vm');

function balanceSlice(src, from, open, close) {
  let depth = 0, inStr = null, esc = false;
  for (let k = from; k < src.length; k++) {
    const c = src[k];
    if (inStr) {
      if (esc) { esc = false; continue; }
      if (c === '\\') { esc = true; continue; }
      if (c === inStr) inStr = null;
      continue;
    }
    if (c === "'" || c === '"' || c === '`') { inStr = c; continue; }
    if (c === open) depth++;
    else if (c === close) { depth--; if (depth === 0) return src.slice(from, k + 1); }
  }
  return null;
}

function extractArrayExpr(src, retIdx) {
  let text = '';
  let cursor = retIdx;
  for (;;) {
    const arr = balanceSlice(src, cursor, '[', ']');
    if (arr === null) return null;
    text += arr;
    let after = cursor + arr.length;          // index just past the ']'
    if (src.startsWith('.concat(', after)) {
      const call = balanceSlice(src, after + 7, '(', ')');
      if (call === null) return null;
      text += '.concat' + call;
      cursor = after + 7 + call.length;       // now just past the concat's ')'
      if (src.startsWith('.concat(', cursor)) continue;
      return { expr: text, end: cursor };
    }
    return { expr: text, end: after };
  }
}

function extractFn(src, start) {
  const open = src.indexOf('{', start);
  let depth = 0;
  for (let k = open; k < src.length; k++) {
    if (src[k] === '{') depth++;
    else if (src[k] === '}') { depth--; if (depth === 0) return src.slice(start, k + 1); }
  }
  return null;
}

const file = process.argv[2];
const outPrefix = process.argv[3] || file.replace(/\.js$/, '');
const src = fs.readFileSync(file, 'utf8');

// ---- 1. string array ----
const retIdx = src.indexOf('return[', src.indexOf('(function(){'));
const got = extractArrayExpr(src, retIdx + 'return'.length);
if (!got) { console.error('FATAL: array extraction failed'); process.exit(1); }
const ctx = {};
vm.createContext(ctx);
const tagM = src.match(/var\s+(_0xod[A-Za-z0-9]+)\s*=\s*'([^']*)'/);
if (tagM) vm.runInContext('var ' + tagM[1] + ' = ' + JSON.stringify(tagM[2]) + ';', ctx);
let arr;
try {
  arr = vm.runInContext('(' + got.expr + ')', ctx);
} catch (e) {
  console.error('array eval failed: ' + e.message);
  console.error('expr head=' + JSON.stringify(got.expr.slice(0, 50)));
  console.error('expr tail=' + JSON.stringify(got.expr.slice(-40)));
  // locate the offending spot
  try { new Function('return (' + got.expr + ')'); } catch (e2) { console.error('new Function says: ' + e2.message); }
  process.exit(1);
}
if (!Array.isArray(arr)) { console.error('not an array: ' + typeof arr); process.exit(1); }
console.error('array length = ' + arr.length);

// ---- 2. decoder ----
const fnRe = /function (_0x[0-9a-f]+)\((_0x[0-9a-f]+),(_0x[0-9a-f]+)\)\{/g;
let m, dec = null;
while ((m = fnRe.exec(src)) !== null) {
  if (src.slice(m.index, m.index + 6000).includes('fromCharCode')) { dec = { name: m[1], idx: m.index }; break; }
}
if (!dec) { console.error('FATAL: decoder not found'); process.exit(1); }
const decSrc = extractFn(src, dec.idx);
const c2 = { __arr: arr };
vm.createContext(c2);
const arrFn = (decSrc.match(/=\s*(_0x[0-9a-f]+)\(\)/) || [])[1];
vm.runInContext('function ' + arrFn + '(){ return __arr; }', c2);
vm.runInContext(decSrc + '\nthis.__dec = ' + dec.name + ';', c2);
console.error('decoder = ' + dec.name + ', arrFn = ' + arrFn);
const sanity = c2.__dec(0x53f, ')&)5');
console.error('sanity dec(0x53f, \')&)5\') = ' + JSON.stringify(sanity));

// ---- 3. dump table: decode every call site found in the source, with its own salt ----
const map = {};
const scanRe = new RegExp(dec.name + "\\((0x[0-9a-fA-F]+)\\s*,\\s*'((?:[^'\\\\]|\\\\.)*)'\\)", 'g');
let sm;
while ((sm = scanRe.exec(src)) !== null) {
  const k = parseInt(sm[1], 16);
  if (map[k] !== undefined) continue;
  try {
    const v = c2.__dec(k, sm[2]);
    if (typeof v === 'string' && v.length && !/^_0x[0-9a-f]+$/.test(v)) map[k] = v;
  } catch (e) { /* ignore */ }
}
// also sweep the whole index space with the most common salt as a fallback
const salts = {};
for (const k in map) { /* noop */ }
console.error('decoded strings = ' + Object.keys(map).length);
fs.writeFileSync(outPrefix + '.strings.json', JSON.stringify(map, null, 1));

// ---- 4. rewrite call sites ----
let hits = 0, misses = 0;
const callRe = new RegExp(dec.name + "\\((0x[0-9a-fA-F]+)\\s*,\\s*'((?:[^'\\\\]|\\\\.)*)'\\)", 'g');
const out = src.replace(callRe, (full, hex, salt) => {
  const k = parseInt(hex, 16);
  if (map[k] !== undefined) { hits++; return JSON.stringify(map[k]); }
  try { const v = c2.__dec(k, salt); if (typeof v === 'string') { hits++; return JSON.stringify(v); } } catch (e) {}
  misses++;
  return full;
});
console.error('rewritten = ' + hits + ', misses = ' + misses);
fs.writeFileSync(outPrefix + '.deob.js', out);
console.log('OK strings=' + Object.keys(map).length + ' rewrites=' + hits + ' misses=' + misses);
