# Tasks

מצב מעודכן ל-2026-10-12. היסטוריה מלאה ב-[AGENT_LOG.md](AGENT_LOG.md).

## הושלם

### שרשרת הארכיון
- [x] בדיקת API של כל-זכות, אימות רישיון והיקף (7,371 דפי תוכן)
- [x] הורדה מלאה ראשונית (טקסט וקישורים בלבד, ללא תמונות)
- [x] ניקוי תכנים (`kolzchut_remove_content.py`) + אינדקס + פורטל עם חיפוש מקומי
- [x] אריזת ZIP + `manifest.json` עם sha256 לכל דף (`kolzchut_release.py`)
- [x] סנכרון דלתא מבוסס sitemap + אימות מחיקות מול האתר החי
- [x] `last_sync.txt` מתקדם רק בריצה מוצלחת מלאה; כשלים נשמרים ב-`retry_queue.json`
- [x] Backfill של `lastmod` לאינדקס

### מודל העדכונים המבוזר
- [x] `kolzchut_contribute.py` — סנכרון מקומי → branch → PR עם תווית
- [x] `kolzchut_local_sync.py` — עטיפה; ברירת מחדל מפנה ל-contribute
- [x] `pr-check.yml` — שער בדיקות עם סקריפטים מ-master בלבד (ללא הרצת קוד מה-PR)
- [x] אכיפת מסנן התוכן האמיתי בצד GitHub (חייב להיות no-op על כל הדפים)
- [x] `auto-merge.yml` — מיזוג אוטומטי מונחה-אירוע + הפעלת בניית Release
- [x] הגנת master: Branch Protection (required check `verify`, linear history, ללא דחיפה ישירה)
- [x] טיפול בהתנגשויות: בדיקת עדכניות לפני הסנכרון + שער `mergeStateStatus`
- [x] אין פרסום חלקי: `failed > 0` עוצר לפני PR וגם חוסם ב-CI
- [x] בדיקות e2e: PR שנוצר → אימות → מיזוג אוטומטי ל-master

### סבב חיסום (2026-10-12)
- [x] תיקון פרצת אמון: ה-CI הריץ את סקריפט האימות **מה-PR** במקום מ-master
- [x] `kolzchut_verify.py`: baseline מודע ל-Git LFS — קודם הבדיקה התבטלה בשקט
- [x] `--require-baseline`: baseline לא-שמיש נכשל בקול במקום להיעלם מהשער
- [x] `auto-merge.yml`: `actions: write` (הפעלת ה-Release נכשלה ב-403)
- [x] `auto-merge.yml`: `workflow_run` במקום polling שננעל על ה-check runs של עצמו
- [x] הגנת "תוכן בלבד": שינויי תשתית לא ממוזגים אוטומטית
- [x] `kolzchut_local_sync.py --direct`: תיקון `TypeError` (shell הועבר פעמיים)
- [x] `kolzchut_remove_content.py`: `--out` לאכיפה ב-CI
- [x] `requirements.txt` + יישור `HOW_TO_RUN.md`/`TASKS.md`/`DISTRIBUTED_UPDATES.md` למציאות
- [x] אימות מול GitHub (PR #4): ה-workflow של PR רץ **מה-PR** — הבקרה הקובעת עברה ל-auto-merge
- [x] בלוקר bootstrap: `pip install -r requirements.txt` על checkout של master — תוקן לתלויות מפורשות
- [x] בדיקת טריות ב-auto-merge (SHA של הריצה מול head ה-PR)

## בביצוע

- [ ] הרצת סנכרון דלתא סדיר מהמחשב המקומי (או VPS עם אישור מפורש מכל-זכות)

## ממתין

- [ ] בקשת גישה רשמית מכל-זכות לסנכרון אוטומטי מהענן
- [ ] הגדרת `CODEOWNERS` להגנה נוספת על `.github/` ו-`*_verify.py` (ראה DECISIONS)
- [ ] תרחיש בדיקה מלא של התנגשות בין שני מעדכנים בזמן אמת
