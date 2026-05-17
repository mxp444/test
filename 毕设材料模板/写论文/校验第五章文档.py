# -*- coding: utf-8 -*-
from pathlib import Path
import win32com.client

path = str((Path(r"C:\Users\R9000P\Desktop\毕设") / "缪锡朋-毕业论文 (修复的) - 副本.doc").resolve())
word = win32com.client.Dispatch("Word.Application")
word.Visible = False
word.DisplayAlerts = 0
doc = word.Documents.Open(path, False, True)
text = doc.Content.Text
print("len=", len(text), "tables=", doc.Tables.Count)
print(text[:700].replace("\r", "⏎").replace("\x07", "¤"))
doc.Close(False)
word.Quit()
