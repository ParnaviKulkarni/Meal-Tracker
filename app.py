import streamlit as st
import google.genai as genai
import gspread
from google.oauth2.service_account import Credentials
import json
from datetime import datetime
from PIL import Image
import re
st.set_page_config(
    page_title="Parna's Meal Tracker", 
    page_icon="https://cdn-icons-png.flaticon.com/512/883/883806.png"
)

# --- 1. CONFIGURATION ---
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
SPREADSHEET_ID = st.secrets["SPREADSHEET_ID"]

client = genai.Client(api_key=GEMINI_API_KEY)
model = st.secrets["MODEL_STRING"]

@st.cache_resource
def get_google_sheet():
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds_dict = dict(st.secrets["gcp_service_account"])
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(SPREADSHEET_ID).sheet1

sheet = get_google_sheet()

def update_daily_totals(sheet, row_index):
    # Fetch all data in today's row and pad it to ensure it has 10 columns
    row_data = sheet.row_values(row_index)
    while len(row_data) < 10:
        row_data.append("")
        
    # Grab the text from the 4 Nutrition columns (Indices 2, 4, 6, 8)
    nutrition_texts = [row_data[2], row_data[4], row_data[6], row_data[8]]
    
    totals = {
        "Calories": 0, "Protein": 0, "Carbs": 0, "Fat": 0, "Fiber": 0, "Sugar": 0,
        "Sodium": 0, "Calcium": 0, "Iron": 0, "Potassium": 0, "Vit A": 0, "Vit C": 0
    }
    
    for text in nutrition_texts:
        if not text: continue
        
        cal = re.search(r'Calories:\s*([\d.]+)', text)
        pro = re.search(r'Protein:\s*([\d.]+)', text)
        carb = re.search(r'Carbs:\s*([\d.]+)', text)
        fat = re.search(r'Fat:\s*([\d.]+)', text)
        fib = re.search(r'Fiber:\s*([\d.]+)', text)
        sug = re.search(r'Sugar:\s*([\d.]+)', text)
        
        sod = re.search(r'Sodium:\s*~?([\d.]+)', text)
        calc = re.search(r'Calcium:\s*~?([\d.]+)', text)
        iron = re.search(r'Iron:\s*~?([\d.]+)', text)
        pot = re.search(r'Potassium:\s*~?([\d.]+)', text)
        vita = re.search(r'Vit A:\s*~?([\d.]+)', text)
        vitc = re.search(r'Vit C:\s*~?([\d.]+)', text)
        
        if cal: totals["Calories"] += float(cal.group(1))
        if pro: totals["Protein"] += float(pro.group(1))
        if carb: totals["Carbs"] += float(carb.group(1))
        if fat: totals["Fat"] += float(fat.group(1))
        if fib: totals["Fiber"] += float(fib.group(1))
        if sug: totals["Sugar"] += float(sug.group(1))
        
        if sod: totals["Sodium"] += float(sod.group(1))
        if calc: totals["Calcium"] += float(calc.group(1))
        if iron: totals["Iron"] += float(iron.group(1))
        if pot: totals["Potassium"] += float(pot.group(1))
        if vita: totals["Vit A"] += float(vita.group(1))
        if vitc: totals["Vit C"] += float(vitc.group(1))
        
    total_str = (
        f"Calories: {int(totals['Calories'])}\n"
        f"Protein: {totals['Protein']:.1f}g\n"
        f"Carbs: {totals['Carbs']:.1f}g\n"
        f"Fat: {totals['Fat']:.1f}g\n"
        f"Fiber: {totals['Fiber']:.1f}g\n"
        f"Sugar: {totals['Sugar']:.1f}g\n"
        f"--\n"
        f"Sodium: ~{int(totals['Sodium'])}mg\n"
        f"Calcium: ~{int(totals['Calcium'])}mg\n"
        f"Iron: ~{totals['Iron']:.1f}mg\n"
        f"Potassium: ~{int(totals['Potassium'])}mg\n"
        f"Vit A: ~{int(totals['Vit A'])}mcg\n"
        f"Vit C: ~{totals['Vit C']:.1f}mg"
    )
    # Update Column 10 (Total Nutrition) in the sheet
    sheet.update_cell(row_index, 10, total_str)

# --- 2. ROBUST DATE CHECKER ---
def get_today_row(sheet):
    now = datetime.now()
    # Google Sheets frequently reformats dates. We check for all common variations.
    possible_formats = [
        now.strftime("%B %d, %Y"),  # October 16, 2026
        now.strftime("%b %d, %Y"),  # Oct 16, 2026
        now.strftime("%m/%d/%Y"),   # 10/16/2026
        now.strftime("%-m/%-d/%Y"), # 10/16/2026 (no leading zeros)
        now.strftime("%Y-%m-%d")    # 2026-10-16
    ]
    
    # Grab all dates in Column A (Date Column)
    try:
        dates_col = sheet.col_values(1) 
    except Exception:
        return None
        
    for i, date_val in enumerate(dates_col):
        for fmt in possible_formats:
            if fmt in str(date_val):
                return i + 1  # +1 because Google Sheets rows are 1-indexed
    return None

# --- 3. UI ---
st.title("Parna's Macro Tracker")
tab1, tab2 = st.tabs(["📸 Log a Meal", "📊 Today's Macros"])

with tab1:
    st.header("Log a New Meal")
    meal_type = st.selectbox("Meal Type", ["Breakfast", "Midday Snack", "Lunch", "Dinner"])
    description = st.text_input("Short Description (e.g., 'Added 1 tsp olive oil')")
    uploaded_file = st.file_uploader("Upload Meal Photo", type=["jpg", "jpeg", "png"])
    
    if st.button("Analyze & Log"):
        if uploaded_file is not None:
            with st.spinner("Analyzing macros with Gemini..."):
                img = Image.open(uploaded_file)
                
                prompt = f"""
                Analyze this meal image. The user also noted: '{description}'.
                Calculate estimated macros (Calories, Protein, Carbs, Fat, Fiber, Sugar) and key micros (Sodium, Calcium, Iron, Potassium, Vitamin A, Vitamin C).
                Return ONLY a raw JSON object with this exact structure:
                {{"food_description": "String describing the meal components",
                  "nutrition_text": "Calories: X\\nProtein: Xg\\nCarbs: Xg\\nFat: Xg\\nFiber: Xg\\nSugar: Xg\\n--\\nSodium: Xmg\\nCalcium: Xmg\\nIron: Xmg\\nPotassium: Xmg\\nVit A: Xmcg\\nVit C: Xmg"}}
                """
                
                try:
                    response = client.model.generate_content(model=model,contents=[prompt, img])
                    result_text = response.text.strip().replace('```json', '').replace('```', '')
                    nutrition_data = json.loads(result_text)
                    
                    st.success("Meal Analyzed! Logging to Google Sheets...")
                    
                    row_index = get_today_row(sheet)
                    
                    col_map = {
                        "Breakfast": (2, 3), 
                        "Midday Snack": (4, 5), 
                        "Lunch": (6, 7), 
                        "Dinner": (8, 9)
                    }
                    food_col, nut_col = col_map[meal_type]
                    
                    if row_index:
                        sheet.update_cell(row_index, food_col, nutrition_data["food_description"])
                        sheet.update_cell(row_index, nut_col, nutrition_data["nutrition_text"])
                        # Automatically calculate and update totals
                        update_daily_totals(sheet, row_index)
                    else:
                        new_row = [datetime.now().strftime("%B %d, %Y")] + [""] * 9
                        sheet.append_row(new_row)
                        new_row_index = len(sheet.col_values(1))
                        sheet.update_cell(new_row_index, food_col, nutrition_data["food_description"])
                        sheet.update_cell(new_row_index, nut_col, nutrition_data["nutrition_text"])
                        # Automatically calculate and update totals for the new row
                        update_daily_totals(sheet, new_row_index)
                        st.info("Created a new row for today.")
                        
                    st.balloons()
                    st.write(nutrition_data["food_description"])
                    st.text(nutrition_data["nutrition_text"])
                    
                except Exception as e:
                    st.error(f"Error: {e}")
        else:
            st.warning("Please upload a photo first!")

with tab2:
    st.header("Today's Macros")
    with st.spinner("Loading and calculating today's totals..."):
        row_index = get_today_row(sheet)
        
        if row_index:
            # 1. Force a recalculation to catch any previously uncalculated meals
            #update_daily_totals(sheet, row_index)
            
            # 2. Fetch the newly updated row data
            row_data = sheet.row_values(row_index)
            
            # 3. Display the Total Nutrition column
            total_nutrition = row_data[9] if len(row_data) >= 10 and row_data[9] else "Totals not calculated yet."
            
            st.subheader("Nutrition for Today")
            st.text(total_nutrition)
        else:
            st.info("No meals logged for today yet! Go to the 'Log a Meal' tab to start.")
        
        sheet_url = f"https://docs.google.com/spreadsheets/d/{SPREADSHEET_ID}/view"
        st.link_button("📝 Open Google Sheet", sheet_url)
