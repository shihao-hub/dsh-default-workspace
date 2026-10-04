const segments = [
  '块 #1 thinking',
  `I'm checking the system details—the date is October 2, 2026, and I need to verify the machine hostname is ZHANGSHIHAO. The task involves downloading a Douyin video, transcribing and summarizing it, then posting the results as a reply in a Lark topic thread. The screenshot shows a task list with a Douyin share link and a request to summarize the video, but I'm missing the chat ID needed for the Lark integration.

I'm considering two approaches: either the user wants me to reply in a Lark topic, or they want me to post the summary directly here in the chat. Since the image mentions "this topic" with an AI prompt about calling skills, there's a risk of misattributing which topic they mean. Let me start by downloading the video first, then I can either search for the relevant Lark chat or ask for clarification if needed. I should also load the lark-shared documentation as required for the Lark integration part. I'll run the download command with JSON output in the background to avoid timeout issues, then read the lark-shared skill and verify the hostname in parallel. Since there's no explicit user request for a long-running goal, I'll skip creating one and just focus on completing`
];

console.log('Sending request...');
const start = Date.now();
try {
  const r = await fetch('http://127.0.0.1:19387/dsh-traj-translate/translate', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ segments })
  });
  console.log('Response status:', r.status, 'Elapsed:', (Date.now() - start), 'ms');
  const text = await r.text();
  console.log('Body:', text);
} catch (e) {
  console.error('Fetch error:', e);
}
