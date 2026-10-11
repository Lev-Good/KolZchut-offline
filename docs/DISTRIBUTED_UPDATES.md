# מודל העדכונים המבוזר — KolZchut-offline

## מטרה
מספר משתמשים מורשים יכולים ללחוץ "עדכן מאגר" ולשלוח עדכון מהמחשב המקומי
שלהם — בלי תלות במחשב של הפרויקט — והעדכון עובר בדיקות אוטומטיות
ומיזוג לגרסה הרשמית ב-GitHub Releases.

## ארכיטקטורה

```
contributor computer           GitHub CI                        end user
  kolzchut_contribute.py        pr-check.yml                     index.html
  1. local delta sync            1. verify integrity              1. welcome screen
  2. content filter              2. filter check                  2. update check
  3. archive verify              3. deletion / failure checks     3. download latest ZIP
  4. branch + commit             4. auto-merge (if all pass)
  5. open PR + label             5. trigger Release
                                 6. Release ZIP published
```

## אבטחה והרשאות

### מה מותר למעדכנים מורשים
- **push לענף ייעודי בלבד** (`sync/auto-update-...`).
- לפתוח PR עם label `auto-merge-candidate`.
- **אין דחיפה ישירה ל-master** — הענף מוגן (Branch Protection).

### הזדהות
- אין אסימונים משותפים.
- כל מעדכן משתמש בחשבון GitHub האישי שלו (`gh auth login` + `gh auth setup-git`).
- ההרשאות מנוהלות דרך הגדרת ה-collaborator של הריפו ב-GitHub (least privilege).

### הפרדת אמון ב-CI
- סקריפטי האימות (kolzchut_verify.py, kolzchut_remove_content.py,
  kolzchut_sync_delta.py) מגיעים מ-master בלבד.
- התוכן מה-PR (kolzchut_out/pages, index.json, delta.json) נקרא
  כנתונים — לא מורץ כקוד על ידי CI.
- ל-runner אין הרשאות כתיבה בזמן הבדיקות.

## טיפול במצבים קריטיים

### עדכון חלקי / כושל
- kolzchut_contribute.py דורש בדיקת אימות מקומית עמידה לפני פתיחת PR.
- kolzchut_verify.py נכשל עם קוד exit 1 אם אחד מהבדיקות לא עובד —
  ה-PR לא נפתח.

### התנגשויות בין מעדכנים
- master שהתקדם מאז תחילת סנכרון → GitHub מזהה `mergeStateStatus: DIRTY`
  → auto-merge מבטל ושולח דוח כישלון ב-PR המזריע לפתוח מחדש.
- עדכונים כפולים (שני PRs עם אותם דפים) → מסנכרן בזהירות; אחד מקבל עדיפות
  דרך label  auto-merge-candidate המוגדר כיום ל-PR עם שינויים המתקבלים
  אוטומטית מהסקריפט.

### שמירה על הגרסה האחרונה התקינה
- אין פרסום כשיש כישלון — הגרסה הקודמת ממשיכה לעמוד.
- דוח שגיאה מופק על ה-PR הכושל.
- `delta.json` יוצא עם `failed: 0` והתהליך חוזר ב-CI כפלט גישה.

## בדיקות ##

### CI בזמן PR
- שלמות אינדקס: כל דף status=ok קיים בדיסק (גודל > 0).
- אין דפים יתומים / כפילויות slug בין ניתוק.
- קישורים פנימיים: פחות מ-2% שבורים מהדגימה.
- סינון: דגימת 400 דפים ללא script/img/iframe/video/audio/object/embed.
- דפי מחיקות חריגים: <1% מהארכיון.
- דו"ח סנכרון: failed = 0.
- גודל סביר: מ-200 דפים למטה, או מ-2,000 דפים למעלה — מסומן כחריגה.

### תרחישי בדיקה למקרה של עריכה ידנית
- עדכון רגיל עם דף אחד changed → merge + Release חדש.
- כשל בהורדת דף → delta.json failed > 0 → CI חוסם, אין פרסום.
- מחיקה חריגה של דפים → CI חוסם, אין פרסום.
- master נע תוך כדי → DIRTY → לא פורסם עד לריבייס.
