from openpyxl import Workbook
from openpyxl.styles import Font

def write_validation_excel(rows, file_path):
    wb = Workbook()
    ws = wb.active
    ws.title = "Validation"

    headers = ["IP", "Command", "Status", "Errors"]
    ws.append(headers)

    for col in range(1, 5):
        ws.cell(row=1, column=col).font = Font(bold=True)

    for r in rows:
        ws.append([
            r["ip"],
            r["command"],
            r["status"],
            "\n".join(r.get("errors", []))
        ])

    wb.save(file_path)
