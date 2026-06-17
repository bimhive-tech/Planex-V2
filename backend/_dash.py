import os, time
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
import django; django.setup()
import fitz
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from apps.reports.models import Report
from apps.reports.services import build_report_context
from apps.reports.pdf import build_report_pdf
DL=os.path.expanduser("~/Downloads")
def sv(n):
    with open(os.path.join(DL,n),"rb") as f: return default_storage.save(f"tmp/{os.path.basename(n)}", ContentFile(f.read()))
def run():
    r=Report.objects.filter(report_number="52").first()
    keys=[sv("Screenshot 2024-04-18 032106.png"),sv("Screenshot 2024-04-18 032150.png"),sv("Screenshot 2024-04-18 032244.png")]
    ctx=build_report_context(r)
    ctx["photos"]=[{"image":k,"caption":""} for k in keys]
    data=build_report_pdf(r,ctx)
    doc=fitz.open(stream=data,filetype="pdf")
    # dashboard is early (after progress_overview ~ page 4-5)
    out="_dc"; os.makedirs(out,exist_ok=True)
    for i in range(3,7):
        doc.load_page(i).get_pixmap(dpi=90).save(os.path.join(out,f"p{i}.png"))
    for k in keys: default_storage.delete(k)
    print("OK pages:", doc.page_count)
for i in range(1,16):
    try:
        print(f"=={i}==",flush=True); run(); break
    except Exception as e:
        import traceback; traceback.print_exc(); time.sleep(5)
