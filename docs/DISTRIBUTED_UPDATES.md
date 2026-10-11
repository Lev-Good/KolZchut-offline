# מודל העדכונים המבוזר — KolZchut-offline

## מטרה
מספר משתמשים מורשים יכולים ללחוץ "עדכן מאגר" ולשלוח עדכון מהמחשב המקומי
שלהם — בלי תלות במחשב של הפרויקט — והעדכון עובר בדיקות אוטומטיות
ומיזוג לגרסה הרשמית ב-GitHub Releases.

## ארכיטקטורה

```
contributor computer            GitHub CI (pr-check.yml)          end user
  kolzchut_contribute.py          1. verification scripts
  0. base up to date? (abort      from master (never from the PR)
     if origin/master moved)      2. integrity + index + pages
  1. local delta sync            3. content filter (real run,
  2. content filter                  must be a no-op)
  3. portal rebuild              4. deletions + sync failures
  4. local verify (aborts)       5. anomalous size vs master
  5. branch + commit                 ↓ all green
  6. push + PR + label          auto-merge.yml (write access)
                                  6. content-only guard
                                  7. merge (squash) unless master moved
                                  8. dispatch "Build release ..."
                                     ↓
                                 Release ZIP published
```

## אבטחה והרשאות

### מה מותר למעדכנים מורשים
- **דחיפה לענף ייעודי בלבד** (`sync/auto-update-<date>-<id>`).
- לפתוח PR עם תווית `auto-merge-candidate`.
- **אין דחיפה ישירה ל-master** — הענף מוגן ב-Branch Protection.

### הזדהות
- אין אסימונים משותפים בקוד.
- כל מעדכן משתמש בחשבון GitHub האישי שלו (`gh auth login`).
- ההרשאה המינימלית שמאפשרת דחיפת ענף היא `Write` כ-collaborator. את master היא
  לא פותחת — Branch Protection חוסם דחיפות ישירות (כולל למנהלים).

### הפרדת אמון (trust boundary)
- כל סקריפטי האימות (`kolzchut_verify.py`, `kolzchut_remove_content.py`)
  נלקחים מ-**master** בלבד. PR תורם **נתוני ארכיון** בלבד.
- ל-job הבדיקות אין הרשאות כתיבה (`contents: read`). התוכן הנבדק נקרא, לא מורץ.
- שלב המיזוג והפרסום חי ב-`auto-merge.yml` (הרשאות כתיבה), שרץ רק אחרי
  שהבדיקות הסתיימו בהצלחה.
- **ההגנה הקובעת:** `auto-merge` ממזג רק PR שנוגע ב-`kolzchut_out/**` ו-`docs/**`.
  PR שנוגע בסקריפטים, ב-workflows או בקוד מדווח "אוטו-מיזוג דולג" וממתין למיזוג אנושי.
  זו הבקרה הקובעת ולא `pr-check`, כי **עבור אירועי `pull_request` GitHub מריץ את קובץ
  ה-workflow מתוך ה-PR** — כך ש-PR יכול, עקרונית, להחליש את הבדיקות שלו. PR שתוכן
  בלבד אינו יכול לשנות את השער, כי שינוי כזה מוציא אותו מכלל הזכאות לאוטו-מיזוג.
- **בדיקת טריות:** המיזוג מתבצע רק אם ה-SHA של הריצה שהסתיימה בהצלחה זהה ל-head
  הנוכחי של ה-PR (כדי לא למזג תוכן שנבדק בגרסה קודמת).
- **Bootstrap-safe:** `pr-check.yml` משתמש בנתיבי ברירת מחדל וב-`--baseline <ref>`
  בלבד, כדי לעבוד גם עם סקריפטי master וגם אחרי המיזוג.

### הגנת master (נכון ל-2026-10-12)
`required_status_checks`: strict, context `verify` · `enforce_admins: true` ·
`required_linear_history: true` (squash בלבד) · force-push ומחיקות חסומים.

## טיפול במצבים קריטיים

### עדכון חלקי או כושל
- `kolzchut_contribute.py` עוצר **לפני** קומיט אם `delta.json` מדווח `failed > 0`
  (הכשלים ממתינים ב-`retry_queue.json`).
- `kolzchut_verify.py` רץ מקומית; כשל עוצר לפני דחיפה.
- ב-CI: בדיקות אינדקס/דפים/מחיקות/גודל, ואכיפת המסנן — כשל חוסם את המיזוג.

### התנגשויות בין מעדכנים
- **לפני הסנכרון:** אם `origin/master` אינו כלול ב-HEAD, הסקריפט עוצר ומבקש
  `git pull --ff-only` — כדי שהדלתא לא תיגזר מבסיס מיושן.
- **בזמן המיזוג:** אם `mergeStateStatus` הוא `DIRTY`, המיזוג לא מתבצע; מופקת
  תגובה ב-PR שמבקשת הרצה מחדש.
- **בין השניים:** אם master זז אחרי ההרצה, Branch Protection (strict) דוחה את
  המיזוג, וה-workflow מדווח על כך ב-PR.

### שמירה על הגרסה האחרונה התקינה
- אין פרסום כשיש כישלון — ה-Release הקודם ממשיך לעמוד.
- כל כשל מדווח כתגובה על ה-PR ועם סיכום מפורט ב-job summary של הריצה.
- ה-Release מופעל רק אחרי מיזוג מוצלח (עם 3 ניסיונות חוזרים).

## בדיקות

### CI בזמן PR (`pr-check.yml`)
| בדיקה | מה נבדק | חוסם? |
|---|---|---|
| אינדקס | סכימה, slug, status, קיום קובץ לכל `status=ok` | כן |
| יתומים/כפילויות | קבצים ללא רשומה, שני כותרים לאותו slug | כן |
| שלמות HTML | ללא `script/img/iframe/video/audio/object/embed` (דגימה) | כן |
| קישורים פנימיים | יחס קישורים שבורים — **מידע בלבד** (ארכיון חלקי) | לא |
| מחיקות | >1% מהארכיון בריצה אחת | כן |
| כשלי סנכרון | `delta.json counts.failed > 0` | כן |
| שינוי חריג בגודל | ±200 / +2000 דפים מול `master`; ה-CI ממטריאליזציה את האינדקס מ-Git LFS ומוודא שהוא נפרס ל-JSON | כן |
| מסנן תוכן | המסנן האמיתי רץ על **כל** הדפים; חייב להיות no-op | כן |
| רגרסיית השער | 27 בדיקות שמריצות את הקוד האמיתי (סינון, מחיקות, גודל, baseline, אמון) | כן |

### חבילת הרגרסיה של השער (`tests/test_archive_gate.py`)
השער נאכף ע"י חבילה קבועה, שמריצה את **הקוד האמיתי** ולא העתק שלו:
סקריפטים מהריפו, והבלוקים שמוטמעים ב-workflows — נחלצים מהקובץ בזמן ריצה.
חילוץ ולא העתקה: שינוי שמסיר הגנה מפיל בדיקה במקום לעבור בשקט.

| קבוצה | מה נאכף |
|---|---|
| שער הסינון | ארכיון שלא סונן נחסם; ארכיון מסונן עובר (חייב להיות no-op) |
| שער המחיקות | `failed > 0` חוסם; מחיקה של יותר מ-1% חוסמת; `delta.json` חסר אינו שגיאה |
| שער הגודל | shrink/grow חריגים מהווים שגיאה; בתוך המגבלות מדווח בדוח ה-JSON |
| baseline | ref לא-קריא / קובץ חסר מחייבים `exit 1` עם שגיאה בדוח; ללא baseline אין בדיקת גודל |
| פלט | `stdout` נשאר JSON טהור (אזהרות ל-`stderr` בלבד) |
| הארכיון בריפו | מאומת (`skip` מפורש אם הקובץ הוא מצביע LFS לא-נפרס) |
| אמון | סקריפטים מ-master בלבד, bootstrap-safe, `actions: write`, תוכן-בלבד, ללא polling, טריות SHA |
| מלאי | `EXPECTED_GATE_TESTS` + ספירה — מחיקת בדיקה כדי "לתקן" אדום נתפסת |

הרצה:
```bash
python -m unittest discover -s tests -v        # 27 בדיקות, ~10 שניות
```
הרצה ב-CI: ב-`pr-check.yml` (אחרי staging, כדי שבדיקת הארכיון תראה תוכן אמיתי ולא
מצביע LFS) ובנפרד ב-`gate-tests.yml` על `push` ל-master עם נתיבים רלוונטיים.
שני המקומות אוכפים `Ran N tests` עם `N > 0` — "אפס בדיקות" אינו ירוק.

למה בנפרד על master: אירועי `pull_request` מריצים את ה-workflow מתוך ה-PR,
ו-auto-merge מסרב לשינויי תשתית — ולכן רק על master הקוד החדש של השער נבדק
בגרסה של עצמו.

### מה נבדק בפועל (ראיות)
- `python kolzchut_verify.py --baseline origin/master` — exit 0 על הארכיון הנוכחי,
  כולל `size_delta_vs_baseline` בדוח (לפני התיקון הבדיקה הזו נעדרה בשקט — baseline
  היה מצביע LFS שלא נפרס ל-JSON).
- PR #3: יצירת ענף → PR → `verify` ירוק → מיזוג ל-master.
- `kolzchut_local_sync.py --direct`: לפני התיקון `TypeError`; אחריו ריצה תקינה.
- חבילת הרגרסיה: 27/27 עוברות מקומית (~9 שניות, כולל אימות הארכיון האמיתי)
  ובדיקת מוטציות ב-7 רגרסיות מכוונות — כל אחת הפילה בדיקה בשם מפורש.

### תרחישי בדיקה
- עדכון רגיל עם דף אחד changed → merge + Release חדש.
- כשל בהורדת דף → עצירה מקומית + `delta.json failed > 0` ב-CI → אין פרסום.
- מחיקה חריגה של דפים → CI חוסם.
- master נע תוך כדי → אין מיזוג; נדרשת הרצה מחדש.
- מסנן לא הופעל מקומית → CI חוסם (המסנן משנה את התוכן).
- PR תשתית (נוגע בסקריפטים) → אוטו-מיזוג מדולג במכוון.

## מגבלות ידועות
- GitHub runners חסומים ע"י האתר (403), ולכן הסנכרון עצמו חייב לרוץ מהמחשב של
  מעדכן מורשה — המודל המבוזר הוא הפתרון לכך, לא עקיפה של החסימה.
- כ-4% מהקישורים הפנימיים מצביעים לדפים שאינם בארכיון החלקי; זה מדווח כ-warning
  ואינו חוסם.
