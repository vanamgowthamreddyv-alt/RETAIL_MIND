from fastapi import APIRouter,Form
import uuid
from datetime import date,datetime, timedelta
import qrcode
from fastapi.responses import HTMLResponse,FileResponse
import os
os.makedirs("temp",exist_ok=True)
Temp_Bills={}
def generate_bill_id(bill_details):
    bill_id=str(uuid.uuid4())
    Temp_Bills[bill_id]={"Bill Data":bill_details,"Expired_at":datetime.utcnow()+timedelta(minutes=100)}
    print(Temp_Bills)
    return bill_id
def generate_qr_path(bill_id:str):
    url=f"http://localhost:8000/scan/{bill_id}"
    img=qrcode.make(url)
    path=f"temp/{bill_id}.png"
    img.save(path)
    return path
router=APIRouter()
@router.post("/Generate/Bill")
async def bill_generte(Product:str=Form(...),Price:int=Form(...),Quantity:int=Form(...)):
    product_details={"Product":Product,"Price":Price,"Quantity":Quantity,"Total":Price*Quantity}
    bill_id=generate_bill_id(product_details)
    qr_path=generate_qr_path(bill_id)
    return {"qr_url":f"http://localhost:8000/qr/{bill_id}","bill_id":bill_id}
@router.get("/scan/{bill_id}")
async def get_bill(bill_id):
    bill=Temp_Bills.get(bill_id)
    if not bill:
        return HTMLResponse("<h3>Bill expired</h3>")
    print(bill["Expired_at"] < datetime.utcnow())
    if bill["Expired_at"] < datetime.utcnow():
        Temp_Bills.pop(bill_id, None)
        qr_path=f"temp/{bill_id}.png"
        if os.path.exists(qr_path):
            os.remove(qr_path)
        return HTMLResponse("<h3>Bill expired</h3>")

    return HTMLResponse(f"""
    <h2>Customer Bill</h2>
    <pre>{bill['Bill Data']}</pre>
    <p>This bill will auto-delete.</p>
    """)
@router.get("/qr/{bill_id}")
async def get_qr_image(bill_id):
    qr_path=f"temp/{bill_id}.png"
    if not os.path.exists(qr_path):
        return HTMLResponse("<h3>QR code not found</h3>")
    from fastapi.responses import FileResponse
    return FileResponse(qr_path,media_type="image/png")

