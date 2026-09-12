from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import cv2
import numpy as np
import shutil
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "../uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 회원 데이터베이스 {email: password}
users_db = {}  
# 계정별 책 목록 데이터베이스 {email: [ {title, author, image}, ... ] }
books_db = {}  

# 👑 여기에 운영자로 지정할 이메일들을 자유롭게 추가하면 돼!
ADMIN_EMAILS = ["yooneeo@gmail.com"]  # 예시: 네 실제 이메일로 변경 가능

@app.post("/api/signup")
async def signup(email: str = Form(...), password: str = Form(...)):
    if email in users_db:
        raise HTTPException(status_code=400, detail="이미 존재하는 이메일입니다.")
    users_db[email] = password
    books_db[email] = []
    return {"status": "success", "message": "회원가입이 완료되었습니다!"}

@app.post("/api/login")
async def login(email: str = Form(...), password: str = Form(...)):
    if email not in users_db or users_db[email] != password:
        raise HTTPException(status_code=400, detail="이메일 또는 비밀번호가 올바르지 않습니다.")
    
    # 등록된 운영자 이메일 목록에 포함되어 있는지 확인
    is_admin = (email in ADMIN_EMAILS)
    return {"status": "success", "message": "로그인 성공!", "email": email, "isAdmin": is_admin}

@app.get("/api/books")
async def get_books(email: str):
    user_books = books_db.get(email, [])
    return {"books": user_books}

# [운영자 전용] 전체 회원 및 서재 데이터 조회
@app.get("/api/admin/all-data")
async def get_all_data(email: str):
    if email not in ADMIN_EMAILS:
        raise HTTPException(status_code=403, detail="접근 권한이 없습니다.")
    
    all_users_info = []
    for user_email in users_db.keys():
        user_books = books_db.get(user_email, [])
        all_users_info.append({
            "email": user_email,
            "bookCount": len(user_books),
            "books": user_books
        })
    return {"users": all_users_info}

@app.post("/api/upload-page")
async def upload_page(
    email: str = Form(...),
    title: str = Form(...),
    author: str = Form(...),
    file: UploadFile = File(...)
):
    if email not in users_db:
        raise HTTPException(status_code=401, detail="인증되지 않은 사용자입니다.")

    file_path = os.path.join(UPLOAD_DIR, f"{email}_{file.filename}")
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # OpenCV 이미지 보정
    img = cv2.imread(file_path, cv2.IMREAD_GRAYSCALE)
    if img is not None:
        blurred = cv2.GaussianBlur(img, (5, 5), 0)
        _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        processed_path = os.path.join(UPLOAD_DIR, f"processed_{email}_{file.filename}")
        cv2.imwrite(processed_path, thresh)
    else:
        processed_path = file_path

    book_info = {
        "title": title,
        "author": author,
        "image": processed_path
    }
    
    if email not in books_db:
        books_db[email] = []
    books_db[email].append(book_info)

    return {
        "status": "success", 
        "message": f"'{title}' 책이 성공적으로 등록 및 보정되었습니다!",
        "book": book_info
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
