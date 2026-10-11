# קל-ז-אפ (KolZchut offline) — ארכיון אופליין מתעדכן של אתר כל זכות

ארכיון אופליין מלא של אתר [כל זכות](https://www.kolzchut.org.il) —
7,300+ דפי מידע על זכויות בישראל — עם **מנגנון עדכון דלתא (Delta updates)**:
לא צריך להוריד הכול שוב; התוכנה מעדכנת רק את הדפים שהשתנו.

---

## ארכיטקטורה

```
┌────────────────────┐          ┌─────────────────────┐
│ KolZchut wiki API  │◄──rt─────│  GitHub Actions     │
│ (kolzchut.org.il)  │          │  - סורק RecentChanges│
└────────────────────┘          │  פעם ביום            │
                                │  - מעדכן דפים שהשתנו │
                                │  - מבנה ZIP מלא     │
                                │  - מפרסם Release    │
                                └─────────┬───────────┘
                                          │
                                          ▼
                                ┌─────────────────────┐
        דפדפן מקומי     │  גרסה חדשה ב-GitHub │
   ┌──────────────┐              │  (manifest.json)    │
   │  index.html  │◄─────────────│                     │
   │  בדיקת גרסה   │              └─────────────────────┘
   │  + הודעת עדכון│
   └──────────────┘
```

### רכיבים

| קובץ | תפקיד |
|---|---|
| `kolzchut_download.py` | הורדה מלאה ראשונית (7,358 דפים) |
| `kolzchut_sync_delta.py` | סנקרון דלתא: RecentChanges → הורדת דפים שהשתנו |
| `kolzchut_build_portal.py` | בניית דף בית עם חיפוש מקומי |
| `kolzchut_remove_content.py` | הסרת תכנים בעייתיים (רשימת מילים/דפים) |
| `kolzchut_release.py` | אריזת גרסה (ZIP + manifest.json) |
| `.github/workflows/daily-sync.yml` | אוטומצייה יומית ב-GitHub |

---

## זרימה

### שלב 1 — הורדה מלאה ראשונית (חד-פעמי)

```bash
python kolzchut_download.py
```
→ `kolzchut_out/pages/` (7,358 דפי HTML) + `kolzchut_out/index.json`

### שלב 2 — ניקוי תכנים (אופציונלי, לפני אריזה)

```bash
python kolzchut_remove_content.py --remove-pages "דף 1" "דף 2" --blank-pages "דף 3"
python kolzchut_remove_content.py --remove-words "מילה1" "מילה2"
```

### שלב 3 — בניית פורטל

```bash
python kolzchut_build_portal.py
```
→ `kolzchut_out/index.html` (אינדקס + חיפוש מקומי)

### שלב 4 — אריזת גרסה

```bash
python kolzchut_release.py
```
→ `releases/kolzchut_v<date>.zip` + `manifest.json` (רשימת כל דף + hash)

---

## מנגנון העדכונים (Delta)

מדיה-ויקי מספקת ערוץ עדכונים מובנה: `list=recentchanges`.
לא צריך לסרוק את כל הויקי פעם ביום — בודקים **מה השתנה מאז הסנקרון הקודם**:

```bash
python kolzchut_sync_delta.py
```

הסקריפט:
1. קורא `last_sync.txt` (חותמת זמן של הסנקרון האחרון).
2. מבקש מה-API `list=recentchanges&rcstart=<last_sync>&rcend=now` ומזהה רק דפים שהשתנו.
3. מוריד רק את אותם דפים (בדרך-כלל עשרות בודדות ביום, לא אלפים).
4. משכתב בזהירות `last_sync.txt`.
5. אם דף נמחק בויקי → מוסיף אותו ל-`deleted_pages.json` (הסקריפט הבא यדע למחוק).
6. מפיק `delta.json` — רשימת דפים שהשתנו (לשימוש Another script, ל-Release).

ב-GitHub Actions: מריצים פעם ביום. אם היו שינויים
→ נבנה ZIP והוא יישלח כ-Release חדש.
אם אין שינויים → לא נוצר Release חדש.

### עדכון מקומי (המשתמש)

1. התוכנה (דף ה-index.html) מבצע בדיקת גרסה מול GitHub API (`releases/latest`).
2. אם יש גרסה חדשה → מוצגת הודעה עם קישור להורדה.
3. לאחר הורדה והחלפה → כל הדפים מתעדכנים.
* (עדכון חלקי של דפים בודדים — קיים גם בסקריפט: עדכון רק הדפים שב-delta.json)

---

## פרסום ב-GitHub

מפעילים `.github/workflows/daily-sync.yml` (ראו דוגמה בתיקיית `workflows/`).
ה-workflow רץ פעם ביום ב-04:00 UTC (06:00 שעון ישראל):
1. רץ `kolzchut_sync_delta.py`.
2. אם יש שינויים → אריזה ידנית/אוטומטית + יצירת Release עם ה-ZIP.
3. מפרסם Release חדש � soft-launch (draft עד אישור ידני).

---

## הרישיון

תוכן: [CC-BY-NC-SA-2.5-IL](https://creativecommons.org/licenses/by-nc-sa/2.5/il/) —
אין שימוש מסחרי; נדרש קרדיט בכל דף (מקור: אתר כל זכות, kolzchut.org.il).
הקוד: MIT.
