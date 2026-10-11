# הרצה ועדכונים — מדריך מהיר

המצב האמיתי של הרשת מתועד ב-[README.md](README.md) וב-[docs/DECISIONS.md](docs/DECISIONS.md):
ה-API של כל-זכות חסום לרובוטים, ו-GitHub runners מקבלים **403** מכל נתיבי האתר.
לכן **אין** סנכרון יומי בענן — הסנכרון רץ מהמחשב של מעדכן מורשה.

## פעם אחת (התחלה)

```bash
pip install -r requirements.txt
python kolzchut_download.py          # הורדה מלאה ראשונית (~45 דק')
python kolzchut_build_portal.py --github-repo Lev-Good/KolZchut-offline
python kolzchut_release.py           # ZIP + manifest
```

## עדכון המאגר — המודל המבוזר (מומלץ)

כל מעדכן מורשה מריץ מהמחשב שלו:

```bash
python kolzchut_contribute.py            # סנכרון דלתא + branch + PR
python kolzchut_contribute.py --check    # בדיקה יבשה: מה ישתנה, בלי PR
```

מה קורה מאחורי הקלעים (ראו [docs/DISTRIBUTED_UPDATES.md](docs/DISTRIBUTED_UPDATES.md)):

1. **בדיקת עדכניות** — `origin/master` חייב להיות כלול ב-HEAD; אחרת הסקריפט עוצר
   ומבקש `git pull` (סנכרון על בסיס מיושן היה נדחה ע"י Branch Protection).
2. סנכרון דלתא מבוסס sitemap (מכבד Crawl-delay 5).
3. המסנן `kolzchut_remove_content.py --default-charedi-list`.
4. בניית הפורטל.
5. אימות מקומי `kolzchut_verify.py` — כשל עוצר לפני שנדחף משהו.
6. קומיט לענף `sync/auto-update-<date>-<id>`, דחיפה, ופתיחת PR עם התווית
   `auto-merge-candidate`.

לאחר מכן GitHub Actions עושה את השאר:
`pr-check` מאמת → בהצלחה `auto-merge` ממזג ומפעיל את בניית ה-Release.

`kolzchut_local_sync.py` הוא עטיפה דקה: ברירת המחדל מפנה ל-`kolzchut_contribute.py`.
המסלול הישן (דחיפה ישירה ל-master, עוקף PR/CI) נשאר כ-`--direct` ואינו מומלץ.

### מתי העדכון לא ייכנס?

| מצב | מה קורה |
|---|---|
| דף נכשל בהורדה (`failed > 0`) | הסקריפט לא פותח PR; הגרסה הקודמת נשארת באוויר |
| `master` התקדם מאז תחילת הסנכרון | נדרשת הרצה מחדש (`git pull` ואז contribute) |
| מחיקה חריגה (>1% מהארכיון) | `pr-check` חוסם את המיזוג |
| המסנן לא הופעל מקומית | `pr-check` מריץ את המסנן האמיתי וחוסם (חייב להיות no-op) |
| `origin/master` לא נגיש ל-baseline | הבדיקה נכשלת בקול במקום להתבטל בשקט |

## סינון תכנים (מנהל)

```bash
python kolzchut_remove_content.py --default-charedi-list
python kolzchut_remove_content.py --remove-pages "שם דף"
python kolzchut_remove_content.py --blank-pages "שם דף"
python kolzchut_remove_content.py --remove-words "מילה"
```

## בדיקת השער מקומית

```bash
python -m unittest discover -s tests -v
```

[tests/test_archive_gate.py](tests/test_archive_gate.py) מריץ את הקוד האמיתי של השער:
אכיפת המסנן, מחיקות וכשלי סנכרון, שינוי חריג בגודל מול baseline, baseline לא-קריא
כשגיאה קשה, ואינווריאנטים של אמון. אותה חבילה רצה בכל PR וגם על master —
הרצה מקומית לפני דחיפה חוסכת סבב CI.

## פרסום Release

בניית ה-Release רצה בענן מתוך `kolzchut_out/` שנמצא כבר בריפו (LFS) — בלי לפנות
לכל-זכות, ולכן עובדת גם כשה-site חוסם runners:

```bash
gh workflow run "Build release from committed archive"
```

במסלול המבוזר אין צורך להריץ זאת ידנית: `auto-merge` מפעיל את ה-workflow הזה
אחרי מיזוג מוצלח.

## פרסום Release ראשון באופן ידני

```bash
gh release create v20261011 releases/kolzchut_v20261011.zip \
  --title "ארכיון כל זכות v20261011" \
  --notes "ארכיון מלא של דפי כל-זכות לשימוש אופליין. רישיון CC-BY-NC-SA-2.5-IL."
```

## פתרון תקלות

| סימפטום | סיבה / פתרון |
|---|---|
| `gh: Not authenticated` | `gh auth login` (זהות אישית — אין אסימונים משותפים) |
| "base branch is stale" | `git checkout master && git pull --ff-only` ואז הרצה מחדש |
| ה-PR נפתח אבל לא ממוזג | קראו את הסיכום ב-Actions (job summary) ואת תגובת ה-bot ב-PR |
| "auto-merge skipped by design" | ה-PR נוגע בקבצי תשתית (לא רק תוכן) — נדרש מיזוג אנושי |
| ריצה יבשה | `python kolzchut_contribute.py --check` |
| רוצים לבדוק את השער לפני דחיפה | `python -m unittest discover -s tests -v` |
