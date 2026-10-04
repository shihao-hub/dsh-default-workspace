const fs = require('fs');
const vm = require('vm');
const E = (s) => JSON.stringify(s);

function extractArrayFn(src) {
  const retIdx = src.indexOf('return[', src.indexOf('(function(){'));
  const fnStart = src.lastIndexOf('function', retIdx - '(function(){'.length);
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
}

const file = process.argv[2];
const indices = process.argv.slice(3).map(h => parseInt(h, 16));
const src = fs.readFileSync(file, 'utf8');
const tag = src.match(/var\s+(_0xod[A-Za-z0-9]+)\s*=\s*'([^']*)'/);
const af = extractArrayFn(src);
const rc = { __out: null };
vm.createContext(rc);
new vm.Script('var ' + tag[1] + ' = ' + E(tag[2]) + ';\n' + af.body + '\n__out = ' + af.name + '();')
  .runInContext(rc, { timeout: 60000 });
const arr = rc.__out;

const fnRe = /function (_0x[0-9a-f]+)\((_0x[0-9a-f]+),(_0x[0-9a-f]+)\)\{/g;
let m, dec = null;
while ((m = fnRe.exec(src)) !== null) {
  if (src.slice(m.index, m.index + 6000).includes('fromCharCode')) { dec = { name: m[1], idx: m.index }; break; }
}
const dc = { __arr: arr };
vm.createContext(dc);
vm.runInContext('function ' + af.name + '(){ return __arr; }', dc);
vm.runInContext(extractFn(src, dec.idx) + '\n__dec = ' + dec.name + ';', dc);

const aliases = new Set([dec.name]);
for (let pass = 0; pass < 5; pass++) for (const a of [...aliases]) {
  const r = new RegExp('([A-Za-z_$][\\w$]*)\\s*=\\s*' + a.replace(/\$/g, '\\$') + '\\b', 'g');
  let mm; while ((mm = r.exec(src)) !== null) aliases.add(mm[1]);
}
const salts = new Set();
for (const a of aliases) {
  const r = new RegExp(a.replace(/\$/g, '\\$') + "\\(0x[0-9a-fA-F]+\\s*,\\s*'([^']*)'\\)", 'g');
  let mm; while ((mm = r.exec(src)) !== null) salts.add(mm[1]);
}
for (const idx of indices) {
  const found = [];
  for (const salt of salts) {
    try {
      const v = dc.__dec(idx, salt);
      if (typeof v === 'string' && v && /^[\x20-\x7e]+$/.test(v)) found.push([salt, v]);
    } catch (e) {}
  }
  const uniq = new Map();
  for (const [s, v] of found) if (!uniq.has(v)) uniq.set(v, s);
  console.log('0x' + idx.toString(16) + ' -> ' + [...uniq.entries()].map(([v, s]) => E(v) + '  [salt ' + E(s) + ']').join(' | '));
}
