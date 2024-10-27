import streamlit as st
import sqlite3
import pandas as pd
import os
import tempfile
import shutil
import tabula
import PyPDF2
import openpyxl
from pathlib import Path

def pdf_to_excel(pdf_path, output_path):
    """
    Convert PDF to Excel file
    
    Parameters:
    pdf_path (str): Path to PDF file
    output_path (str): Path for output Excel file
    
    Returns:
    str: Path to created Excel file
    """
    try:
        # Read PDF file
        tables = tabula.read_pdf(pdf_path, pages='all', multiple_tables=True)
        
        # Create Excel writer object
        with pd.ExcelWriter(output_path, engine='openpyxl') as writer:
            # If no tables were found, try to extract text and create a single table
            if not tables:
                pdf_reader = PyPDF2.PdfReader(pdf_path)
                text_data = []
                
                for page in pdf_reader.pages:
                    text = page.extract_text()
                    if text:
                        # Split text into lines and create a simple table
                        lines = [line.strip() for line in text.split('\n') if line.strip()]
                        text_data.extend(lines)
                
                if text_data:
                    df = pd.DataFrame({'Content': text_data})
                    df.to_excel(writer, sheet_name='Sheet1', index=False)
            else:
                # Write each table to a different sheet
                for i, table in enumerate(tables):
                    if not table.empty:
                        sheet_name = f'Sheet{i+1}'
                        table.to_excel(writer, sheet_name=sheet_name, index=False)
        
        return output_path
    except Exception as e:
        raise Exception(f"Error converting PDF to Excel: {str(e)}")

def get_excel_sheets(file):
    """Get list of sheet names from Excel file"""
    return pd.ExcelFile(file).sheet_names

def excel_to_database(excel_file, database_name, sheet_names=None):
    """
    Convert Excel file to SQLite database.
    
    Parameters:
    excel_file: File object or path
    database_name (str): Name for the SQLite database
    sheet_names (list, optional): List of sheet names to convert
    
    Returns:
    tuple: (database_path, conversion_info)
    """
    conversion_info = []
    
    # Create database connection
    conn = sqlite3.connect(database_name)
    
    try:
        # Read all sheets if sheet_names is None
        if sheet_names is None:
            excel_data = pd.read_excel(excel_file, sheet_name=None)
        else:
            excel_data = {sheet: pd.read_excel(excel_file, sheet_name=sheet) 
                         for sheet in sheet_names}
        
        # Convert each sheet to a table
        for sheet_name, df in excel_data.items():
            # Clean column names
            df.columns = [col.lower().replace(' ', '_').replace('-', '_') 
                         for col in df.columns]
            
            # Clean table name
            table_name = ''.join(char for char in sheet_name 
                               if char.isalnum() or char == '_').lower()
            
            # Write to database
            df.to_sql(table_name, conn, if_exists='replace', index=False)
            
            # Store conversion info
            info = {
                'sheet_name': sheet_name,
                'table_name': table_name,
                'rows': len(df),
                'columns': list(df.columns)
            }
            conversion_info.append(info)
    
    finally:
        conn.close()
    
    return database_name, conversion_info

def get_table_preview(database_path, table_name, rows=5):
    """Get preview of table contents"""
    conn = sqlite3.connect(database_path)
    try:
        df = pd.read_sql(f"SELECT * FROM {table_name} LIMIT {rows}", conn)
        return df
    finally:
        conn.close()

def main():
    st.set_page_config(page_title="File to SQLite Converter", layout="wide")
    
    st.title("PDF/Excel to SQLite Database Converter")
    st.write("Upload a PDF or Excel file and convert it to a SQLite database")
    st.info('The PDF file should contain a table', icon="ℹ")
    
    # File uploader
    uploaded_file = st.file_uploader(
        "Choose a file",
        type=['pdf', 'xlsx', 'xls'],
        help="Upload a PDF or Excel file"
    )
    
    if uploaded_file is not None:
        try:
            # Create temporary directory
            temp_dir = tempfile.mkdtemp()
            
            # Save uploaded file
            temp_input_path = os.path.join(temp_dir, uploaded_file.name)
            with open(temp_input_path, 'wb') as f:
                f.write(uploaded_file.getvalue())
            
            # Handle PDF conversion if necessary
            file_extension = Path(uploaded_file.name).suffix.lower()
            if file_extension == '.pdf':
                st.info("Converting PDF to Excel format...")
                with st.spinner("This may take a moment..."):
                    temp_excel_path = os.path.join(temp_dir, 'converted.xlsx')
                    temp_excel_path = pdf_to_excel(temp_input_path, temp_excel_path)
                st.success("PDF converted to Excel successfully!")
            else:
                temp_excel_path = temp_input_path
            
            # Get sheet names
            sheet_names = get_excel_sheets(temp_excel_path)
            
            st.write("### File Details")
            col1, col2 = st.columns(2)
            with col1:
                st.write(f"File name: {uploaded_file.name}")
                st.write(f"Number of sheets: {len(sheet_names)}")
            
            # Sheet selection
            st.write("### Sheet Selection")
            selected_sheets = st.multiselect(
                "Select sheets to convert (leave empty to convert all sheets)",
                options=sheet_names,
                default=None
            )
            
            if not selected_sheets:
                selected_sheets = None
                st.info("All sheets will be converted")
            
            # Database name input
            default_db_name = Path(uploaded_file.name).stem + ".db"
            db_name = st.text_input(
                "Enter database name",
                value=default_db_name,
                help="Enter the name for your SQLite database file"
            )
            
            # Convert button
            if st.button("Convert to Database"):
                try:
                    with st.spinner("Converting to SQLite database..."):
                        # Create database in temporary directory
                        temp_db_path = os.path.join(temp_dir, db_name)
                        
                        # Process the conversion
                        db_path, conversion_info = excel_to_database(
                            temp_excel_path,
                            temp_db_path,
                            selected_sheets
                        )
                        
                        # Display conversion results
                        st.success("Conversion completed successfully!")
                        
                        # If it was a PDF, offer Excel download too
                        if file_extension == '.pdf':
                            with open(temp_excel_path, 'rb') as f:
                                st.download_button(
                                    label="Download Converted Excel",
                                    data=f.read(),
                                    file_name="converted.xlsx",
                                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                    help="Download the intermediate Excel file"
                                )
                        
                        st.write("### Conversion Details")
                        for info in conversion_info:
                            with st.expander(f"Sheet: {info['sheet_name']}"):
                                st.write(f"Table name: {info['table_name']}")
                                st.write(f"Number of rows: {info['rows']}")
                                st.write(f"Columns: {', '.join(info['columns'])}")
                                
                                # Show data preview
                                st.write("Data Preview:")
                                preview_df = get_table_preview(temp_db_path, info['table_name'])
                                st.dataframe(preview_df)
                        
                        # Provide download link for database
                        with open(temp_db_path, 'rb') as f:
                            st.download_button(
                                label="Download SQLite Database",
                                data=f.read(),
                                file_name=db_name,
                                mime="application/x-sqlite3",
                                help="Click to download the converted database file"
                            )
                
                except Exception as e:
                    st.error(f"Error during conversion: {str(e)}")
                    st.write("Please check your file and try again.")
        
        except Exception as e:
            st.error(f"Error processing file: {str(e)}")
        
        finally:
            # Clean up temporary directory
            try:
                shutil.rmtree(temp_dir)
            except Exception:
                pass

if __name__ == "__main__":
    main()