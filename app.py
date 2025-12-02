import streamlit as st
import pandas as pd
import re
from io import BytesIO
from pypdf import PdfReader

# --- Core Utility Functions ---

def extract_text_from_pdf(uploaded_file):
    """Extracts raw text content from a PDF file object."""
    try:
        pdf_reader = PdfReader(uploaded_file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n\n"
        return text
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
        return None

def parse_payroll_data(raw_text):
    """
    Parses the raw text to extract Employee Name, Date, and Gross Remuneration,
    and calculates the total remuneration per employee.
    """
    if not raw_text:
        return pd.DataFrame()

    # Regex for Employee Name (Assuming names follow the pattern: Lastname, Firstname MiddleName)
    # The pattern should be broad to catch variations like Kapamba, Kayoka Bovick
    name_pattern = re.compile(r"^([A-Z][a-z]+(?:-\s?[A-Z][a-z]+)?, [A-Z].*)$", re.MULTILINE)

    # Regex for Data Line (CSV-like structure)
    # This pattern captures the date (Field 1) and the Gross Remuneration (Field 9)
    # It relies on splitting the line by the quoted separator `","` or unquoted `,`
    # Field indices: 1-Date, 9-Gross Remuneration
    date_pattern = re.compile(r'"(\d{4}-\d{2}-\d{2})"')

    all_data = []
    current_employee = "Unknown Employee"
    
    # Clean up the text: replace multiple newlines with a single space to normalize data rows
    # and split the text into lines for iterative processing.
    # We must be careful not to merge names and data lines.
    
    lines = raw_text.split('\n')
    
    # Process lines, aggregating data
    for line in lines:
        line = line.strip()
        
        # 1. Check for Employee Name
        name_match = name_pattern.match(line)
        if name_match:
            current_employee = name_match.group(1).strip()
            continue

        # 2. Check for Data Line
        date_match = date_pattern.match(line)
        if date_match:
            # Normalize and split the line by comma, trying to handle quotes
            # A simple approach: remove quotes and split by comma to get fields
            
            # Remove the quotes for simpler splitting, then split by comma
            cleaned_line = line.replace('"', '').replace('\n', '').strip()
            
            # The structure appears to be: Date, Basic Salary, Loan Repayment, Tax (PAYE), UIF - Employee, SDL - Employer, UIF - Employer, Gross Remuneration Taxable, Gross Remuneration, Nett Pay
            # Gross Remuneration is the 9th column (index 8)
            fields = [f.strip() for f in cleaned_line.split(',') if f.strip()]
            
            # Since the number of empty fields (like Loan Repayment, Tax PAYE) varies,
            # we count backward from the end where the columns seem to be more consistent:
            # [..., Gross Remuneration, Nett Pay]
            # Gross Remuneration is the second to last main figure.
            
            if len(fields) >= 10:
                date = fields[0]
                # Gross Remuneration is the 9th element (index 8) in the 10-column set
                gross_remuneration = fields[8] 
                
                # Check for R currency symbol and valid date format
                if re.match(r"R\s*[\d,]+\.\d{2}", gross_remuneration) and re.match(r"\d{4}-\d{2}-\d{2}", date):
                    all_data.append({
                        "Employee Name": current_employee,
                        "Date": date,
                        "Gross Remuneration": gross_remuneration
                    })
                
    # Create DataFrame
    df = pd.DataFrame(all_data)

    if df.empty:
        return df

    # --- Data Cleaning and Aggregation ---
    
    # Convert 'Gross Remuneration' to numeric for calculation
    # Remove 'R', commas, and convert to float
    def clean_currency(value):
        try:
            return float(value.replace('R', '').replace(',', '').strip())
        except:
            return 0.0

    df['Gross Remuneration Value'] = df['Gross Remuneration'].apply(clean_currency)

    # Calculate Totals
    totals = df.groupby('Employee Name')['Gross Remuneration Value'].sum().reset_index()
    totals.columns = ['Employee Name', 'Total Gross Remuneration']
    
    # Format the total column back to currency
    totals['Total Gross Remuneration'] = totals['Total Gross Remuneration'].map('R {:,.2f}'.format)

    # Prepare Final Output
    final_df = df[['Employee Name', 'Date', 'Gross Remuneration']].copy()

    # Append totals to the end of each employee's records
    final_records = []
    
    for name in final_df['Employee Name'].unique():
        employee_records = final_df[final_df['Employee Name'] == name]
        total_row = totals[totals['Employee Name'] == name].iloc[0]
        
        final_records.extend(employee_records.to_dict('records'))
        
        final_records.append({
            "Employee Name": f"TOTAL for {name}",
            "Date": "",
            "Gross Remuneration": total_row['Total Gross Remuneration']
        })

    return pd.DataFrame(final_records)

@st.cache_data
def convert_df_to_csv(df):
    """Converts the DataFrame to a CSV string for download."""
    return df.to_csv(index=False).encode('utf-8')

# --- Streamlit Application Layout ---

st.set_page_config(
    page_title="Payroll PDF to CSV Extractor",
    layout="centered",
    initial_sidebar_state="expanded"
)

st.title("💰 Payroll Data Extractor")
st.markdown("Upload your payroll PDF report to extract and summarize **Employee Name**, **Date**, and **Gross Remuneration** into a single CSV file.")

st.warning("⚠️ **Important:** This app is tailored for the specific CSV-like structure shown in your document snippet. Minor variations in your 30-page report might affect parsing accuracy.")

# File Uploader
uploaded_file = st.file_uploader(
    "Upload the PDF Payroll Report",
    type="pdf",
    accept_multiple_files=False,
    key="pdf_uploader"
)

if uploaded_file is not None:
    # Use st.spinner for a better UX while processing
    with st.spinner("Processing PDF and extracting data..."):
        # 1. Extract Text
        pdf_text = extract_text_from_pdf(uploaded_file)
        
        if pdf_text:
            # 2. Parse Data
            result_df = parse_payroll_data(pdf_text)
            
            if not result_df.empty:
                st.success("Extraction Complete! Data Ready for Review and Download.")
                
                # 3. Display Data
                st.subheader("Extracted and Summarized Data")
                st.dataframe(result_df, hide_index=True)
                
                # 4. Download Button
                csv_data = convert_df_to_csv(result_df)
                
                st.download_button(
                    label="Download Extracted Payroll Data as CSV",
                    data=csv_data,
                    file_name='payroll_summary.csv',
                    mime='text/csv',
                    type="primary"
                )
                
                st.markdown("---")
                st.info("The CSV includes the date records and a final 'TOTAL' row for each employee.")
            else:
                st.error("Could not find any matching payroll records. Please ensure the PDF structure exactly matches the provided snippet.")
        
# Instructions for Deployment
st.sidebar.header("Deployment Information")
st.sidebar.markdown("""
This is a Streamlit application, which is ideal for free deployment.

1.  **Save the file:** Save the code above as `app.py`.
2.  **Create a `requirements.txt` file:**
    ```text
    streamlit
    pandas
    pypdf
    ```
3.  **Upload to GitHub:** Create a new repository and upload `app.py` and `requirements.txt`.
4.  **Deploy:** Go to the [Streamlit Community Cloud](https://share.streamlit.io/) website, log in, and connect it to your GitHub repository to deploy the app for free.
""")

# Show raw text toggle (useful for debugging parsing)
if uploaded_file is not None and st.sidebar.checkbox("Show Raw Extracted Text (For Debugging)"):
    st.sidebar.subheader("Raw Text Output")
    st.sidebar.code(pdf_text[:10000]) # Limit output size
