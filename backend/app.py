from fastapi import FastAPI, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
import cv2
import numpy as np
import shutil
import os

app = FastAPI()

# 프론트엔드와 통신을 위한 CORS 설정
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = "../uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@app.post("/api/upload-page")
async def upload_page(file: UploadFile = File(...), title: str = Form(...)):
    # 1. 업로드된 파일 저장 경로 설정
    file_path = os.path.join(UPLOAD_DIR, file.filename)
    with open(file_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    # 2. OpenCV를 이용한 이미지 보정 (흑백 이진화 처리)
    img = cv2.imread(file_path, cv2.IMREAD_GRAYSCALE)
    blurred = cv2.GaussianBlur(img, (5, 5), 0)
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    processed_path = os.path.join(UPLOAD_DIR, f"processed_{file.filename}")
    cv2.imwrite(processed_path, thresh)

    return {
        "status": "success", 
        "message": f"'{title}' 책의 페이지가 성공적으로 보정되었습니다!",
        "original": file_path,
        "processed": processed_path
    }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app:app", host="0.0.0.0", port=8000, reload=True)