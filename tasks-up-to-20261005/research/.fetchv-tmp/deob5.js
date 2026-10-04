const fs = require('fs');
const vm = require('vm');
const E = (s) => JSON.stringify(s);

function extractArrayFn(src) {
  const retIdx = src.indexOf('return[', src.indexOf('(function(){'));
  const iifeStart = retIdx - '(function(){'.length;
  const fnStart = src.lastIndexOf('function', iifeStart);
  let depth = 0, fnEndIdx = -1;
  for (let k = src.indexOf('{', fnStart); k < src.length; k++) {
    if (src[k] === '{') depth++;
    else if (src[k] === '}') { depth--; if (depth === 0) { fnEndIdx = k; break; } }
  }
  const body = src.slice(fnStart, fnEndIdx + 1);
  return { name: body.match(/^function\s+(_0x[0-9a-f]+)/)[1], body };
}
function extractFn(src, start) {
  let depth = 0;
  for (let k = src.indexOf('{', start); k < src.length; k++) {
    if (src[k] === '{') depth++;
    else if (src[k] === '}') { depth--; if (depth === 0) return src.slice(start, k + 1); }
  }
  return null;
}

const file = process.argv[2];
const outPrefix = process.argv[3];
const src = fs.readFileSync(file, 'utf8');
const tag = src.match(/var\s+(_0xod[A-Za-z0-9]+)\s*=\s*'([^']*)'/);

const af = extractArrayFn(src);
const rc = { __out: null };
vm.createContext(rc);
new vm.Script('var ' + tag[1] + ' = ' + E(tag[2]) + ';\n' + af.body + '\n__out = ' + af.name + '();')
  .runInContext(rc, { timeout: 60000 });
const arr = rc.__out;

// decoder
const fnRe = /function (_0x[0-9a-f]+)\((_0x[0-9a-f]+),(_0x[0-9a-f]+)\)\{/g;
let m, dec = null;
while ((m = fnRe.exec(src)) !== null) {
  if (src.slice(m.index, m.index + 6000).includes('fromCharCode')) { dec = { name: m[1], idx: m.index }; break; }
}
const decSrc = extractFn(src, dec.idx);
const dc = { __arr: arr };
vm.createContext(dc);
vm.runInContext('function ' + af.name + '(){ return __arr; }', dc);
vm.runInContext(decSrc + '\n__dec = ' + dec.name + ';', dc);

// collect all call-site salts
const aliases = new Set([dec.name]);
for (let pass = 0; pass < 5; pass++) {
  for (const a of [...aliases]) {
    const r = new RegExp('([A-Za-z_$][\\w$]*)\\s*=\\s*' + a.replace(/\$/g, '\\$') + '\\b', 'g');
    let mm; while ((mm = r.exec(src)) !== null) aliases.add(mm[1]);
  }
}
const saltCount = {};
const reList = [...aliases].map(a => new RegExp(
  a.replace(/\$/g, '\\$') + "\\((0x[0-9a-fA-F]+)\\s*,\\s*'((?:[^'\\\\]|\\\\.)*)'\\)", 'g'));
for (const re of reList) {
  let mm;
  while ((mm = re.exec(src)) !== null) saltCount[mm[2]] = (saltCount[mm[2]] || 0) + 1;
}
const salts = Object.keys(saltCount).sort((a, b) => saltCount[b] - saltCount[a]);
console.error('distinct salts = ' + salts.length + ', top = ' + salts.slice(0, 8).map(s => E(s) + ':' + saltCount[s]).join(' '));

// full table: every index x every salt (accept the first printable result)
const printable = (v) => typeof v === 'string' && v.length &&
  /^[\x09\x0a\x0d\x20-\x7e\u00a0-\uffff]*$/.test(v) && !/^_0x[0-9a-f]+$/.test(v);
const table = {};
for (const salt of salts) {
  for (let k = 0; k < arr.length; k++) {
    if (table[k] !== undefined) continue;
    try { const v = dc.__dec(k, salt); if (printable(v)) table[k] = v; } catch (e) {}
  }
}
console.error('table entries = ' + Object.keys(table).length + ' / ' + arr.length);
fs.writeFileSync(outPrefix + '.table.json', JSON.stringify(table, null, 1));

// rewrite: any alias call whose index has a table entry
let hits = 0, misses = 0;
let out = src;
for (const re of reList.map(r => new RegExp(r.source, 'g'))) {
  out = out.replace(re, (full, hex) => {
    const k = parseInt(hex, 16);
    if (table[k] !== undefined) { hits++; return E(table[k]); }
    misses++; return full;
  });
}
console.error('rewritten = ' + hits + ', misses = ' + misses);
fs.writeFileSync(outPrefix + '.deob.js', out);
console.log('OK table=' + Object.keys(table).length + ' rewrites=' + hits + ' misses=' + misses);
