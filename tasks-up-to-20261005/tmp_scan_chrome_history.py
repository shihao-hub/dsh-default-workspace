import os, sqlite3, shutil, tempfile, glob, datetime, sys

base = os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\User Data")
targets = []
for prof in os.listdir(base):
    hist = os.path.join(base, prof, "History")
    if os.path.isfile(hist):
        targets.append((prof, hist))

print(f"profiles with history: {[t[0] for t in targets]}")

kw = sys.argv[1] if len(sys.argv) > 1 else "douyin"

def chrome_time(t):
    if not t:
        return ""
    return (datetime.datetime(1601, 1, 1) + datetime.timedelta(microseconds=t)).strftime("%Y-%m-%d %H:%M")

rows_all = []
for prof, hist in targets:
    tmp = os.path.join(tempfile.gettempdir(), f"hist_{prof.replace(' ', '_')}.sqlite")
    try:
        shutil.copy2(hist, tmp)
    except Exception as e:
        print(f"[skip] {prof}: {e}")
        continue
    try:
        con = sqlite3.connect(tmp)
        cur = con.cursor()
        cur.execute(
            "SELECT url, title, last_visit_time, visit_count FROM urls "
            "WHERE url LIKE ? OR title LIKE ? ORDER BY last_visit_time DESC LIMIT 80",
            (f"%{kw}%", f"%{kw}%"),
        )
        for url, title, t, vc in cur.fetchall():
            rows_all.append((t, prof, title, url, vc))
        con.close()
    except Exception as e:
        print(f"[err] {prof}: {e}")
    finally:
        try:
            os.remove(tmp)
        except Exception:
            pass

rows_all.sort(reverse=True)
for t, prof, title, url, vc in rows_all[:80]:
    print(f"{chrome_time(t)} | {prof} | vc={vc} | {title[:70]} | {url[:150]}")
print(f"total matches: {len(rows_all)}")
