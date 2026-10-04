const fs = require('fs');
const src = fs.readFileSync(process.argv[2], 'utf8');
const retIdx = src.indexOf('return[', src.indexOf('(function(){'));
const iifeStart = retIdx - '(function(){'.length;
const fnStart = src.lastIndexOf('function', iifeStart);
let depth = 0, k0 = src.indexOf('{', fnStart), fnEndIdx = -1;
for (let k = k0; k < src.length; k++) {
  if (src[k] === '{') depth++;
  else if (src[k] === '}') { depth--; if (depth === 0) { fnEndIdx = k; break; } }
}
const fnBody = src.slice(fnStart, fnEndIdx + 1);
console.log('fnBody length', fnBody.length);
console.log('head:', fnBody.slice(0, 60));
console.log('tail:', fnBody.slice(-90));
const tag = src.match(/var\s+(_0xod[A-Za-z0-9]+)\s*=\s*'([^']*)'/);
const out = 'var ' + tag[1] + ' = ' + JSON.stringify(tag[2]) + ';\n'
  + 'try { const A = (' + fnBody + ')(); console.log("OK len", A.length, "A[0]", JSON.stringify(A[0])); '
  + 'require("fs").writeFileSync(process.argv[2] + ".arr.rot.json", JSON.stringify(A)); } '
  + 'catch (e) { console.log("ERR", e.message); }';
fs.writeFileSync(process.argv[3], out);
console.log('wrote', process.argv[3]);
