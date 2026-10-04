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

const file = process.argv[2];
const src = fs.readFileSync(file, 'utf8');
const tag = src.match(/var\s+(_0xod[A-Za-z0-9]+)\s*=\s*'([^']*)'/);
const retIdx = src.indexOf('return[', src.indexOf('(function(){'));
let cursor = retIdx, expr = '';
for (;;) {
  const arr = balanceSlice(src, cursor, '[', ']');
  expr += arr;
  const after = cursor + arr.length;
  if (src.startsWith('.concat(', after)) {
    const call = balanceSlice(src, after + 7, '(', ')');
    expr += '.concat' + call;
    cursor = after + 7 + call.length;
    continue;
  }
  break;
}
console.log('array expr length =', expr.length);
const ctx = { [tag[1]]: tag[2] };
vm.createContext(ctx);
const arr = vm.runInContext('(' + expr + ')', ctx);
console.log('array length =', arr.length, 'arr[0] =', JSON.stringify(arr[0]));
fs.writeFileSync(file + '.arr.raw.json', JSON.stringify(arr));
