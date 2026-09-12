from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.staticfiles import StaticFiles
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

UPLOAD_DIR = "uploads"  # 상대 경로 수정 (서버 환경에 맞춤)
os.makedirs(UPLOAD_DIR, exist_ok=True)

# 📌 업로드된 이미지를 웹에서 불러올 수 있도록 스태틱 디렉토리 마운트
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

# 회원 데이터베이스 {email: password}
users_db = {}  
# 계정별 책 목록 데이터베이스 {email: [ {title, author, image}, ... ] }
books_db = {}  

# 운영자로 지정할 이메일들
ADMIN_EMAILS = ["sungkook@example.com"]  # 네 이메일로 변경 가능

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
    
    is_admin = (email in ADMIN_EMAILS)
    return {"status": "success", "message": "로그인 성공!", "email": email, "isAdmin": is_admin}

@app.post("/api/update-password")
async def update_password(email: str = Form(...), current_password: str = Form(...), new_password: str = Form(...)):
    if email not in users_db or users_db[email] != current_password:
        raise HTTPException(status_code=400, detail="현재 비밀번호가 일치하지 않습니다.")
    
    users_db[email] = new_password
    return {"status": "success", "message": "비밀번호가 성공적으로 변경되었습니다!"}

@app.get("/api/books")
async def get_books(email: str):
    user_books = books_db.get(email, [])
    return {"books": user_books}

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

    try:
        # 안전한 파일 이름 생성 (특수문자 방지)
        safe_filename = file.filename.replace(" ", "_")
        file_name = f"{email}_{safe_filename}"
        file_path = os.path.join(UPLOAD_DIR, file_name)
        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        # OpenCV 이미지 보정 안전 처리
        image_url = f"/uploads/{file_name}"
        try:
            img = cv2.imread(file_path, cv2.IMREAD_GRAYSCALE)
            if img is not None:
                blurred = cv2.GaussianBlur(img, (5, 5), 0)
                _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
                processed_file_name = f"processed_{file_name}"
                processed_path = os.path.join(UPLOAD_DIR, processed_file_name)
                cv2.imwrite(processed_path, thresh)
                image_url = f"/uploads/{processed_file_name}"
        except Exception as img_err:
            print(f"OpenCV 처리 중 예외 발생 (원본 이미지 유지): {img_err}")

        book_info = {
            "title": title,
            "author": author,
            "image": image_url
        }
        
        if email not in books_db:
            books_db[email] = []
        books_db[email].append(book_info)

        return {
            "status": "success", 
            "message": f"'{title}' 책이 성공적으로 등록되었습니다!",
            "book": book_info
        }
    except Exception as e:
        print(f"업로드 에러 발생: {e}")
        raise HTTPException(status_code=500, detail=f"업로드 실패: {str(e)}")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)
