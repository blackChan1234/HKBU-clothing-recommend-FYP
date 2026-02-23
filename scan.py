import os

# --- 設定區域 (Configuration) ---

# 1. 你想要包含的檔案類型 (根據你的 Full-stack 專案設定)
ALLOWED_EXTENSIONS = {
    '.py',       # Python 后端
    '.js', '.jsx', # React 前端
    '.ts', '.tsx', # 如果你有用 TypeScript
    '.css',      # 樣式 (有的話可能有助於理解 UI)
    '.md',       # README 文件通常包含架構說明
    '.json',     # 設定檔 (如 package.json 可以讓 AI 知道你用了甚麼庫)
    '.sql'       # 資料庫結構
}

# 2. 絕對要忽略的資料夾 (這是最重要的一步，避免檔案過大)
IGNORE_DIRS = {
    'node_modules',  # React 依賴包 (超大，絕對不要)
    '__pycache__',   # Python 快取
    '.git',          # Git 版本控制
    '.venv', 'venv', # Python 虛擬環境
    '.idea', '.vscode', # IDE 設定
    'dist', 'build', 'coverage', # 編譯後的檔案
    'assets', 'images','IDM-VTON' # 圖片通常不需要轉成文字
}

# 3. 特殊要忽略的檔案
IGNORE_FILES = {
    'package-lock.json', # 太長且無助於邏輯理解
    'yarn.lock',
    '.DS_Store'          # Mac 系統檔
}

OUTPUT_FILENAME = "full_project_code_for_gemini.txt"

def combine_files(start_path):
    print(f"🚀 開始掃描資料夾: {start_path} ...")
    
    with open(OUTPUT_FILENAME, 'w', encoding='utf-8') as outfile:
        # 寫入一個開頭說明，告訴 Gemini 這是什麼
        outfile.write("Project Codebase Structure and Content\n")
        outfile.write("=====================================\n\n")

        # os.walk 會自動鑽進每一層資料夾
        for root, dirs, files in os.walk(start_path):
            # 修改 dirs 列表，讓 os.walk 略過我們不想看的資料夾 (inplace modification)
            dirs[:] = [d for d in dirs if d not in IGNORE_DIRS]

            for file in files:
                # 檢查檔案是否在忽略清單中
                if file in IGNORE_FILES:
                    continue

                # 檢查副檔名是否是我們要的
                _, ext = os.path.splitext(file)
                if ext.lower() in ALLOWED_EXTENSIONS:
                    file_path = os.path.join(root, file)
                    rel_path = os.path.relpath(file_path, start_path) # 取得相對路徑
                    
                    try:
                        with open(file_path, 'r', encoding='utf-8') as infile:
                            content = infile.read()
                            
                            # 這是給 Gem 看的格式，非常重要！
                            # 讓 AI 知道這段 code 屬於哪個檔案
                            outfile.write(f"\n{'='*60}\n")
                            outfile.write(f"FILE PATH: {rel_path}\n")
                            outfile.write(f"{'='*60}\n")
                            outfile.write(content)
                            outfile.write("\n\n")
                            
                            print(f"✅ 已加入: {rel_path}")
                            
                    except Exception as e:
                        print(f"❌ 無法讀取: {rel_path} (Error: {e})")

    print(f"\n✨ 完成！所有程式碼已合併至: {OUTPUT_FILENAME}")
    print(f"📁 檔案大小: {os.path.getsize(OUTPUT_FILENAME) / 1024:.2f} KB")

if __name__ == "__main__":
    # 執行腳本，掃描當前目錄
    current_directory = os.getcwd()
    combine_files(current_directory)