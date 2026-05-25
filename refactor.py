import os

with open("app.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

new_lines = []
in_main_content = False

for i, line in enumerate(lines):
    # Fix imports
    if line.startswith("import logging"):
        new_lines.append(line)
        new_lines.append("import os\n")
        new_lines.append("from dotenv import load_dotenv\n")
        continue
    if line.startswith("from data_processor import"):
        new_lines.append("load_dotenv()\n")
        new_lines.append(line)
        continue

    # Identify the start of the presentation area
    if line.startswith("# ----------------- DATA PRESENTATION -----------------"):
        in_main_content = True
        new_lines.append("# ----------------- UI TABS -----------------\n")
        new_lines.append("tab1, tab2 = st.tabs([\"📊 Operations Dashboard\", \"📁 Data Management\"])\n\n")
        
        # Add Tab 2 content
        new_lines.append("with tab2:\n")
        new_lines.append("    st.header(\"Upload Job Orders\")\n")
        new_lines.append("    st.markdown(\"Upload a `.xls` or `.xlsx` file containing daily incoming and completed job orders.\")\n")
        new_lines.append("    uploaded_file = st.file_uploader(\"Choose an Excel file\", type=['xls', 'xlsx'])\n")
        new_lines.append("    if uploaded_file is not None:\n")
        new_lines.append("        try:\n")
        new_lines.append("            new_data = pd.read_excel(uploaded_file)\n")
        new_lines.append("            st.success(\"File successfully read!\")\n")
        new_lines.append("            st.dataframe(new_data, use_container_width=True)\n")
        new_lines.append("            if st.button(\"Append to Historical Data\"):\n")
        new_lines.append("                try:\n")
        new_lines.append("                    existing_data = pd.read_excel('Jobsdata.xlsx')\n")
        new_lines.append("                    combined_data = pd.concat([existing_data, new_data], ignore_index=True)\n")
        new_lines.append("                    combined_data.to_excel('Jobsdata.xlsx', index=False)\n")
        new_lines.append("                    st.success(\"✅ Data successfully appended to Jobsdata.xlsx!\")\n")
        new_lines.append("                    st.cache_data.clear()\n")
        new_lines.append("                except Exception as e:\n")
        new_lines.append("                    st.error(f\"Error appending data: {e}\")\n")
        new_lines.append("        except Exception as e:\n")
        new_lines.append("            st.error(f\"Error reading file: {e}\")\n\n")
        
        new_lines.append("with tab1:\n")
        
        # We also need to indent the # ----- DATA PRESENTATION line
        new_lines.append("    " + line)
        continue
        
    # Replace the broken secrets logic inside the loop if we're past it
    # We will just replace it line by line
    if "if not st.secrets.get(\"GEMINI_API_KEY\") and not os.environ.get(\"GEMINI_API_KEY\"):" in line:
        # We skip the next 11 lines
        pass
    
    if in_main_content:
        # Check if we are at the secrets logic to replace
        if line.strip() == "if not st.secrets.get(\"GEMINI_API_KEY\") and not os.environ.get(\"GEMINI_API_KEY\"):":
            new_lines.append("    " * 2 + "gemini_key = os.environ.get(\"GEMINI_API_KEY\")\n")
            new_lines.append("    " * 2 + "if not gemini_key:\n")
            new_lines.append("    " * 3 + "try:\n")
            new_lines.append("    " * 4 + "if st.secrets.get(\"GEMINI_API_KEY\"):\n")
            new_lines.append("    " * 5 + "gemini_key = st.secrets.get(\"GEMINI_API_KEY\")\n")
            new_lines.append("    " * 3 + "except Exception:\n")
            new_lines.append("    " * 4 + "pass\n")
            new_lines.append("    " * 2 + "if not gemini_key:\n")
            continue
        elif "if os.path.exists(\".env\"):" in line or "with open(\".env\") as f:" in line or "for line in f:" in line or "if \"GEMINI_API_KEY\" in line:" in line or "os.environ[\"GEMINI_API_KEY\"] = line.split(\"=\")[1].strip()" in line or "if not os.environ.get(\"GEMINI_API_KEY\"):" in line:
            # skip these lines
            continue
        elif line.strip() == "st.error(\"🔑 Gemini API Key is missing! Please configure it or add it to `.env` file.\")":
            new_lines.append("    " * 3 + "st.error(\"🔑 Gemini API Key is missing! Please configure it or add it to `.env` file.\")\n")
            continue
        elif line.strip() == "st.stop()":
            new_lines.append("    " * 3 + "st.stop()\n")
            continue
        
        # Default indentation
        if line == "\n":
            new_lines.append(line)
        else:
            new_lines.append("    " + line)
    else:
        new_lines.append(line)

with open("app.py", "w", encoding="utf-8") as f:
    f.writelines(new_lines)
print("Refactored app.py successfully!")
