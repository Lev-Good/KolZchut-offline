# הרצה ועדכונים — מדריך מהיר

## פעם אחת (התחלה)

```bash
pip install requests beautifulsoup4
python kolzchut_download.py          # הורדת כל 7,358 הדפים (~45 דק')
python kolzchut_build_portal.py --github-repo Lev-Good/KolZchut-offline
python kolzchut_release.py           # ZIP + manifest
```

## עדכון יומי (אוטומטי ב-GitHub Actions)

GitHub Actions רץ פעם ביום 06:00 שעון ישראל:
- בודק לכל-זכות מה השתנה ביום האחרון (`recentchanges`).
- מוריד רק דפים שהשתנו ומפרסם Release חדש אם יש.

משתמש-קצה: פותח את הארכיון המקומי → דף הבית מציג הודעה "קיימת גרסה חדשה" אם יש
→ קישור להורדת ZIP החדש מ-GitHub Releases.

## סינון תכנים (מנהל)

```bash
python kolzchut_remove_content.py --default-charedi-list
python kolzchut_remove_content.py --remove-pages "שם דף"
python kolzchut_remove_content.py --blank-pages "שם דף"
python kolzchut_remove_content.py --remove-words "מילה"
```

## פרסום Release ראשון באופן ידני

```bash
gh release create v20261011 releases/kolzchut_v20261011.zip \
  --title "ארכיון כל זכות v20261011" \
  --notes "ארכיון מלא של 7,358 דפי כל-זכות לשימוש אופליין. רישיון CC-BY-NC-SA-2.5-IL."
```
