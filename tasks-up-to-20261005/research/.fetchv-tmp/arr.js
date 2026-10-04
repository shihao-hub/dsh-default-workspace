const fs = require('fs');
const vm = require('vm');

function balanceSlice(src, from, open, close) {
  // from = index of first '[' char; returns slice through matching ']'
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

/** Extract the full `return <expr>` expression text of the array IIFE. */
function extractArrayExpr(src, retIdx) {
  let k = retIdx;                    // index of '[' after 'return'
  let text = '';
  for (;;) {
    const arr = balanceSlice(src, k, '[', ']');
    if (arr === null) return null;
    text += arr;
    let after = k + arr.length;
    if (src.startsWith('.concat(', after)) {
      const call = balanceSlice(src, after + 7, '(', ')');
      if (call === null) return null;
      text += '.concat' + call;
      after = after + 7 + call.length;
      if (src.startsWith('.concat(', after)) { k = after; continue; }
    }
    return { expr: text, end: after };
  }
}

const file = process.argv[2];
const src = fs.readFileSync(file, 'utf8');
const retIdx = src.indexOf('return[', src.indexOf('(function(){'));
const got = extractArrayExpr(src, retIdx + 'return'.length);
if (!got) { console.error('extract failed'); process.exit(1); }
console.error('expr length = ' + got.expr.length + ', tail = ' + JSON.stringify(got.expr.slice(-20)));

const ctx = {};
vm.createContext(ctx);
// the array references the tag variable declared at the top of the bundle
const tagM = src.match(/var\s+(_0xod[A-Za-z0-9]+)\s*=\s*'([^']*)'/);
if (tagM) vm.runInContext('var ' + tagM[1] + ' = ' + JSON.stringify(tagM[2]) + ';', ctx);
let arr;
try { arr = vm.runInContext(got.expr, ctx); }
catch (e) { console.error('eval failed: ' + e.message); process.exit(1); }
console.error('array length = ' + arr.length + ', arr[0] = ' + JSON.stringify(arr[0]));
fs.writeFileSync(file + '.arr.json', JSON.stringify(arr, null, 0));
console.log('OK array ' + arr.length);
