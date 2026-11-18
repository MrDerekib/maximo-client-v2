"""Excel-friendly plain text and safe HTML for visible table rows."""
import csv
from html import escape
from io import StringIO
from PySide6.QtCore import QMimeData


def row_copy_mime(table, rows):
    rows = sorted({row for row in rows if 0 <= row < table.rowCount() and not table.isRowHidden(row)})
    if not rows:
        return None
    header = table.horizontalHeader()
    columns = sorted((col for col in range(table.columnCount()) if not table.isColumnHidden(col)),
                     key=header.visualIndex)
    if not columns:
        return None
    captions = [table.horizontalHeaderItem(col).text() if table.horizontalHeaderItem(col) else '' for col in columns]
    values = [[table.item(row,col).text() if table.item(row,col) else '' for col in columns] for row in rows]
    text = StringIO(newline='')
    writer = csv.writer(text, delimiter='\t', lineterminator='\r\n')
    writer.writerow(captions);writer.writerows(values)
    def cell(value):
        return escape(value).replace('\r\n','\n').replace('\r','\n').replace('\n','<br>')
    html = '<table border="1" cellspacing="0" cellpadding="4"><thead><tr>'
    html += ''.join('<th>'+cell(value)+'</th>' for value in captions)+'</tr></thead><tbody>'
    html += ''.join('<tr>'+''.join('<td>'+cell(value)+'</td>' for value in row)+'</tr>' for row in values)
    html += '</tbody></table>'
    mime = QMimeData();mime.setText(text.getvalue());mime.setHtml(html)
    return mime
