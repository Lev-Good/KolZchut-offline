# יומן עבודה

## 2026-10-11 — בדיקת גישה מענן (probe) + תכניות VPS

### מטרה
לבדוק בהרצה אמיתית אם אפשר להריץ סנכרון יומי ב-GitHub Actions, ללא מחשב המשתמש.

### בוצע
- workflow ניסיוני `.github/workflows/cloud-probe.yml` (הרצה ידנית בלבד).
- ריצה אמיתית (run 38162887263): sitemap מביא HTTP **403**, דף מאמר ציבורי מביא HTTP **403**, עם UA מזוהה ותדירות מכובדת.
- מסקנה: GitHub runner נחסם על ידי האתר **לכל הנתיבים** — לא רק ה-API.
- נכתב `docs/VPS_DEPLOYMENT.md` — סקר ספקים📳 
  (JetServer ישראל, Vultr תל-אביב, OVH, Hetzner, Oracle free…), עלויות ותנאים.
- מוסדר: הרצת Release בענן ממשיכה לעבוד מהארכיון בריפו (ללא פנייה לכל-זכות).
- README עודכן לפי המציאות: סנכרון sitemap-based ממחשב מקומי/VPS; לא RecentChanges API.

### ראיות
```
[sitemap] status=403 content_type=text/html size=3457 err=HTTPError 403
[article] status=403 content_type=text/html size=3508 err=HTTPError 403
PROBE OUTCOME: BLOCKED/FAILED — cloud sync NOT confirmed
```
run: https://github.com/Lev-Good/KolZchut-offline/actions/runs/38162887263

### מקור
מחקר VPS עודכן אמפירית 11.10.2026.

### סטטוס
הושלם. אוטומציה מהענן אינה אפשרית ללא הרשאה מפורשת — ממשיכים בהרצה מקומית או VPS עם אישור.

## 2026-10-11 — תיקון מנגנון הסנכרונון (sitemap + אימות מחיקות)

### מטרה
לתקן את סנכרון ה-delta כך שיעבוד על דפים אמיתיים בלי false-changed / false-deleted.

### בוצע
- נמצא שה-API (api.php) מוגדר Disallow ב-robots.txt — לא משתמשים בו לשינויים.
- sitemap NS0 (מותר) => 7,348 דפים, עם lastmod לכל עמוד.
- נמצא: sitemap משמיט 10 דפים שקיימים באתר (HEAD חוזר 200) — לכן אימות מחיקות בפועל בקוד.
- kolzchut_sync_delta.py מתוקן: backfill lastmod, אימות HEAD למחיקות, false-positives leave.
- kolzchut_download.py: URL_SAFE משותף (היה כולל bug).

### בדיקות
- backfill: 7,348 עדכונים שמו lastmod.
- dry-run: changed=0 (במקום 7,348 שלפני התיקון), deleted=10 → אומת ומדוק (0 deleted).
- delta-sync e2e: דף "איסור הוצאה לחופשה..." שה-lastmod שלו רוסן ידנית ל-2024 → זוהה changed, הורד מה-article URL המותר, נשמר status ok + lastmod חדש (2026-08-16).
- סנכרון חוזר (run ריק): 0 changed / 0 deleted / cursor מתקדם רק בהצלחה.

### סטטוס
הושלם — מנגנון הסנכרון האוטומטי עובד על נתיב ה-article URL המותר.

### הערות
- GitHub Actions נחסם מהיקי (מ-IP של GitHub) — מבוצע מקומי באמצעות kolzchut_local_sync.py.

## 2026-10-11 — הקמת פרויקט והתשתית

### מטרה
הורדת אתר כל-זכות לצורך שימוש אופליין, טקסט וקישורים בלבד.

### בוצע
- אימות API: `https://www.kolzchut.org.il/w/he/api.php` עובד, MediaWiki 1.43, list=allpages פסיבי.
- אימות רישיון: CC-BY-NC-SA-2.5-IL.
- ההיקף: 7,371 דפי תוכן, 1,571 תמונות (תמונות הוסרו מההיקף לפי בקשת המשתמש).
- הקמת תיעוד: SPEC.md, DECISIONS.md, TASKS.md.

### סטטוס
בתהליך — כתיבת סקריפט הורדה בהמשך.

## 2026-10-11 — סקריפט הורדה + פיילוט 50 דפים + פורטל עם חיפוש

### בוצע
- `kolzchut_download.py` — הורדת דפים דרך API, ניקוי (ללא תמונות/סקריפטים/כרום), כתיבת HTML מקומי עם קרדיט רישיון, index.json להמשך.
- `kolzchut_build_portal.py` — דף בית RTL עם אינדקס אלפביתי + חיפוש מקומי מוטמע (JSON בתוך הדף, עובד גם מ-file://).
- פיילוט: 50 דפים ראשונים הורדו בהצלחה (0 כשלים), מהירות 2.7 דפים/שנייה.
- בדיקה ידנית בדפדפן: דף בית, חיפוש, מעבר לקישור — כל הזרימה עובדת.

### בעיות ופתרונות
- Windows MAX_PATH: קידוד אחוזים הפך שמות לנתיבים ארוכים מדי (`OSError: Invalid argument`). הפתרון: שמות עבריים קריאים + סיומת MD5 (8 תווים) לשמירה על ייחודיות.
- השרת המובנה של Preview מגיש קובץ בודד בלבד (404 על קבצי pages/). החלפה ב-`python -m http.server` רגיל — עובד אקסטרא.

### הערה חשובה על ZIP
פתיחת ZIP והרצה מתוך חלון file:// עובדת רק אם החיפוש המוטמע מוטמע בדף בית (מצב קיים). שימוש מ-`file://` זמין ומתוקן בכוונה.

### בדיקות
- פיילוט: 50/50 דפים הורדו.
- פורטל: חיפוש מוצא ומציג תוצאות נכון.
- ניווט אל דף תוכן עובד.

### סטטוס
פיילוט הושלם — ממתין לאישור המשתמש להרצה המלאה (7,358 דפים).

## 2026-10-11 — מערכת עדכונים מלאה (גירסת Release)

### מטרה
הפיכת הארכיון למוצר מתעדכן: סריקת RecentChanges יומית ב-GitHub Actions, Release עם ZIP, והודעת עדכון בתוך התוכנה (בלי סריקת הכול).

### בוצע
- אימות `list=recentchanges` עובד ב-API של כל-זכות — יש ערוץ עדכונים, אין צורך בסריקה מלאה.
- `kolzchut_sync_delta.py` — סנקרון דלתא: קורא last_sync.txt, מזהה דפים שהשתנו/נמחקו, מוריד רק אותם, מפיק delta.json. נבדק: 22 דפים ב-9 שניות על חלון 3 ימים.
- `kolzchut_release.py` — ZIP + manifest.json עם sha256 לכל דף + version.
- `kolzchut_remove_content.py` — הסרת דפים/ריקון דפים/עריכת פסקאות לפי מילות מפתח + רשימה מובנית לחרדים. נבדק: scrub של פסקה בודדת עבד.
- `.github/workflows/daily-sync.yml` — ריצה יומית 06:00 שעון ישראל, dry-run bootstrap, Release אוטומטי כשיש שינויים.
- דף הבית: בדיקת גרסה מול GitHub Releases API (releases/latest) + הודעת "קיימת גרסה חדשה" + version.txt מקומי.
- הרצה בפועל: build portal (4,325 דפים שנורדו עד עתה) + release ZIP 26.6MB.

### קבצים
kolzchut_sync_delta.py, kolzchut_release.py, kolzchut_remove_content.py, .github/workflows/daily-sync.yml, kolzchut_build_portal.py (edited), README.md, docs/*

### בעיות
- steps.date לא הוגדר ב-workflow — תוקן ל-steps.release.outputs.date.
- ארכיון נוכחי 4,325/7,358 דפים (הרצה מלאה לא הושלמה עדיין בפועל — הפיילוט על 50 + דלתא לא מכסה את ההיקף המלא).

### סטטוס
הושלם מבחינת קוד; נותרו: הרצה מלאה מקיפה + העלאה ל-GitHub (מחייב החלטת משתמש על שם ריפו).

## 2026-10-11 — פרסום מלא ל-GitHub + Release אוטומטי

### מטרה
יצירת ריפו ציבורי, העלאת קוד + ארכיון מלא, והפעלת Release אוטומטי.

### בוצע
- ריפו חדש: **https://github.com/Lev-Good/KolZchut-offline** (public).
- הורדה מלאה הושלמה ע"י המשתמש: 7,358/7,358 דפים.
- פורטל נבנה מחדש עם `--github-repo` (בדיקת עדכונים פעילה) + release ZIP 42.3MB.
- Release ראשון פורסם ידנית: **v20261011**.
- GitHub Actions נכשל על רנר-ענן: הויקי של כל-זכות חוסם בקשות מ-IP של GitHub. פתרון: workflow חדש שבונה Release מהארכיון שכבר בריפו (LFS), וסקריפט סנקרון מקומי `kolzchut_local_sync.py` (דלתא -> סינון -> פורטל -> push -> workflow run).
- kolzchut_out עלה לריפו דרך Git LFS (7,365 קבצים, 166MB).
- תקלת push: ספק הסינון (Etrog) חסם העלאה של אובייקט LFS אחד ל-S3 של GitHub — פתרון: שינוי זעיר בקובץ שינה את ה-hash ואיפשר העלאה.
- workflow ירוק: **v202610111558** פורסם אוטומטית מהארכיון בריפו (1m42s).

### ארכיטקטורת עדכונים סופית
1. מחשב מקומי (המשתמש): `python kolzchut_local_sync.py` — דלתא מהויקי + סינון + push.
2. GitHub Actions: בונה ZIP מהארכיון המעודכן בריפו ומפרסם Release.
3. משתמשי-קצה: דף הבית מציג הודעת עדכון ומוביל ל-Release החדש.

### סטטוס
הושלם. הפצה פעילה.

## 2026-10-12 — סבב חיסום מלא של מערכת העדכונים המבוזרת

### מטרה
סריקה מלאה של המערכת, איתור ותיקון שגיאות, והכנה להפצה מלאה.

### בוצע
- סריקת כל הסקריפטים, ה-workflows, התיעוד, מצב ה-Git והגנות הענף.
- איתרתי ותיקנתי 6 בעיות אמיתיות (להלן) + יישור תיעוד.
- `requirements.txt` חדש; עדכון `.gitignore`; החלטות מתועדות ב-DECISIONS.md.

### בעיות שנמצאו ותוקנו
1. **פרצת אמון (קריטית):** pr-check הריץ את `kolzchut_verify.py` מתוך ה-PR.
2. **בדיקה שהתבטלה בשקט:** ה-baseline הוא מצביע LFS → בדיקת השינוי החריג לא רצה.
3. **auto-merge לא יכול היה להצליח:** polling על rollup שכלל את ה-check runs של עצמו.
4. **הפעלת Release נכשלה (403):** חסרה הרשאת `actions: write`.
5. **`TypeError` במסלול `--direct`:** `shell` הועבר פעמיים ל-`subprocess.run`.
6. **סינון לא נאכף ב-CI:** רק נדגם, לא הורץ המסנן האמיתי. בנוסף תיעוד מיושן
   (HOW_TO_RUN הצהיר על סנכרון ענן יומי שאינו קיים).

### קבצים שהושפעו
- `.github/workflows/pr-check.yml`, `.github/workflows/auto-merge.yml`
- `kolzchut_verify.py`, `kolzchut_contribute.py`, `kolzchut_local_sync.py`, `kolzchut_remove_content.py`
- `requirements.txt`, `.gitignore`, `HOW_TO_RUN.md`
- `docs/TASKS.md`, `docs/DISTRIBUTED_UPDATES.md`, `docs/DECISIONS.md`, `docs/AGENT_LOG.md`, `docs/SPEC.md`

### בדיקות
- `py_compile` לכל סקריפטי ה-Python — עובר.
- `yaml.safe_load` לכל ה-workflows — עובר; שמות ה-workflows מוצלבים מול `workflow_run` ומול בניית ה-Release.
- `kolzchut_verify.py --baseline origin/master`: לפני התיקון `size_delta_vs_baseline`
  נעדר מהדוח; אחריו הוא מופיע והריצה מסתיימת ב-exit 0.
- `kolzchut_local_sync.run(..., shell=True)`: לפני — `TypeError: got multiple values
  for keyword argument 'shell'`; אחרי — ריצה תקינה.
- Branch Protection אומת דרך ה-API: required check `verify`, `enforce_admins`, linear history.

### בעיות פתוחות
- שינויי תשתית (כמו PR זה) אינם מתמזגים אוטומטית במכוון — נדרש מיזוג של המנהל.


## 2026-10-12 — סבב שני: אימות מול GitHub (PR #4)

### מטרה
לוודא שהתיקונים עובדים בפועל ב-CI של GitHub, לא רק מקומית.

### בוצע
- ענף `infra/distributed-pipeline-hardening`, PR #4 (15 קבצים).
- הריצה הראשונה נכשלה בשלב "Install deps".

### בעיות שנמצאו בריצה
7. **בלוקר bootstrap:** ה-workflow רץ על ה-checkout של master, שאין בו
   `requirements.txt` → ה-check הנדרש `verify` נכשל → אי-אפשר למזג (deadlock).
8. **ממצא ארכיטקטוני:** הריצה הוכיחה ש-GitHub מריץ לאירועי `pull_request` את קובץ
   ה-workflow **מתוך ה-PR** (הפקודה שהורצה קיימת רק ב-PR). לכן `pr-check.yml` לבדו
   אינו שכבת אמון, והבקרה הקובעת עברה ל-`auto-merge.yml`.

### פתרון
- ה-CI מתקין תלויות מפורשות; הארכיון עובר לנתיב ברירת המחדל; הוסר השימוש בדגלים
  חדשים (`--baseline-index`, `--require-baseline`) לטובת `--baseline origin/master`
  ש-master תומך בו — כך השער עובד לפני המיזוג ואחריו.
- `auto-merge`: הגנת תוכן-בלבד היא הבקרה הקובעת + בדיקת טריות SHA מול head ה-PR.
- `kolzchut_verify.py`: baseline מבוקש שאינו קריא = שגיאה קשה במקום דילוג שקט.

### בדיקות
- `py_compile` ל-8 סקריפטים; `yaml.safe_load` + `bash -n` + `compile()` לכל בלוק
  מוטמע ב-workflows — 0 כשלים.
- שער הסינון (הקוד שחולץ מה-workflow עצמו) בשני כיוונים: לא-מסונן → exit 1,
  מסונן → exit 0.
- baseline: ללא → exit 0 בלי הבדיקה; `origin/master` → exit 0 עם הבדיקה;
  ref לא-קיים → exit 1 עם הודעה מפורשת.

### סטטוס
חלקי — ממתין לריצת CI ירוקה ולמיזוג אנושי (PR תשתית).

## 2026-10-12 — חבילת רגרסיה קבועה לשער + חיווט ל-CI

### מטרה
שהשער (סינון, מחיקות, שינוי גודל, baseline לא-קריא, אינווריאנטים של אמון) לא יישבר
בשקט ע"י שינוי עתידי — במקום בדיקות ידניות חד-פעמיות, חבילה קבועה בפרויקט.

### בוצע
- `tests/test_archive_gate.py` (חדש) — 30 בדיקות שמריצות את הקוד האמיתי.
- `pr-check.yml`: שלב חדש שמריץ את החבילה **אחרי** staging (כדי שבדיקת הארכיון
  תראה תוכן אמיתי ולא מצביע LFS), עם שער "אפס בדיקות אינו ירוק".
- `.github/workflows/gate-tests.yml` (חדש): אותה חבילה על `push` ל-master, שם קוד
  השער נלקח מ-master עצמו. ב-PR אין נקודה כזו: ה-workflow מגיע מה-PR והבדיקות
  רצות מול סקריפטי ה-BASE.
- אכיפת מלאי: `EXPECTED_GATE_TESTS` + בדיקת ספירה — מחיקת הבדיקה שתפסה בעיה
  נתפסת בעצמה.
- תיעוד: README, HOW_TO_RUN, docs/DISTRIBUTED_UPDATES, docs/DECISIONS, docs/TASKS.

### קבצים שהושפעו
- `tests/test_archive_gate.py`, `.github/workflows/pr-check.yml`,
  `.github/workflows/gate-tests.yml`, `kolzchut_verify.py` (אזהרות ל-stderr),
  `README.md`, `HOW_TO_RUN.md`, `docs/*`

### בדיקות
- החבילה: 30/30 עוברות מקומית, ~15 שניות (כולל אימות הארכיון האמיתי — 7,358 דפים).
- בדיקת מוטציות על עותק של העץ (11 מוטציות) — כולן הפילו בדיקה בשם מפורש:
  verifier מה-PR · `pip install -r requirements.txt` · ניטרול שער הסינון · השתקת
  כשל baseline · הסרת `actions: write` · הסרת הגנת התוכן-בלבד · חזרה ל-polling ·
  המרת `exit "$status"` ל-`exit 0` · הסרת שער "אפס בדיקות" · מחיקת שלב הרצת
  החבילה מ-pr-check · שינוי הטריגר של `gate-tests.yml`.
- שלב ה-CI הורץ ישירות (חילוץ מה-YAML) ב-4 תרחישים: ארכיון אמיתי → exit 0;
  master בלי `tests/` → דילוג; אפס בדיקות → exit 1; בדיקה נכשלת → exit 1
  (כלומר `tee` אינו בולע כשל).
- `yaml.safe_load` + `bash -n` לכל בלוק shell + `compile()` לכל בלוק Python מוטמע,
  בכל 5 ה-workflows — 0 כשלים.
- שלב ה-CI הורץ **בפועל** ב-CI האמיתי (run 38179028636, commit 884ca3a): הוא רץ
  ודילג במפורש ("no tests/ on the base branch … skipping") כי master שלפני המיזוג
  אינו מכיל `tests/`; שאר השער עבר — `VERIFY OK` · `baseline pages: 7358` ·
  `content filter is a no-op on all 7358 pages` · `deletion check ok`.

### בעיות שנמצאו
- אזהרות ה-baseline נכתבו ל-stdout וזיהמו את דוח ה-JSON של `kolzchut_verify.py`.
  תוקן ל-stderr, ונוספה בדיקה מפורשת בחבילה (`test_stdout_stays_pure_json...`).
- שלב ה-CI הסתמך תחילה על `-e` המשתמע של ה-runner; הוחלף בלכידת סטטוס מפורשת
  (`status=$?` + `exit "$status"`) כדי שכשל לא ייבלע ע"י `tee`.

### סטטוס
הושלם מקומית. החבילה טרם רצה ב-CI: עד המיזוג אין `tests/` ב-master, ולכן שלב
ה-CI מדלג במפורש ("bootstrap") — ההרצה הראשונה תהיה ב-PR התוכן הבא.

