from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import cv2
import numpy as np
import base64
import json
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_FILE = "database.json"

# 데이터 파일 불러오기 또는 초기화
def load_data():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"users": {}, "books": {}}

# 데이터 파일 저장하기
def save_data(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

ADMIN_EMAILS = ["yooneeo@gmail.com"]

@app.post("/api/signup")
async def signup(email: str = Form(...), password: str = Form(...)):
    db = load_data()
    if email in db["users"]:
        raise HTTPException(status_code=400, detail="이미 존재하는 이메일입니다.")
    
    db["users"][email] = password
    db["books"][email] = []
    save_data(db)
    
    return {"status": "success", "message": "회원가입이 완료되었습니다!"}

@app.post("/api/login")
async def login(email: str = Form(...), password: str = Form(...)):
    db = load_data()
    if email not in db["users"] or db["users"][email] != password:
        raise HTTPException(status_code=400, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
    
    is_admin = (email in ADMIN_EMAILS)
    return {"status": "success", "message": "로그인 성공!", "email": email, "isAdmin": is_admin}

@app.post("/api/update-password")
async def update_password(email: str = Form(...), current_password: str = Form(...), new_password: str = Form(...)):
    db = load_data()
    if email not in db["users"] or db["users"][email] != current_password:
        raise HTTPException(status_code=400, detail="현재 비밀번호가 일치하지 않습니다.")
    
    db["users"][email] = new_password
    save_data(db)
    
    return {"status": "success", "message": "비밀번호가 성공적으로 변경되었습니다!"}

@app.get("/api/books")
async def get_books(email: str):
    db = load_data()
    user_books = db["books"].get(email, [])
    return {"books": user_books}

@app.get("/api/admin/all-data")
async def get_all_data(email: str):
    db = load_data()
    if email not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")
    
    all_users_info = []
    for user_email in db["users"].keys():
        user_books = db["books"].get(user_email, [])
        all_users_info.append({
            "email": user_email,
            "bookCount": len(user_books),
            "books": user_books
        })
    return {"users": all_users_info}

@app.delete("/api/books")
async def delete_book(email: str = Form(...), title: str = Form(...)):
    db = load_data()
    if email not in db["users"]:
        raise HTTPException(status_code=401, detail="인증되지 않은 사용자입니다.")
    
    user_books = db["books"].get(email, [])
    new_books = [book for book in user_books if book["title"] != title]
    
    if len(new_books) == len(user_books):
        raise HTTPException(status_code=404, detail="해당 책을 찾을 수 없습니다.")
    
    db["books"][email] = new_books
    save_data(db)
    
    return {"status": "success", "message": f"'{title}' 책이 삭제되었습니다."}


# --- 스캔 보정 관련 함수들 ---
def order_points(pts):
    rect = np.zeros((4, 2), dtype="float32")
    s = pts.sum(axis=1)
    rect[0] = pts[np.argmin(s)]
    rect[2] = pts[np.argmax(s)]
    diff = np.diff(pts, axis=1)
    rect[1] = pts[np.argmin(diff)]
    rect[3] = pts[np.argmax(diff)]
    return rect

def four_point_transform(image, pts):
    rect = order_points(pts)
    (tl, tr, br, bl) = rect
    widthA = np.sqrt(((br[0] - bl[0]) ** 2) + ((br[1] - bl[1]) ** 2))
    widthB = np.sqrt(((tr[0] - tl[0]) ** 2) + ((tr[1] - tl[1]) ** 2))
    maxWidth = max(int(widthA), int(widthB))
    heightA = np.sqrt(((tr[0] - br[0]) ** 2) + ((tr[1] - br[1]) ** 2))
    heightB = np.sqrt(((tl[0] - bl[0]) ** 2) + ((tl[1] - bl[1]) ** 2))
    maxHeight = max(int(heightA), int(heightB))
    dst = np.array([[0, 0], [maxWidth - 1, 0], [maxWidth - 1, maxHeight - 1], [0, maxHeight - 1]], dtype="float32")
    M = cv2.getPerspectiveTransform(rect, dst)
    return cv2.warpPerspective(image, M, (maxWidth, maxHeight))

def scan_book_image(image_bytes):
    np_arr = np.frombuffer(image_bytes, np.uint8)
    image = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    if image is None:
        return None
        
    orig = image.copy()
    H, W = image.shape[:2]
    total_area = H * W
    
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    edged = cv2.Canny(gray, 75, 200)
    
    cnts, _ = cv2.findContours(edged.copy(), cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    cnts = sorted(cnts, key=cv2.contourArea, reverse=True)[:5]
    
    screenCnt = None
    for c in cnts:
        area = cv2.contourArea(c)
        if area < total_area * 0.2 or area > total_area * 0.95:
            continue
            
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4:
            screenCnt = approx
            break
            
    if screenCnt is not None:
        try:
            warped = four_point_transform(orig, screenCnt.reshape(4, 2))
            if warped.shape[0] > 100 and warped.shape[1] > 100:
                _, encoded_img = cv2.imencode('.jpg', warped)
                return encoded_img.tobytes()
        except Exception:
            pass
            
    _, encoded_img = cv2.imencode('.jpg', orig)
    return encoded_img.tobytes()


@app.post("/api/upload-page")
async def upload_page(
    email: str = Form(...),
    title: str = Form(...),
    author: str = Form(...),
    file: UploadFile = File(...)
):
    db = load_data()
    if email not in db["users"]:
        raise HTTPException(status_code=401, detail="인증되지 않은 사용자입니다.")

    try:
        contents = await file.read()
        processed_bytes = scan_book_image(contents)
        
        if processed_bytes is not None:
            base64_str = base64.b64encode(processed_bytes).decode('utf-8')
            image_url = f"data:image/jpeg;base64,{base64_str}"
        else:
            image_url = ""

        book_info = {
            "title": title,
            "author": author,
            "image": image_url,
            "pages": [image_url]
        }
        
        if email not in db["books"]:
            db["books"][email] = []
        db["books"][email].append(book_info)
        
        save_data(db)

        return {
            "status": "success", 
            "message": f"'{title}' 책이 성공적으로 등록되었습니다!",
            "book": book_info
        }
    except Exception as e:
        print(f"업로드 에러 발생: {e}")
        raise HTTPException(status_code=500, detail=f"업로드 실패: {str(e)}")


@app.post("/api/add-page")
async def add_page(
    email: str = Form(...),
    title: str = Form(...),
    file: UploadFile = File(...)
):
    db = load_data()
    if email not in db["users"]:
        raise HTTPException(status_code=401, detail="인증되지 않은 사용자입니다.")

    user_books = db["books"].get(email, [])
    target_book = None
    for book in user_books:
        if book["title"] == title:
            target_book = book
            break

    if not target_book:
        raise HTTPException(status_code=404, detail="해당 책을 찾을 수 없습니다.")

    try:
        contents = await file.read()
        processed_bytes = scan_book_image(contents)
        
        if processed_bytes is not None:
            base64_str = base64.b64encode(processed_bytes).decode('utf-8')
            image_url = f"data:image/jpeg;base64,{base64_str}"
        else:
            image_url = ""

        if "pages" not in target_book:
            target_book["pages"] = [target_book.get("image", "")]
        
        target_book["pages"].append(image_url)
        save_data(db)

        return {"status": "success", "message": "페이지가 추가되었습니다!", "pages": target_book["pages"]}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"페이지 추가 실패: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
