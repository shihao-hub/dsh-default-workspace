// One-shot probe for the traj-translate route.
const url = 'http://127.0.0.1:19387/dsh-traj-translate/translate';
const body = process.argv[2] ?? '{"segments":["The client half is complete."]}';
try {
  const res = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body,
  });
  const text = await res.text();
  console.log('STATUS:', res.status);
  console.log('BODY:', text.slice(0, 2000));
} catch (error) {
  console.log('FETCH ERROR:', error?.message ?? error);
}
