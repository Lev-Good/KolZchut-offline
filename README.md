# קל-ז-אפ (KolZchut offline) — ארכיון אופליין מתעדכן של אתר כל זכות

ארכיון אופליין מלא של אתר [כל זכות](https://www.kolzchut.org.il) —
7,300+ דפי מידע על זכויות בישראל — עם **מנגנון עדכון דלתא (Delta updates)**:
לא צריך להוריד הכול שוב; התוכנה מעדכנת רק את הדפים שהשתנו.

---

## גישת הרשת האמיתית (מגבלות חשובות)

| מה | סטטוס |
|---|---|
| MediaWiki Action API (`/w/he/api.php`) | **חסום / מוגדר כ־Disallow על ידי robots.txt** — לא לשימוש באוטומציה |
| Sitemap NS0 (`/sitemap/sitemap-kz_he-NS_0-0.xml.gz`) | מותר — כולל `lastmod` לכל דף |
| פיד Atom לשינויים | מותר אך מוגבל להיסטוריה קצרה |
| דפי מאמרים (`/he/<page>`) | מותרים — עם **Crawl-delay: 5** בין בקשות |
| GitHub‑hosted runner (Actions) | **חסום** — HTTP 403 מכל נתיב על האתר (נבדק בפועל, run 38162887263, 11.10.2026) |
| VPS פרטי | **אפשרי — מומלץ לקבל אישור מפורש מכל-זכות** לפני ריצה |

מנגנון הסנכרון הוא **sitemap‑based** (לא RecentChanges API):
משווה את `lastmod` של כל דף בה-sitemap מול `lastmod` שנשמר ב־`index.json` —
ובכך מזהה דפים חדשים, משונים, ונמחקים, בלי לסרוק מחדש את האתר ובלי להשתמש ב־API.

---

## ארכיטקטורה

```
┌──────────────────────┐            ┌────────────────────────┐
│   sitemap NS0 (gz)    │──────────► │   מחשב מקומי / VPS      │
│ kolzchut.org.il       │  (מותר)   │  kolzchut_sync_delta.py │
└──────────────────────┘            │  או kolzchut_local_sync.py│
                                    └──────────┬─────────────┘
                                               │ (לחיצה ידנית / cron יומי מקומי)
                                               │ push kolzchut_out (LFS)
                                               ▼
                                    ┌────────────────────────┐
   דפדפן מקומי                      │      GitHub             │
  ┌───────────────┐                │ kolzchut_out/ בריפו      │
  │  index.html   │◄───in-app──── │ workflow Build release  │
  │  בדיקת גרסה    │  version check│ → ZIP Release           │
  │  + הודעת עדכון │                │                          │
  └───────────────┘                └────────────────────────┘
```

### רכיבים

| קובץ | תפקיד |
|---|---|
| `kolzchut_download.py` | הורדה מלאה ראשונית (7,358 דפים) — דרך ה-API; לשימוש חד-פעמי מקומי |
| `kolzchut_sync_delta.py` | סנכרון דלתא: sitemap lastmod → הורדת דפים שהשתנו (דרך דפי מאמרים מותרים) |
| `kolzchut_build_portal.py` | בניית דף בית עם חיפוש מקומי |
| `kolzchut_remove_content.py` | הסרת תכנים בעייתיים (רשימת מילים/דפים) |
| `kolzchut_release.py` | אריזת גרסה (ZIP + manifest.json) |
| `kolzchut_local_sync.py` | ריצת־על יומית: סנכרון → סינון → פורטל → push → trigger Release |
| `.github/workflows/daily-sync.yml` | בניית ZIP/Release מהארכיון הקיים בריפו (ללא גישה לאתר) |
| `.github/workflows/cloud-probe.yml` | בדיקת גישה ענן (ריצה ידנית؛ הראתה 403 מ-runners) |

---

## זרימת סנכרון (kolzchut_sync_delta.py)

1. שולף sitemap טרי: `{title: lastmod}`.
2. משווה מול `index.json` (ששומר `lastmod` המקומי): חדש / משונה / נמחק.
3. אם דף מסומן כנמחק ב-sitemap → מבצע **HEAD** לכתובת הציבורית לפני מחיקה מהארכיון.
   ה-sitemap משמיט לפעמים דפים קיימים — אסור להסתמך עליו למחיקות בלבד.
4. מוריד רק דפים משונים/חדשים דרך **דפי המאמרים הציבוריים** (Crawl-delay 5).
5. מציב `last_sync.txt` רק אחרי ריצה שלמה (כשלים נשמרים לריצה הבאה דרך `retry_queue.json`).
6. מעדכן `index.json` + `delta.json` + `sync_log.jsonl` + `deleted_pages.json`.

## זרימה יומית מומלצת

### אופציה A — מהמחשב המקומי (המנגנון הנוכחי)
```bash
python kolzchut_local_sync.py        # סנכרון דלתא → סינון → פורטל → push → workflow run
```
ניתן לשלב ב־cron / Windows Task Scheduler פעם ביום.

### אופציה B — VPS עצמאי (לא תלוי במחשב שלך)
ראה `docs/VPS_DEPLOYMENT.md` להשוואת ספקים, עלויות ותנאים.
כולל את הדרישה לקבלת אישור מכל-זכות לריצה סדירה מכתובת IP ציבורית.

### בניית Release ב-GitHub (עובד בענן, ללא גישה לאתר)
```bash
gh workflow run "Build release from committed archive"
```
ה-workflow מבוסס רק על `kolzchut_out/` שהועלה כבר לריפו (LFS) — לא פונה לכל-זכות.

---

## בדיקת גרסה מהדפדפן

דף הבית מבצע `fetch`/`$.ajax` ל־`api.github.com/repos/.../releases/latest`
ומציג הודעת עדכון כשמספר הגרסה החדש גבוה מהמקומי (`version.txt`).
בשימוש מ-`file://` הבדיקה עשויה להיחסם בדפדפנים — ההודעה עשויה שלא להופיע;
אין נזק פונקציונלי.

## הרישיון

תוכן: [CC‑BY‑NC‑SA‑2.5‑IL](https://creativecommons.org/licenses/by-nc-sa/2.5/il/) —
אין שימוש מסחרי; נדרש קרדיט בכל דף (מקור: אתר כל זכות, kolzchut.org.il).
קוד: MIT.
