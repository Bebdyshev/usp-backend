import pandas as pd
from fastapi import HTTPException
from io import BytesIO
import json
import re
from typing import Dict, List, Optional, Tuple, Any
import unicodedata

def normalize_name(name: str) -> str:
    """Normalize student name for consistent storage"""
    if not name or pd.isna(name):
        return ""
    
    # Convert to string and strip whitespace
    name = str(name).strip()
    
    # Unicode normalization
    name = unicodedata.normalize('NFKC', name)
    
    # Remove extra spaces between words
    name = re.sub(r'\s+', ' ', name)
    
    # Remove any trailing commas or periods
    name = name.rstrip('.,')
    
    return name

def validate_percentage(value: Any) -> Optional[float]:
    """Validate and convert percentage value"""
    if pd.isna(value) or value == "" or value is None:
        return None
    
    try:
        # Convert to float
        percent = float(value)
        
        # Validate range (0-100)
        if 0 <= percent <= 100:
            return percent
        else:
            return None
    except (ValueError, TypeError):
        return None

def calculate_predicted_score(
    monitoring_percent: Optional[float],
    current_quarters: List[Optional[float]],
    teacher_percent: Optional[float],
    weights: Dict[str, float] = None
) -> float:
    """
    Calculate predicted score based on available data
    New formula: 0.7 * avg(quarters) + 0.3 * teacher_percent
    """
    if weights is None:
        weights = {
            'current': 0.7,
            'teacher': 0.3
        }
    
    # Calculate average of available quarters
    valid_quarters = [q for q in current_quarters if q is not None]
    current_avg = sum(valid_quarters) / len(valid_quarters) if valid_quarters else 0.0
    
    # Use provided values or 0.0 as fallback
    teacher = teacher_percent if teacher_percent is not None else 0.0
    
    # Calculate weighted predicted score: 70% quarters average + 30% teacher prediction
    predicted = (
        weights['current'] * current_avg +
        weights['teacher'] * teacher
    )
    
    return round(predicted, 2)

def parse_excel_grades(
    file_content: bytes,
    expected_columns: Dict[str, List[str]] = None
) -> Dict[str, Any]:
    """
    Parse Excel file for grade upload
    
    Expected columns (case-insensitive, flexible matching):
    - ФИО / Name / Student Name
    - Мониторинг / Monitoring / Monitoring %
    - Q1 / Четверть 1 / Quarter 1
    - Q2 / Четверть 2 / Quarter 2  
    - Q3 / Четверть 3 / Quarter 3
    - Q4 / Четверть 4 / Quarter 4
    - Учитель / Teacher / Teacher %
    """
    
    if expected_columns is None:
        expected_columns = {
            'name': ['фио', 'имя', 'name', 'student', 'студент', 'ученик'],
            'monitoring': ['мониторинг', 'monitoring', 'мон', 'mon'],
            'q1': ['q1', 'четверть 1', 'quarter 1', '1 четверть', 'ч1'],
            'q2': ['q2', 'четверть 2', 'quarter 2', '2 четверть', 'ч2'],
            'q3': ['q3', 'четверть 3', 'quarter 3', '3 четверть', 'ч3'],
            'q4': ['q4', 'четверть 4', 'quarter 4', '4 четверть', 'ч4'],
            'teacher': ['учитель', 'teacher', 'преподаватель', 'препод']
        }
    
    try:
        # Read Excel file
        excel_data = BytesIO(file_content)
        df = pd.read_excel(excel_data, sheet_name=0, header=0)
        
        if df.empty:
            raise HTTPException(status_code=400, detail="Excel file is empty")
        
        # Normalize column names for matching
        df.columns = df.columns.astype(str)
        normalized_columns = {col: col.lower().strip() for col in df.columns}
        
        # Find column mappings
        column_mapping = {}
        
        for field, possible_names in expected_columns.items():
            found = False
            for col_name, normalized in normalized_columns.items():
                if any(possible in normalized for possible in possible_names):
                    column_mapping[field] = col_name
                    found = True
                    break
            
            if not found and field == 'name':
                # Name column is required
                raise HTTPException(
                    status_code=400, 
                    detail=f"Required column not found: {field}. Available columns: {list(df.columns)}"
                )
        
        # Parse student data
        students_data = []
        warnings = []
        errors = []
        
        for index, row in df.iterrows():
            try:
                # Skip empty rows
                if row.isna().all():
                    continue
                
                # Get student name (required)
                student_name = normalize_name(row.get(column_mapping.get('name', '')))
                if not student_name:
                    warnings.append(f"Row {index + 2}: Missing student name, skipped")
                    continue
                
                # Parse percentages
                monitoring_percent = validate_percentage(row.get(column_mapping.get('monitoring')))
                teacher_percent = validate_percentage(row.get(column_mapping.get('teacher')))
                
                # Parse quarterly grades
                quarters = []
                for quarter in ['q1', 'q2', 'q3', 'q4']:
                    col = column_mapping.get(quarter)
                    if col:
                        quarter_value = validate_percentage(row.get(col))
                        quarters.append(quarter_value)
                    else:
                        quarters.append(None)
                
                # Calculate predicted score
                predicted_score = calculate_predicted_score(
                    monitoring_percent, quarters, teacher_percent
                )
                
                # Create predicted scores array (4 identical values for compatibility)
                predicted_scores = [predicted_score] * 4
                
                # Prepare actual scores (replace None with 0.0 for calculations)
                actual_scores = [q if q is not None else 0.0 for q in quarters]
                
                student_data = {
                    "student_name": student_name,
                    "monitoring_percent": monitoring_percent,
                    "current_quarters": quarters,
                    "teacher_percent": teacher_percent,
                    "actual_scores": actual_scores,
                    "predicted_scores": predicted_scores,
                    "predicted_score": predicted_score
                }
                
                students_data.append(student_data)
                
            except Exception as e:
                errors.append(f"Row {index + 2}: Error processing data - {str(e)}")
                continue
        
        if not students_data:
            raise HTTPException(
                status_code=400, 
                detail="No valid student data found in Excel file"
            )
        
        response = {
            "students": students_data,
            "total_rows": len(df),
            "processed_rows": len(students_data),
            "warnings": warnings,
            "errors": errors,
            "column_mapping": column_mapping
        }
        
        return response
        
    except pd.errors.EmptyDataError:
        raise HTTPException(status_code=400, detail="Excel file is empty or corrupted")
    except pd.errors.ParserError as e:
        raise HTTPException(status_code=400, detail=f"Error parsing Excel file: {str(e)}")
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        raise HTTPException(status_code=500, detail=f"Unexpected error processing Excel file: {str(e)}")

def generate_excel_template() -> bytes:
    """Generate Excel template with proper column headers"""
    
    template_data = {
        'ФИО': ['Иванов Иван Иванович', 'Петров Петр Петрович', 'Сидорова Анна Владимировна'],
        'Мониторинг, %': [85.5, 92.0, 78.3],
        'Q1, %': [88, 90, 82],
        'Q2, %': [85, 94, 79],
        'Q3, %': [None, 89, 85],  # Example of missing quarter
        'Q4, %': [None, None, None],  # Future quarters
        'Учитель, %': [87, 91, 80]
    }
    
    df = pd.DataFrame(template_data)
    
    # Create Excel file in memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, sheet_name='Grades', index=False)
        
        # Format the worksheet
        worksheet = writer.sheets['Grades']
        
        # Auto-adjust column widths
        for column in worksheet.columns:
            max_length = 0
            column_letter = column[0].column_letter
            for cell in column:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except:
                    pass
            adjusted_width = min(max_length + 2, 30)
            worksheet.column_dimensions[column_letter].width = adjusted_width
    
    output.seek(0)
    return output.getvalue()



