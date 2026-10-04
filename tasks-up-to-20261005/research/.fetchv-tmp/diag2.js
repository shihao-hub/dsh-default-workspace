const fs = require('fs');
const vm = require('vm');
const s = fs.readFileSync(process.argv[2], 'utf8');
const i = s.indexOf('(function(){return[');
const end = s.indexOf('];', i) + 1;          // index just past ']'
const expr = s.slice(i, end) + '})()';       // (function(){return[...]})()
console.log('expr len =', expr.length);
console.log('expr head =', JSON.stringify(expr.slice(0, 40)));
console.log('expr tail =', JSON.stringify(expr.slice(-12)));
try {
  const fn = new Function('return ' + expr);
  const arr = fn();
  console.log('PARSE OK, array length =', arr.length, 'arr[0] =', JSON.stringify(arr[0]));
} catch (e) {
  console.log('PARSE FAIL:', e.message);
  // find the first offset where concatenating breaks
  for (let n = 100; n < expr.length; n += 1000) {
    try { new Function('return ' + expr.slice(0, n) + ']})()'); }
    catch (err) { console.log('first break near offset', n, ':', err.message); break; }
  }
}
